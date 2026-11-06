# Written by Claude Code
"""
Camera preview API of the setup wizard backend: starts one camera and serves its latest frame.

The camera runs as `ros2 launch par_framework_core par.launch.py camera:=<name> camera_only:=true`
in its own process group; a ROS node in this backend receives its frames on the neutral
/camera/image_raw and keeps only the latest one, which the app fetches as JPEG. Only one camera at
a time, because the neutral /camera/... topics exist once. A watchdog stops the camera once the app
has stopped fetching frames, however the preview was left (screen closed, app quit or crashed).
The previewed camera's settings are read live from its driver node through the ROS 2 parameter
services: names, current values and their descriptors (description, range, read-only).
"""

from contextlib import asynccontextmanager
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time

import cameras_api
import cv2
from fastapi import APIRouter, HTTPException, Response
import numpy as np
from par_framework_core.launch_helpers import (BLACKFLY_NODE_PARAMETERS_KEY,
                                               BRIO_NODE_PARAMETERS_KEY,
                                               CU40_NODE_PARAMETERS_KEY,
                                               DEFAULT_TOPIC_NAME_CAMERA_IMAGE)
from pydantic import BaseModel
from rcl_interfaces.msg import ParameterType
import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import parameter_value_to_python
from rclpy.parameter_client import AsyncParameterClient
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Image

# The app shows the preview small; a smaller JPEG also keeps the polling cheap.
PREVIEW_MAXIMUM_WIDTH_PX = 960
PREVIEW_JPEG_QUALITY_PERCENT = 80
# How long the camera's launch may take to end after SIGINT, and again after SIGTERM.
CAMERA_PROCESS_STOP_TIMEOUT_S = 10.0
# The launch's output, read back when the camera process ends early (e.g. camera not connected).
CAMERA_PROCESS_LOG_PATH = os.path.join(tempfile.gettempdir(),
                                       'par_setup_wizard_camera_preview.log')
CAMERA_PROCESS_LOG_TAIL_LINE_COUNT = 8
# How long shutting down waits for the thread that spins the frame receiver.
SPIN_THREAD_JOIN_TIMEOUT_S = 5.0
# The app fetches a frame about every 0.1 s while the preview is shown; after this long without a
# request nobody watches, so the watchdog stops the camera.
PREVIEW_UNWATCHED_TIMEOUT_S = 5.0
WATCHDOG_CHECK_INTERVAL_S = 1.0

# Full name of each camera's driver node, whose parameters are the camera's settings, as the
# create_*_node functions in launch_helpers start them. The Kinect driver runs without a name
# override, so its default name is assumed (not checked with a running Kinect yet).
# Simplification: copied from launch_helpers; upgrade: the camera catalog names the node.
DRIVER_NODE_NAME_BY_CAMERA = {
    'brio': BRIO_NODE_PARAMETERS_KEY,
    'webcam': '/camera/webcam/webcam_node',
    'realsense': '/camera/realsense',
    'blackfly': BLACKFLY_NODE_PARAMETERS_KEY,
    'cu40': CU40_NODE_PARAMETERS_KEY,
    'event': '/camera/event',
    'kinect': '/k4a_ros_device_node',
}
# Shown besides every setting with a range (those are the ones meant to be tuned).
# Simplification: until the camera catalog lists which settings the wizard shows.
EXTRA_SHOWN_SETTING_NAMES_BY_CAMERA = {
    'brio': ['camera_resolution_x', 'camera_resolution_y', 'camera_fps'],
    'webcam': ['image_size', 'pixel_format'],
    'blackfly': ['frame_rate', 'exposure_auto', 'exposure_time', 'gain_auto', 'gain'],
    'cu40': ['camera_resolution_x', 'camera_resolution_y'],
    'kinect': ['color_resolution', 'depth_mode', 'fps'],
}
# How long to wait for the driver's parameter services and each of their answers.
PARAMETER_SERVICE_TIMEOUT_S = 2.0
TYPE_NAME_BY_PARAMETER_TYPE = {
    ParameterType.PARAMETER_BOOL: 'bool',
    ParameterType.PARAMETER_INTEGER: 'integer',
    ParameterType.PARAMETER_DOUBLE: 'double',
    ParameterType.PARAMETER_STRING: 'string',
    ParameterType.PARAMETER_BYTE_ARRAY: 'byte array',
    ParameterType.PARAMETER_BOOL_ARRAY: 'bool array',
    ParameterType.PARAMETER_INTEGER_ARRAY: 'integer array',
    ParameterType.PARAMETER_DOUBLE_ARRAY: 'double array',
    ParameterType.PARAMETER_STRING_ARRAY: 'string array',
}

