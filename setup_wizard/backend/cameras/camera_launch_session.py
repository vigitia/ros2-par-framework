# Written by Claude Code
"""
Camera launch session of the setup wizard backend: the one camera launch the backend runs.

A camera launch is `ros2 launch <package> <launch file> camera:=<camera> profile:=<name> ...` in
its own process group: the preview's par.launch.py (par_framework_core) with camera_only:=true,
a calibration launch of ros2-par-framework-calibration that starts the camera itself, or a sensor
node run. Its camera is a saved
profile's camera by its name; its streams are in /cameras/<camera name>/. Whatever launch it is,
its frames, settings, stop and watchdog work alike for the APIs built on it (previews, focus,
intrinsics, extrinsics, sensor node runs, settings reads).

Only one camera launch at a time, and none while this backend runs a profile (run_api.py) or
another program's camera runs (e.g. the framework from a terminal), which may hold the same
device. A watchdog stops the launch once nobody has asked for its frames or state for a while,
however it was left (screen closed, app quit or crashed).

The session also owns the backend's ROS node (backend_ros_node.py), started and stopped with the
backend through run_ros_for_camera_launches, the lifespan of the camera preview router.

Lock order: profile_run_state.profile_run_lock, then CameraLaunchSession.camera_launch_lock, then
CameraLaunchSession.session_lock. Take a later lock only while holding the earlier ones you need,
never the other way round.
"""

import collections
from contextlib import asynccontextmanager
import os
import subprocess
import tempfile
import threading
import time

from cameras.camera_types import read_installed_camera_entry
from fastapi import HTTPException
from par_framework_core.par_launch_cameras import CAMERAS_NAMESPACE, get_camera_namespace
from profiles.profile_files import (check_profile_exists, find_profile_camera,
                                    read_profile_cameras_or_raise)
from profiles.profile_run_state import is_profile_running, profile_run_lock
import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.signals import SignalHandlerOptions
from shared.backend_helpers import get_ros2_executable_path, read_log_lines, read_log_tail_text
from shared.backend_ros_node import CAMERA_IMAGE_STREAM_NAME, CameraPreviewRosNode
from shared.node_parameters import get_node_parameter_client
from shared.process_groups import LAUNCH_STOP_SIGNALS, stop_process_group

# How long the camera's launch may take to end after SIGINT, and again after SIGTERM.
CAMERA_PROCESS_STOP_TIMEOUT_S = 10.0
# The package of par.launch.py, which previews and sensor node runs start
CORE_LAUNCH_PACKAGE_NAME = 'par_framework_core'
# The launch's output, read back when the camera process ends early (e.g. camera not connected).
CAMERA_PROCESS_LOG_PATH = os.path.join(tempfile.gettempdir(),
                                       'par_setup_wizard_camera_preview.log')
CAMERA_PROCESS_LOG_TAIL_LINE_COUNT = 8
# How long shutting down waits for the thread that spins the backend's ROS node.
SPIN_THREAD_JOIN_TIMEOUT_S = 5.0
# The app asks for the feeds every 0.5 s while the camera starts, then fetches a frame about every
# 0.1 s; after this long without either request nobody watches, so the watchdog stops the camera.
PREVIEW_UNWATCHED_TIMEOUT_S = 5.0
WATCHDOG_CHECK_INTERVAL_S = 1.0

# The camera a preview or a calibration launch shows: camera_name names its namespace,
# camera_type its entry, serial its unit ('' when none is named), camera_argument is the launch's
# camera:= ('' starts every camera of the profile, e.g. a sensor node run, which shows the first)
PreviewCamera = collections.namedtuple(
    'PreviewCamera', ['camera_name', 'camera_type', 'serial', 'camera_argument'])