# The encodings the camera drivers publish on /camera/image_raw, with their channel count
CHANNEL_COUNT_BY_ENCODING = {'mono8': 1, 'bgr8': 3, 'rgb8': 3, 'bgra8': 4, 'rgba8': 4}


class CameraFrameReceiver(Node):
    """Keeps the latest frame of /camera/image_raw while a preview runs, nothing older."""

    def __init__(self):
        super().__init__('setup_wizard_camera_preview')
        self._latest_image_message_lock = threading.Lock()
        self._latest_image_message = None
        self._image_subscription = None

    def start_receiving(self):
        """Subscribe to the camera's frames, forgetting any frame of an earlier preview."""
        with self._latest_image_message_lock:
            self._latest_image_message = None
        if self._image_subscription is None:
            # Frames are published BEST_EFFORT; a reliable subscriber would receive nothing
            frame_qos = QoSProfile(depth=1, history=QoSHistoryPolicy.KEEP_LAST,
                                   reliability=QoSReliabilityPolicy.BEST_EFFORT)
            self._image_subscription = self.create_subscription(
                Image, DEFAULT_TOPIC_NAME_CAMERA_IMAGE, self._on_image_received, frame_qos)

    def stop_receiving(self):
        """Unsubscribe, so frames cost nothing while no preview runs."""
        if self._image_subscription is not None:
            self.destroy_subscription(self._image_subscription)
            self._image_subscription = None
        with self._latest_image_message_lock:
            self._latest_image_message = None

    def get_latest_image_message(self):
        with self._latest_image_message_lock:
            return self._latest_image_message

    def count_camera_image_publishers(self):
        return self.count_publishers(DEFAULT_TOPIC_NAME_CAMERA_IMAGE)

    def _on_image_received(self, image_message):
        with self._latest_image_message_lock:
            self._latest_image_message = image_message


class CameraPreviewSession:
    """The camera process of the running preview and the node receiving its frames."""

    def __init__(self, frame_receiver):
        self.frame_receiver = frame_receiver
        # Endpoints run in a thread pool, so start and stop may overlap
        self.session_lock = threading.Lock()
        self.camera_process = None
        self.camera_name = None
        # One parameter client per driver node, kept: rclpy's client cannot be destroyed on its own
        self.parameter_client_by_node_name = {}
        # time.monotonic() of the last start or frame request, read by the watchdog
        self.last_preview_request_monotonic_s = 0.0


@asynccontextmanager
async def _run_ros_for_camera_preview(app):
    """Start the frame receiver with the backend, and stop the camera and ROS with it."""
    global _camera_preview_session
    # uvicorn handles Ctrl+C and SIGTERM; rclpy's own handlers would end the ROS context before
    # this function's cleanup runs.
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    frame_receiver = CameraFrameReceiver()
    executor = SingleThreadedExecutor()
    executor.add_node(frame_receiver)
    spin_thread = threading.Thread(target=_spin_executor, args=(executor,), daemon=True)
    spin_thread.start()
    _camera_preview_session = CameraPreviewSession(frame_receiver)
    watchdog_stop_event = threading.Event()
    watchdog_thread = threading.Thread(
        target=_stop_unwatched_camera_preview,
        args=(_camera_preview_session, watchdog_stop_event), daemon=True)
    watchdog_thread.start()
    try:
        yield
    finally:
        watchdog_stop_event.set()
        watchdog_thread.join(timeout=SPIN_THREAD_JOIN_TIMEOUT_S)
        with _camera_preview_session.session_lock:
            _stop_camera_process(_camera_preview_session)
        executor.shutdown()
        spin_thread.join(timeout=SPIN_THREAD_JOIN_TIMEOUT_S)
        frame_receiver.destroy_node()
        rclpy.try_shutdown()
        _camera_preview_session = None