class CameraLaunchSession:
    """The process of the running camera launch and the ROS node receiving its frames."""

    def __init__(self, preview_ros_node):
        self.preview_ros_node = preview_ros_node
        # Endpoints run in a thread pool, so start and stop may overlap. Held only briefly: frame,
        # feed and focus requests wait for it
        self.session_lock = threading.Lock()
        # Held by every start and stop of the camera process for their whole duration, including
        # the wait for a stopping process to end, so a start never launches a camera before the
        # old one has ended. Lock order: camera_launch_lock before session_lock
        self.camera_launch_lock = threading.Lock()
        self.camera_process = None
        # The running camera; None while none runs
        self.preview_camera = None
        # The running process's command line, so a start asking for the same launch can keep it
        self.camera_launch_command = None
        # Every start gets a new id, returned to the app; a stop naming an older id is ignored
        self.started_preview_count = 0
        self.running_preview_id = None
        # The publishers of camera images of cameras stopped here. A camera ended by a signal
        # stays in the ROS graph for a while (until its DDS lease runs out), and must count neither
        # as another program's camera nor as the driver of the next preview.
        self.stopped_camera_publisher_gids = set()
        # One parameter client per driver node, kept: rclpy's client cannot be destroyed on its own
        self.parameter_client_by_node_name = {}
        # time.monotonic() of the last start or frame request, read by the watchdog; set through
        # record_preview_request
        self.last_preview_request_monotonic_s = 0.0
        # The profile the camera was started with; None while none runs
        self.profile_name = None
        # Settings changed on this preview's driver and not yet written into a profile, with the
        # values the driver accepted, and the driver node they belong to
        self.unsaved_setting_value_by_name = {}
        self.unsaved_settings_node_name = None

    def record_preview_request(self, preview_id=None):
        """
        Count now as a request watching the preview, so the watchdog keeps the camera running.

        With preview_id, only while that preview still runs. Hold session_lock.
        """
        if preview_id is not None and preview_id != self.running_preview_id:
            return
        self.last_preview_request_monotonic_s = time.monotonic()


# Set while the backend runs, by run_ros_for_camera_launches
_camera_launch_session = None


@asynccontextmanager
async def run_ros_for_camera_launches(app):
    """Start the backend's ROS node with the backend, and stop the camera and ROS with it."""
    global _camera_launch_session
    # uvicorn handles Ctrl+C and SIGTERM; rclpy's own handlers would end the ROS context before
    # this function's cleanup runs.
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    preview_ros_node = CameraPreviewRosNode()
    executor = SingleThreadedExecutor()
    executor.add_node(preview_ros_node)
    spin_thread = threading.Thread(target=_spin_executor, args=(executor,), daemon=True)
    spin_thread.start()
    _camera_launch_session = CameraLaunchSession(preview_ros_node)
    watchdog_stop_event = threading.Event()
    watchdog_thread = threading.Thread(
        target=_stop_unwatched_camera_launch,
        args=(_camera_launch_session, watchdog_stop_event), daemon=True)
    watchdog_thread.start()
    try:
        yield
    finally:
        watchdog_stop_event.set()
        watchdog_thread.join(timeout=SPIN_THREAD_JOIN_TIMEOUT_S)
        _stop_camera_process(_camera_launch_session)
        executor.shutdown()
        spin_thread.join(timeout=SPIN_THREAD_JOIN_TIMEOUT_S)
        preview_ros_node.destroy_node()
        rclpy.try_shutdown()
        _camera_launch_session = None


def _stop_unwatched_camera_launch(session, watchdog_stop_event):
    """Stop the camera when no feeds or frames were asked for in PREVIEW_UNWATCHED_TIMEOUT_S."""
    # Checks until the backend shuts down; wait() returns True as soon as the event is set
    while not watchdog_stop_event.wait(timeout=WATCHDOG_CHECK_INTERVAL_S):
        with session.session_lock:
            if session.camera_process is None:
                continue
            unwatched_duration_s = time.monotonic() - session.last_preview_request_monotonic_s
            unwatched_preview_id = session.running_preview_id
        if unwatched_duration_s > PREVIEW_UNWATCHED_TIMEOUT_S:
            # Only that preview: one started meanwhile is watched
            _stop_camera_process(session, unwatched_preview_id)


def _spin_executor(executor):
    try:
        executor.spin()
    except ExternalShutdownException:
        pass


def get_camera_launch_session() -> CameraLaunchSession:
    """Return the backend's camera launch session; 503 while the backend is still starting."""
    if _camera_launch_session is None:
        raise HTTPException(status_code=503, detail='The camera preview is not ready yet')
    return _camera_launch_session


def create_profile_preview_camera(profile_name, camera_name):
    """Return the profile's camera of this name as a PreviewCamera; HTTP 404 when it has none."""
    check_profile_exists(profile_name)
    profile_camera = find_profile_camera(read_profile_cameras_or_raise(profile_name), camera_name)
    return PreviewCamera(camera_name=profile_camera.camera_name,
                         camera_type=profile_camera.camera_type, serial=profile_camera.serial,
                         camera_argument=profile_camera.camera_name)