def _stop_unwatched_camera_preview(session, watchdog_stop_event):
    """Stop the camera when no frame was requested for PREVIEW_UNWATCHED_TIMEOUT_S."""
    # Checks until the backend shuts down; wait() returns True as soon as the event is set
    while not watchdog_stop_event.wait(timeout=WATCHDOG_CHECK_INTERVAL_S):
        with session.session_lock:
            if session.camera_process is None:
                continue
            unwatched_duration_s = time.monotonic() - session.last_preview_request_monotonic_s
            if unwatched_duration_s > PREVIEW_UNWATCHED_TIMEOUT_S:
                _stop_camera_process(session)


def _spin_executor(executor):
    try:
        executor.spin()
    except ExternalShutdownException:
        pass


# Set while the backend runs, by the router's lifespan
_camera_preview_session = None

camera_preview_router = APIRouter(lifespan=_run_ros_for_camera_preview)


class CameraSetting(BaseModel):
    setting_name: str
    # bool, int, float, str, a list of those, or None while the parameter is not set
    setting_value: bool | int | float | str | list | None
    type_name: str
    description: str
    # The allowed range from the driver's descriptor; None without one
    minimum_value: float | None = None
    maximum_value: float | None = None
    step_value: float | None = None
    is_read_only: bool


class CameraSettingsResponse(BaseModel):
    camera_name: str
    driver_node_name: str
    settings: list[CameraSetting]


class CameraPreviewStartRequest(BaseModel):
    # A key of launch_helpers.CAMERA_DRIVER_REMAPPINGS whose driver is installed.
    camera_name: str


class CameraPreviewStopRequest(BaseModel):
    # Stop only when this camera runs, so a late stop from a screen that switched cameras does not
    # end the preview of the next one. None stops whatever runs.
    camera_name: str | None = None


@camera_preview_router.post('/api/camera-preview/start')
def start_camera_preview(request: CameraPreviewStartRequest) -> None:
    """Start the camera for the preview, stopping the camera of an earlier preview first."""
    _check_camera_is_installed(request.camera_name)
    ros2_executable_path = shutil.which('ros2')
    if ros2_executable_path is None:
        raise HTTPException(status_code=500,
                            detail='ros2 not found: start the backend in a bash with ROS and the '
                                   'workspace sourced')
    session = _get_camera_preview_session()
    with session.session_lock:
        _stop_camera_process(session)
        # Another camera driver (e.g. the running framework) would fight over the device and mix
        # its frames into the preview.
        if session.frame_receiver.count_camera_image_publishers() > 0:
            raise HTTPException(status_code=409,
                                detail=f'Another camera already publishes '
                                       f'{DEFAULT_TOPIC_NAME_CAMERA_IMAGE}: stop the running '
                                       f'framework first')
        session.frame_receiver.start_receiving()
        # No profile: the new profile is not saved yet, so the camera starts with the settings of
        # par_setup.yaml.
        camera_launch_command = [ros2_executable_path, 'launch', 'par_framework_core',
                                 'par.launch.py', f'camera:={request.camera_name}',
                                 'camera_only:=true']
        with open(CAMERA_PROCESS_LOG_PATH, 'w') as camera_process_log_file:
            # Its own process group, so stopping reaches the launch and every node it started.
            session.camera_process = subprocess.Popen(
                camera_launch_command, stdout=camera_process_log_file,
                stderr=subprocess.STDOUT, start_new_session=True)
        session.camera_name = request.camera_name
        session.last_preview_request_monotonic_s = time.monotonic()


@camera_preview_router.post('/api/camera-preview/stop')
def stop_camera_preview(request: CameraPreviewStopRequest) -> None:
    """Stop the preview's camera; a stop naming another camera than the running one is ignored."""
    session = _get_camera_preview_session()
    with session.session_lock:
        if request.camera_name is not None and request.camera_name != session.camera_name:
            return
        _stop_camera_process(session)