def get_preview_topic_name(session, stream_name):
    """Return a stream of the running camera, e.g. /cameras/overhead/camera_info. Hold the lock."""
    if session.preview_camera is None:
        raise HTTPException(status_code=409, detail='No camera preview is running')
    return f'{get_camera_namespace(session.preview_camera.camera_name)}/{stream_name}'


def start_camera_launch(preview_camera, profile_name, launch_package_name, launch_file_name,
                        launch_arguments, may_keep_same_launch=False):
    """
    Start a launch file that starts the camera, as the preview's camera.

    launch_file_name is a launch file of the ROS package launch_package_name.

    Stops the camera of an earlier launch first. launch_arguments: ['name:=value', ...]; camera:=
    is added from preview_camera, profile:= from profile_name. Returns the new preview id. 409
    while this backend runs a profile.

    may_keep_same_launch: when exactly this launch still runs, keep it and only hand out a new
    preview id. So a screen replacing another screen of the same camera (e.g. the camera's next
    section) keeps the camera running, while the old screen's stop, naming the older id, is
    ignored. Calibration launches pass False: each run starts afresh.
    """
    read_installed_camera_entry(preview_camera.camera_type)
    check_profile_exists(profile_name)
    ros2_executable_path = get_ros2_executable_path()
    session = get_camera_launch_session()
    # Held until the camera runs, so a profile run cannot start between the check and the start
    with profile_run_lock:
        if is_profile_running():
            raise HTTPException(status_code=409,
                                detail='A profile is running: stop the running profile first')
        with session.camera_launch_lock:
            camera_launch_command = _create_camera_launch_command(
                preview_camera, profile_name, ros2_executable_path, launch_package_name,
                launch_file_name, launch_arguments)
            if may_keep_same_launch:
                with session.session_lock:
                    if _is_launch_running(session, camera_launch_command):
                        session.started_preview_count += 1
                        session.running_preview_id = session.started_preview_count
                        session.record_preview_request()
                        return session.running_preview_id
            _stop_camera_process_holding_launch_lock(session)
            with session.session_lock:
                return _start_camera_process(session, preview_camera, profile_name,
                                             camera_launch_command)


def _create_camera_launch_command(preview_camera, profile_name, ros2_executable_path,
                                  launch_package_name, launch_file_name, launch_arguments):
    """Return the command line of the camera launch, as a list."""
    camera_launch_command = [ros2_executable_path, 'launch', launch_package_name,
                             launch_file_name, *launch_arguments]
    if preview_camera.camera_argument:
        camera_launch_command.append(f'camera:={preview_camera.camera_argument}')
    camera_launch_command.append(f'profile:={profile_name}')
    return camera_launch_command


def _is_launch_running(session, camera_launch_command):
    """Return whether this command's process runs and has not ended. Hold session_lock."""
    if session.camera_process is None:
        return False
    if session.camera_process.poll() is not None:
        return False
    return session.camera_launch_command == camera_launch_command


def _start_camera_process(session, preview_camera, profile_name, camera_launch_command):
    """Start the camera's launch unless another camera publishes; hold both session locks."""
    # Another camera driver (e.g. the running framework) would fight over the device and mix
    # its frames into the preview. Cameras stopped here may still show up for a while.
    current_publisher_gids = set(session.preview_ros_node.get_camera_image_publishers())
    foreign_publisher_gids = current_publisher_gids - session.stopped_camera_publisher_gids
    if foreign_publisher_gids:
        raise HTTPException(status_code=409,
                            detail=f'Another camera already publishes below '
                                   f'{CAMERAS_NAMESPACE}: stop the running framework first')
    # Forget stopped publishers that have left the graph
    session.stopped_camera_publisher_gids &= current_publisher_gids
    with open(CAMERA_PROCESS_LOG_PATH, 'w') as camera_process_log_file:
        # Its own process group, so stopping reaches the launch and every node it started.
        session.camera_process = subprocess.Popen(
            camera_launch_command, stdout=camera_process_log_file,
            stderr=subprocess.STDOUT, start_new_session=True)
    session.preview_camera = preview_camera
    session.camera_launch_command = camera_launch_command
    session.profile_name = profile_name
    session.started_preview_count += 1
    session.running_preview_id = session.started_preview_count
    session.record_preview_request()
    return session.running_preview_id