@camera_preview_router.get('/api/camera-preview/frame')
def get_camera_preview_frame() -> Response:
    """Return the latest frame as JPEG; 204 while the camera has not sent one yet."""
    session = _get_camera_preview_session()
    with session.session_lock:
        camera_process = session.camera_process
        if camera_process is None:
            raise HTTPException(status_code=409, detail='No camera preview is running')
        session.last_preview_request_monotonic_s = time.monotonic()
        camera_process_exit_code = camera_process.poll()
        if camera_process_exit_code is not None:
            # Keep the process until the next start or stop, so every poll reports the same end
            raise HTTPException(status_code=409,
                                detail=f'The camera stopped (exit code {camera_process_exit_code})'
                                       f'. Is it connected? Last output:\n'
                                       f'{_read_camera_process_log_tail()}')
    image_message = session.frame_receiver.get_latest_image_message()
    if image_message is None:
        return Response(status_code=204)
    preview_frame = _convert_image_message_to_preview_frame(image_message)
    if preview_frame is None:
        raise HTTPException(status_code=409,
                            detail=f'The camera publishes {image_message.encoding!r}, which the '
                                   f'preview cannot show')
    jpeg_quality = [cv2.IMWRITE_JPEG_QUALITY, PREVIEW_JPEG_QUALITY_PERCENT]
    is_encoded, jpeg_bytes = cv2.imencode('.jpg', preview_frame, jpeg_quality)
    if not is_encoded:
        raise HTTPException(status_code=500, detail='Could not encode the frame as JPEG')
    return Response(content=jpeg_bytes.tobytes(), media_type='image/jpeg')


@camera_preview_router.get('/api/camera-preview/settings')
def get_camera_preview_settings() -> CameraSettingsResponse:
    """Return the previewed camera's settings, read live from its driver node."""
    session = _get_camera_preview_session()
    with session.session_lock:
        camera_name = session.camera_name
        if camera_name is None:
            raise HTTPException(status_code=409, detail='No camera preview is running')
        driver_node_name = DRIVER_NODE_NAME_BY_CAMERA.get(camera_name)
        if driver_node_name is None:
            raise HTTPException(status_code=404,
                                detail=f'The driver node of {camera_name} is not known')
        parameter_client = session.parameter_client_by_node_name.get(driver_node_name)
        if parameter_client is None:
            parameter_client = AsyncParameterClient(session.frame_receiver, driver_node_name)
            session.parameter_client_by_node_name[driver_node_name] = parameter_client
    # Outside the lock: waiting for the driver must not hold up the frames.
    if not parameter_client.wait_for_services(timeout_sec=PARAMETER_SERVICE_TIMEOUT_S):
        raise HTTPException(status_code=503,
                            detail=f'{driver_node_name} does not answer yet; the camera may '
                                   f'still be starting')
    settings = _read_camera_settings(parameter_client, camera_name)
    return CameraSettingsResponse(camera_name=camera_name, driver_node_name=driver_node_name,
                                  settings=settings)


def _read_camera_settings(parameter_client, camera_name):
    """Return the settings with a range, plus the camera's extra shown settings, sorted."""
    parameter_names = list(_wait_for_parameter_service(
        parameter_client.list_parameters()).result.names)
    if not parameter_names:
        return []
    descriptors = _wait_for_parameter_service(
        parameter_client.describe_parameters(parameter_names)).descriptors
    parameter_values = _wait_for_parameter_service(
        parameter_client.get_parameters(parameter_names)).values
    extra_shown_setting_names = EXTRA_SHOWN_SETTING_NAMES_BY_CAMERA.get(camera_name, [])
    settings = []
    named_parameters = zip(parameter_names, descriptors, parameter_values)
    for parameter_name, descriptor, parameter_value in named_parameters:
        has_range = bool(descriptor.integer_range) or bool(descriptor.floating_point_range)
        if not has_range and parameter_name not in extra_shown_setting_names:
            continue
        settings.append(_create_camera_setting(parameter_name, descriptor, parameter_value))
    settings.sort(key=lambda camera_setting: camera_setting.setting_name)
    return settings