def stop_camera_launch(only_preview_id=None) -> None:
    """
    End the running camera launch, e.g. before a profile run needs the camera.

    With only_preview_id, only while that preview runs. Hold neither session lock.
    """
    _stop_camera_process(get_camera_launch_session(), only_preview_id)


def check_camera_process_runs(session):
    """Raise 409 when no preview runs or its camera has stopped. Hold the session lock."""
    camera_process = session.camera_process
    if camera_process is None:
        raise HTTPException(status_code=409, detail='No camera preview is running')
    camera_process_exit_code = camera_process.poll()
    if camera_process_exit_code is not None:
        # Keep the process until the next start or stop, so every request reports the same end
        log_tail_text = read_log_tail_text(CAMERA_PROCESS_LOG_PATH,
                                           CAMERA_PROCESS_LOG_TAIL_LINE_COUNT)
        raise HTTPException(status_code=409,
                            detail=f'The camera stopped (exit code {camera_process_exit_code}). '
                                   f'Is it connected? Last output:\n{log_tail_text}')


def find_own_camera_driver_node_name(session):
    """Return the node publishing the preview camera's image; 503 while there is none."""
    # Simplification: the camera's settings are taken from the node publishing the colour image.
    # For a camera whose images come from a second node (e.g. the event camera, whose frames are
    # rendered by event_camera_renderer), that is the second node. Upgrade: the camera catalog
    # names the driver node for such cameras.
    image_topic_name = get_preview_topic_name(session, CAMERA_IMAGE_STREAM_NAME)
    node_name_by_publisher_gid = session.preview_ros_node.get_camera_image_publishers(
        image_topic_name)
    for publisher_gid, full_node_name in node_name_by_publisher_gid.items():
        # Publishers of earlier previews may still be in the graph; a node not known yet is
        # still starting
        if publisher_gid not in session.stopped_camera_publisher_gids and full_node_name:
            return full_node_name
    raise HTTPException(status_code=503,
                        detail=f'No node publishes {image_topic_name} yet; the camera may still '
                               f'be starting')


def get_driver_parameter_client(session):
    """Return the driver node's name and a parameter client for it, waiting for its services."""
    with session.session_lock:
        check_camera_process_runs(session)
        driver_node_name = find_own_camera_driver_node_name(session)
    return driver_node_name, get_node_parameter_client(session, driver_node_name)


def _stop_camera_process(session: CameraLaunchSession, only_preview_id=None) -> None:
    """
    End the camera's launch: SIGINT like Ctrl+C, then SIGTERM, then SIGKILL.

    With only_preview_id, only while that preview runs. Hold neither session lock: the process is
    detached under session_lock, then waited for under camera_launch_lock alone, so frame and
    feed requests do not wait for its end, but a start does.
    """
    with session.camera_launch_lock:
        _stop_camera_process_holding_launch_lock(session, only_preview_id)


def _stop_camera_process_holding_launch_lock(session: CameraLaunchSession,
                                             only_preview_id=None) -> None:
    """Do what _stop_camera_process does; hold camera_launch_lock, not session_lock."""
    with session.session_lock:
        if only_preview_id is not None and only_preview_id != session.running_preview_id:
            return
        camera_process = _detach_camera_process(session)
    if camera_process is None:
        return
    stop_process_group(camera_process, LAUNCH_STOP_SIGNALS, CAMERA_PROCESS_STOP_TIMEOUT_S)


def _detach_camera_process(session: CameraLaunchSession):
    """Forget the running camera and return its process (None without). Hold session_lock."""
    camera_process = session.camera_process
    if camera_process is not None:
        # Simplification: every publisher present now counts as this camera's, assuming nothing
        # else started publishing during the preview (a start refuses to run beside another).
        session.stopped_camera_publisher_gids |= set(
            session.preview_ros_node.get_camera_image_publishers())
    session.camera_process = None
    session.camera_launch_command = None
    session.preview_camera = None
    session.profile_name = None
    session.unsaved_setting_value_by_name = {}
    session.unsaved_settings_node_name = None
    session.running_preview_id = None
    session.preview_ros_node.stop_receiving()
    return camera_process


def read_camera_process_log_lines() -> list[str]:
    """Return the output of the latest camera launch, line by line; [] without any."""
    return read_log_lines(CAMERA_PROCESS_LOG_PATH)