def _create_camera_setting(parameter_name, descriptor, parameter_value):
    setting_value = parameter_value_to_python(parameter_value)
    # Array parameters arrive as array.array or similar; JSON needs a plain list
    if not isinstance(setting_value, (bool, int, float, str, type(None))):
        setting_value = list(setting_value)
    camera_setting = CameraSetting(
        setting_name=parameter_name,
        setting_value=setting_value,
        type_name=TYPE_NAME_BY_PARAMETER_TYPE.get(parameter_value.type, 'not set'),
        description=descriptor.description,
        is_read_only=descriptor.read_only)
    if descriptor.integer_range:
        integer_range = descriptor.integer_range[0]
        camera_setting.minimum_value = integer_range.from_value
        camera_setting.maximum_value = integer_range.to_value
        camera_setting.step_value = integer_range.step
    elif descriptor.floating_point_range:
        floating_point_range = descriptor.floating_point_range[0]
        camera_setting.minimum_value = floating_point_range.from_value
        camera_setting.maximum_value = floating_point_range.to_value
        camera_setting.step_value = floating_point_range.step
    return camera_setting


def _wait_for_parameter_service(service_future):
    """Wait for a parameter service answer; the executor thread completes the future."""
    answer_received_event = threading.Event()
    service_future.add_done_callback(lambda done_future: answer_received_event.set())
    if not answer_received_event.wait(timeout=PARAMETER_SERVICE_TIMEOUT_S):
        service_future.cancel()
        raise HTTPException(status_code=504,
                            detail='The camera driver did not answer the parameter request')
    return service_future.result()


def _get_camera_preview_session() -> CameraPreviewSession:
    if _camera_preview_session is None:
        raise HTTPException(status_code=503, detail='The camera preview is not ready yet')
    return _camera_preview_session


def _check_camera_is_installed(camera_name: str) -> None:
    """Reject camera names the framework does not know and cameras whose driver is missing."""
    for supported_camera in cameras_api.get_camera_list().cameras:
        if supported_camera.camera_name != camera_name:
            continue
        if not supported_camera.is_installed:
            raise HTTPException(status_code=409,
                                detail=f'The driver of {camera_name} is not installed '
                                       f'({", ".join(supported_camera.driver_package_names)})')
        return
    raise HTTPException(status_code=404, detail=f'Unknown camera {camera_name!r}')


def _stop_camera_process(session: CameraPreviewSession) -> None:
    """End the camera's launch: SIGINT like Ctrl+C, then SIGTERM, then SIGKILL. Hold the lock."""
    camera_process = session.camera_process
    session.camera_process = None
    session.camera_name = None
    session.frame_receiver.stop_receiving()
    if camera_process is None or camera_process.poll() is not None:
        return
    for stop_signal in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(camera_process.pid, stop_signal)
        except ProcessLookupError:
            return
        try:
            camera_process.wait(timeout=CAMERA_PROCESS_STOP_TIMEOUT_S)
            return
        except subprocess.TimeoutExpired:
            continue


def _read_camera_process_log_tail() -> str:
    try:
        with open(CAMERA_PROCESS_LOG_PATH) as camera_process_log_file:
            log_lines = camera_process_log_file.read().splitlines()
    except OSError:
        return '(no output)'
    return '\n'.join(log_lines[-CAMERA_PROCESS_LOG_TAIL_LINE_COUNT:])


def _convert_image_message_to_preview_frame(image_message):
    """Return the frame as a uint8 array for OpenCV (gray or BGR), scaled down for the preview."""
    # The same row handling as scripts/focus_preview.py, but keeping the colours
    channel_count = CHANNEL_COUNT_BY_ENCODING.get(image_message.encoding)
    if channel_count is None:
        return None
    rows = np.frombuffer(image_message.data, dtype=np.uint8).reshape(image_message.height,
                                                                     image_message.step)
    # step may include padding at the end of each row
    pixel_rows = rows[:, :image_message.width * channel_count]
    if channel_count == 1:
        frame = pixel_rows
    else:
        frame = pixel_rows.reshape(image_message.height, image_message.width, channel_count)
        if image_message.encoding == 'rgb8':
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        elif image_message.encoding == 'bgra8':
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        elif image_message.encoding == 'rgba8':
            frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)

    frame_width_px = image_message.width
    if frame_width_px <= PREVIEW_MAXIMUM_WIDTH_PX:
        return frame
    scale_factor = PREVIEW_MAXIMUM_WIDTH_PX / frame_width_px
    preview_height_px = max(1, round(image_message.height * scale_factor))
    return cv2.resize(frame, (PREVIEW_MAXIMUM_WIDTH_PX, preview_height_px),
                      interpolation=cv2.INTER_AREA)
