# Written by Claude Code
"""
Camera preview API of the setup wizard backend: starts one camera, serves its feeds and settings.

The camera runs as `ros2 launch par_framework_core par.launch.py camera:=<name> camera_only:=true`
(plus `profile:=<name>` for a saved profile) in its own process group. Everything else is generic,
so any driver that follows the ROS 2 conventions works without code here:
- The driver node is the node that publishes the neutral /camera/image_raw.
- Its feeds are all sensor_msgs/Image topics that node publishes (e.g. colour, depth and infrared
  of a depth camera). A ROS node in this backend subscribes to a feed once the app asks for it and
  keeps only the latest frame, which the app fetches as JPEG.
- Its settings are its parameters, read and changed through the ROS 2 parameter services, except
  those ROS 2 itself adds to every node and image publisher.
A calibration launch that starts the camera itself runs the same way (start_camera_launch).
Only one camera at a time, because the neutral /camera/... topics exist once. A watchdog stops
the camera once the app has stopped fetching frames, however the preview was left (screen closed,
app quit or crashed).
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
from par_framework_core.launch_helpers import DEFAULT_TOPIC_NAME_CAMERA_IMAGE
import profiles_api
from pydantic import BaseModel
from rcl_interfaces.msg import ParameterType
import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter, parameter_value_to_python
from rclpy.parameter_client import AsyncParameterClient
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from rclpy.validate_topic_name import validate_topic_name
from sensor_msgs.msg import Image

# The app shows the preview small; a smaller JPEG also keeps the polling cheap.
PREVIEW_MAXIMUM_WIDTH_PX = 960
PREVIEW_JPEG_QUALITY_PERCENT = 80
# How long the camera's launch may take to end after SIGINT, and again after SIGTERM.
CAMERA_PROCESS_STOP_TIMEOUT_S = 10.0
# The preview's launch file in par_framework_core, started with camera_only:=true
CAMERA_PREVIEW_LAUNCH_FILE_NAME = 'par.launch.py'
# The launch's output, read back when the camera process ends early (e.g. camera not connected).
CAMERA_PROCESS_LOG_PATH = os.path.join(tempfile.gettempdir(),
                                       'par_setup_wizard_camera_preview.log')
CAMERA_PROCESS_LOG_TAIL_LINE_COUNT = 8
# How long shutting down waits for the thread that spins the frame receiver.
SPIN_THREAD_JOIN_TIMEOUT_S = 5.0
# The app asks for the feeds every 0.5 s while the camera starts, then fetches a frame about every
# 0.1 s; after this long without either request nobody watches, so the watchdog stops the camera.
PREVIEW_UNWATCHED_TIMEOUT_S = 5.0
WATCHDOG_CHECK_INTERVAL_S = 1.0

# The message type of the topics offered as feeds
FEED_MESSAGE_TYPE_NAME = 'sensor_msgs/msg/Image'

# Every parameter of the driver node is shown as a setting, except those ROS 2 itself adds to
# nodes and image publishers: they say nothing about the camera, whichever driver it is.
ROS_INFRASTRUCTURE_PARAMETER_NAMES = ('use_sim_time', 'start_type_description_service')
# rclcpp's QoS overrides of each topic, e.g. qos_overrides./camera/image_raw.publisher.depth
ROS_INFRASTRUCTURE_PARAMETER_PREFIXES = ('qos_overrides.',)
# image_transport's choice of transports, e.g. raw.enable_pub_plugins
ROS_INFRASTRUCTURE_PARAMETER_SUFFIXES = ('.enable_pub_plugins',)
# image_transport plugins name their parameters <topic>.<plugin>.<setting>, e.g.
# image_raw.compressed.jpeg_quality.
# Simplification: the plugins shipped with ROS 2; a parameter of another plugin is shown as a
# camera setting. Upgrade: ask pluginlib for the installed image_transport plugins.
IMAGE_TRANSPORT_PLUGIN_NAMES = ('compressed', 'compressedDepth', 'theora', 'zstd', 'ffmpeg')
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

# 8-bit encodings shown as they are, with their channel count
CHANNEL_COUNT_BY_8_BIT_ENCODING = {'mono8': 1, '8UC1': 1, 'bgr8': 3, 'rgb8': 3, '8UC3': 3,
                                   'bgra8': 4, 'rgba8': 4}
# Encodings of depth and infrared images, scaled to 8 bit for the preview; NumPy type per encoding
NUMPY_TYPE_BY_SCALED_ENCODING = {'mono16': np.uint16, '16UC1': np.uint16, '32FC1': np.float32}
# The share of pixels allowed to be darker or brighter than the scaled range, so a few extreme
# pixels (e.g. reflections in infrared) do not leave the rest of the image black.
SCALED_FEED_CLIPPED_PERCENT = 1.0


class CameraFrameReceiver(Node):
    """Keeps the latest frame of every feed the app has asked for while a preview runs."""

    def __init__(self):
        super().__init__('setup_wizard_camera_preview')
        self._latest_image_message_lock = threading.Lock()
        self._latest_image_message_by_topic = {}
        self._image_subscription_by_topic = {}

    def subscribe_to_feed(self, topic_name):
        """Subscribe to a feed unless already subscribed; its first frame arrives later."""
        if topic_name in self._image_subscription_by_topic:
            return
        # Frames are published BEST_EFFORT; a reliable subscriber would receive nothing
        frame_qos = QoSProfile(depth=1, history=QoSHistoryPolicy.KEEP_LAST,
                               reliability=QoSReliabilityPolicy.BEST_EFFORT)

        def keep_latest_image_message(image_message):
            with self._latest_image_message_lock:
                self._latest_image_message_by_topic[topic_name] = image_message

        self._image_subscription_by_topic[topic_name] = self.create_subscription(
            Image, topic_name, keep_latest_image_message, frame_qos)

    def stop_receiving(self):
        """Unsubscribe from every feed, so frames cost nothing while no preview runs."""
        for image_subscription in self._image_subscription_by_topic.values():
            self.destroy_subscription(image_subscription)
        self._image_subscription_by_topic = {}
        with self._latest_image_message_lock:
            self._latest_image_message_by_topic = {}

    def get_latest_image_message(self, topic_name):
        with self._latest_image_message_lock:
            return self._latest_image_message_by_topic.get(topic_name)

    def get_camera_image_publishers(self):
        """Return the publishers of /camera/image_raw as {endpoint GID: full node name or None}."""
        # The node name is None while ROS knows the publisher but not yet its node, as right after
        # a camera starts (it reports placeholders like _NODE_NAMESPACE_UNKNOWN_ then).
        node_name_by_publisher_gid = {}
        for endpoint_info in self.get_publishers_info_by_topic(DEFAULT_TOPIC_NAME_CAMERA_IMAGE):
            full_node_name = None
            if endpoint_info.node_namespace.startswith('/'):
                full_node_name = join_node_name(endpoint_info.node_namespace,
                                                endpoint_info.node_name)
            node_name_by_publisher_gid[tuple(endpoint_info.endpoint_gid)] = full_node_name
        return node_name_by_publisher_gid

    def list_feed_topic_names(self, full_node_name):
        """Return the sensor_msgs/Image topics the node publishes, sorted."""
        node_namespace, node_name = full_node_name.rsplit('/', 1)
        if not node_namespace:
            node_namespace = '/'
        feed_topic_names = []
        topic_names_and_types = self.get_publisher_names_and_types_by_node(node_name,
                                                                           node_namespace)
        for topic_name, type_names in topic_names_and_types:
            if FEED_MESSAGE_TYPE_NAME in type_names:
                feed_topic_names.append(topic_name)
        return sorted(feed_topic_names)


class CameraPreviewSession:
    """The camera process of the running preview and the node receiving its frames."""

    def __init__(self, frame_receiver):
        self.frame_receiver = frame_receiver
        # Endpoints run in a thread pool, so start and stop may overlap
        self.session_lock = threading.Lock()
        self.camera_process = None
        self.camera_name = None
        # Every start gets a new id, returned to the app; a stop naming an older id is ignored
        self.started_preview_count = 0
        self.running_preview_id = None
        # The publishers of /camera/image_raw of cameras stopped here. A camera ended by a signal
        # stays in the ROS graph for a while (until its DDS lease runs out), and must count neither
        # as another program's camera nor as the driver of the next preview.
        self.stopped_camera_publisher_gids = set()
        # One parameter client per driver node, kept: rclpy's client cannot be destroyed on its own
        self.parameter_client_by_node_name = {}
        # time.monotonic() of the last start or frame request, read by the watchdog
        self.last_preview_request_monotonic_s = 0.0
        # The saved profile the camera was started with; None for par_setup.yaml alone
        self.profile_name = None
        # Settings changed on this preview's driver and not yet written into a profile, with the
        # values the driver accepted, and the driver node they belong to
        self.unsaved_setting_value_by_name = {}
        self.unsaved_settings_node_name = None
        # Changes made without a saved profile (in the new-profile wizard), kept after their camera
        # stopped until the profile is created: {(camera name, driver node name): {setting: value}}
        self.new_profile_setting_values_by_camera_node = {}


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
    """Stop the camera when no feeds or frames were asked for in PREVIEW_UNWATCHED_TIMEOUT_S."""
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
    # The descriptor's free text on allowed values, e.g. the options of a menu; ROS gives it no
    # fixed format, so it is shown as a hint, empty without one.
    additional_constraints: str = ''
    is_read_only: bool


class CameraSettingsResponse(BaseModel):
    camera_name: str
    driver_node_name: str
    settings: list[CameraSetting]
    # Where changes can be saved; None while the camera runs without a saved profile
    profile_name: str | None
    unsaved_setting_names: list[str]


class CameraSettingsSaveResponse(BaseModel):
    profile_name: str
    node_section_name: str
    written_setting_names: list[str]
    removed_setting_names: list[str]


class CameraSettingChangeRequest(BaseModel):
    setting_name: str
    # Converted to the parameter's current type; the driver decides whether it accepts the value
    setting_value: bool | int | float | str | list


class CameraFeed(BaseModel):
    topic_name: str


class CameraFeedsResponse(BaseModel):
    driver_node_name: str
    feeds: list[CameraFeed]


class CameraPreviewStartRequest(BaseModel):
    # A key of launch_helpers.CAMERA_DRIVER_REMAPPINGS whose driver is installed.
    camera_name: str
    # Starts the camera with this saved profile's settings; None uses par_setup.yaml's, e.g. for a
    # profile that is not saved yet.
    profile_name: str | None = None


class CameraPreviewStartResponse(BaseModel):
    # Names this preview in its stop request
    preview_id: int


class CameraPreviewStopRequest(BaseModel):
    # Stop only while this preview runs. A screen closing after a newer screen started a preview,
    # even of the same camera, must not end that one. None stops whatever runs.
    preview_id: int | None = None


@camera_preview_router.post('/api/camera-preview/start')
def start_camera_preview(request: CameraPreviewStartRequest) -> CameraPreviewStartResponse:
    """Start the camera for the preview, stopping the camera of an earlier preview first."""
    preview_id = start_camera_launch(request.camera_name, request.profile_name,
                                     CAMERA_PREVIEW_LAUNCH_FILE_NAME,
                                     [f'camera:={request.camera_name}', 'camera_only:=true'])
    return CameraPreviewStartResponse(preview_id=preview_id)


def start_camera_launch(camera_name, profile_name, launch_file_name, launch_arguments):
    """
    Start a launch file of par_framework_core that starts the camera, as the preview's camera.

    Stops the camera of an earlier preview first. Besides the preview's own launch, a calibration
    launch that starts the camera itself runs this way, so its frames, settings, stop and
    watchdog work as for a preview. launch_arguments: ['name:=value', ...]; profile:= is added
    for a saved profile. Returns the new preview id.
    """
    _check_camera_is_installed(camera_name)
    if profile_name is not None:
        profiles_api.check_profile_exists(profile_name)
    ros2_executable_path = shutil.which('ros2')
    if ros2_executable_path is None:
        raise HTTPException(status_code=500,
                            detail='ros2 not found: start the backend in a bash with ROS and the '
                                   'workspace sourced')
    session = get_camera_preview_session()
    with session.session_lock:
        _stop_camera_process(session)
        # Another camera driver (e.g. the running framework) would fight over the device and mix
        # its frames into the preview. Cameras stopped here may still show up for a while.
        current_publisher_gids = set(session.frame_receiver.get_camera_image_publishers())
        foreign_publisher_gids = current_publisher_gids - session.stopped_camera_publisher_gids
        if foreign_publisher_gids:
            raise HTTPException(status_code=409,
                                detail=f'Another camera already publishes '
                                       f'{DEFAULT_TOPIC_NAME_CAMERA_IMAGE}: stop the running '
                                       f'framework first')
        # Forget stopped publishers that have left the graph
        session.stopped_camera_publisher_gids &= current_publisher_gids
        camera_launch_command = [ros2_executable_path, 'launch', 'par_framework_core',
                                 launch_file_name, *launch_arguments]
        if profile_name is not None:
            camera_launch_command.append(f'profile:={profile_name}')
        with open(CAMERA_PROCESS_LOG_PATH, 'w') as camera_process_log_file:
            # Its own process group, so stopping reaches the launch and every node it started.
            session.camera_process = subprocess.Popen(
                camera_launch_command, stdout=camera_process_log_file,
                stderr=subprocess.STDOUT, start_new_session=True)
        session.camera_name = camera_name
        session.profile_name = profile_name
        session.last_preview_request_monotonic_s = time.monotonic()
        session.started_preview_count += 1
        session.running_preview_id = session.started_preview_count
        return session.running_preview_id


@camera_preview_router.post('/api/camera-preview/stop')
def stop_camera_preview(request: CameraPreviewStopRequest) -> None:
    """Stop the preview's camera; a stop naming another preview than the running one is ignored."""
    session = get_camera_preview_session()
    with session.session_lock:
        if request.preview_id is not None and request.preview_id != session.running_preview_id:
            return
        _stop_camera_process(session)


@camera_preview_router.get('/api/camera-preview/feeds')
def get_camera_preview_feeds() -> CameraFeedsResponse:
    """List the previewed camera's image topics; 503 while its driver node is not up yet."""
    session = get_camera_preview_session()
    with session.session_lock:
        check_camera_process_runs(session)
        # Waiting for a starting camera counts as watching: ROS may report its node seconds after
        # the driver runs, and the watchdog must not stop it before the first frame is asked for
        session.last_preview_request_monotonic_s = time.monotonic()
        driver_node_name = _find_own_camera_driver_node_name(session)
    try:
        feed_topic_names = session.frame_receiver.list_feed_topic_names(driver_node_name)
    except Exception as error:
        # rclpy raises when the node has left the graph meanwhile, e.g. the camera just stopped
        raise HTTPException(status_code=503,
                            detail=f'Cannot list the topics of {driver_node_name}: {error}'
                            ) from error
    feeds = []
    for feed_topic_name in feed_topic_names:
        feeds.append(CameraFeed(topic_name=feed_topic_name))
    return CameraFeedsResponse(driver_node_name=driver_node_name, feeds=feeds)


@camera_preview_router.get('/api/camera-preview/frame')
def get_camera_preview_frame(topic_name: str = DEFAULT_TOPIC_NAME_CAMERA_IMAGE) -> Response:
    """Return a feed's latest frame as JPEG; 204 while it has not sent one yet."""
    # Comes from the network and ends up in a subscription: must be a valid ROS topic name
    try:
        validate_topic_name(topic_name)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f'Not a topic name: {error}') from error
    session = get_camera_preview_session()
    with session.session_lock:
        check_camera_process_runs(session)
        session.last_preview_request_monotonic_s = time.monotonic()
        session.frame_receiver.subscribe_to_feed(topic_name)
    image_message = session.frame_receiver.get_latest_image_message(topic_name)
    if image_message is None:
        return Response(status_code=204)
    preview_frame = _convert_image_message_to_preview_frame(image_message)
    if preview_frame is None:
        raise HTTPException(status_code=409,
                            detail=f'{topic_name} has the encoding {image_message.encoding!r}, '
                                   f'which the preview cannot show')
    jpeg_quality = [cv2.IMWRITE_JPEG_QUALITY, PREVIEW_JPEG_QUALITY_PERCENT]
    is_encoded, jpeg_bytes = cv2.imencode('.jpg', preview_frame, jpeg_quality)
    if not is_encoded:
        raise HTTPException(status_code=500, detail='Could not encode the frame as JPEG')
    return Response(content=jpeg_bytes.tobytes(), media_type='image/jpeg')


@camera_preview_router.get('/api/camera-preview/settings')
def get_camera_preview_settings() -> CameraSettingsResponse:
    """Return the previewed camera's settings, read live from its driver node."""
    session = get_camera_preview_session()
    driver_node_name, parameter_client = get_driver_parameter_client(session)
    settings = read_node_settings(parameter_client)
    with session.session_lock:
        profile_name = session.profile_name
        unsaved_setting_names = sorted(session.unsaved_setting_value_by_name)
    return CameraSettingsResponse(camera_name=session.camera_name or '',
                                  driver_node_name=driver_node_name, settings=settings,
                                  profile_name=profile_name,
                                  unsaved_setting_names=unsaved_setting_names)


@camera_preview_router.put('/api/camera-preview/settings')
def change_camera_preview_setting(request: CameraSettingChangeRequest) -> None:
    """Set one setting on the running driver; 409 with the driver's reason when it refuses."""
    session = get_camera_preview_session()
    with session.session_lock:
        changed_preview_id = session.running_preview_id
    driver_node_name, parameter_client = get_driver_parameter_client(session)
    current_parameter_values = wait_for_driver_service_answer(
        parameter_client.get_parameters([request.setting_name])).values
    if not current_parameter_values:
        raise HTTPException(status_code=404,
                            detail=f'{driver_node_name} has no setting {request.setting_name!r}')
    parameter_type = Parameter.Type(current_parameter_values[0].type)
    parameter_value = convert_setting_value(request.setting_value, parameter_type)
    parameter = Parameter(request.setting_name, parameter_type, parameter_value)
    set_results = wait_for_driver_service_answer(
        parameter_client.set_parameters([parameter])).results
    if not set_results[0].successful:
        refusal_reason = set_results[0].reason or 'no reason given'
        raise HTTPException(status_code=409,
                            detail=f'{driver_node_name} refused {request.setting_name} = '
                                   f'{parameter_value!r}: {refusal_reason}')
    with session.session_lock:
        # A camera restarted meanwhile has new settings, which this change is not part of
        if session.running_preview_id == changed_preview_id:
            # The value as the driver accepted it, in the parameter's own type (e.g. 5.0 for a
            # double), so ROS accepts it from the profile at the next start
            session.unsaved_setting_value_by_name[request.setting_name] = (
                _convert_parameter_value_to_plain_python(parameter.get_parameter_value()))
            session.unsaved_settings_node_name = driver_node_name


@camera_preview_router.post('/api/camera-preview/settings/save-to-profile')
def save_camera_preview_settings_to_profile() -> CameraSettingsSaveResponse:
    """Write the settings changed on the running driver into the profile it was started with."""
    session = get_camera_preview_session()
    with session.session_lock:
        check_camera_process_runs(session)
        profile_name = session.profile_name
        preview_id = session.running_preview_id
        driver_node_name = session.unsaved_settings_node_name
        setting_value_by_name = dict(session.unsaved_setting_value_by_name)
    if profile_name is None:
        raise HTTPException(status_code=409,
                            detail='The camera runs without a saved profile; the new-profile '
                                   'wizard saves its changes when the profile is created')
    if not setting_value_by_name:
        return CameraSettingsSaveResponse(profile_name=profile_name, node_section_name='',
                                          written_setting_names=[], removed_setting_names=[])
    # Simplification: a setting the launch file sets itself after the parameter files (e.g. a
    # camera's camera_info_url) is saved too, but the launch value wins at the next start.
    # Upgrade: mark such settings read-only in the drivers, or compare with the launch's values.
    write_result = profiles_api.write_node_settings_into_profile(
        profile_name, driver_node_name, setting_value_by_name)
    with session.session_lock:
        if session.running_preview_id == preview_id:
            for setting_name in setting_value_by_name:
                session.unsaved_setting_value_by_name.pop(setting_name, None)
    return CameraSettingsSaveResponse(profile_name=profile_name,
                                      node_section_name=write_result.node_section_name,
                                      written_setting_names=write_result.written_setting_names,
                                      removed_setting_names=write_result.removed_setting_names)


@camera_preview_router.delete('/api/camera-preview/new-profile-settings')
def discard_new_profile_settings() -> None:
    """Forget setting changes kept for a new profile, e.g. when the new-profile wizard starts."""
    session = get_camera_preview_session()
    with session.session_lock:
        session.new_profile_setting_values_by_camera_node = {}
        if session.profile_name is None:
            session.unsaved_setting_value_by_name = {}


def take_new_profile_setting_values(camera_name):
    """
    Return the settings changed without a profile for camera_name, {driver node: {name: value}}.

    Includes the running preview's changes. Forgets all kept changes, also those of other
    cameras, which the new profile does not have.
    """
    session = get_camera_preview_session()
    with session.session_lock:
        _keep_unsaved_settings_for_new_profile(session)
        if session.profile_name is None:
            session.unsaved_setting_value_by_name = {}
        setting_values_by_node_name = {}
        for (kept_camera_name, node_name), setting_value_by_name in (
                session.new_profile_setting_values_by_camera_node.items()):
            if kept_camera_name == camera_name:
                setting_values_by_node_name[node_name] = dict(setting_value_by_name)
        session.new_profile_setting_values_by_camera_node = {}
    return setting_values_by_node_name


def _keep_unsaved_settings_for_new_profile(session):
    """Copy a profile-less preview's changes into the kept ones. Hold the session lock."""
    if session.profile_name is not None or not session.unsaved_setting_value_by_name:
        return
    camera_node_key = (session.camera_name, session.unsaved_settings_node_name)
    kept_setting_value_by_name = session.new_profile_setting_values_by_camera_node.setdefault(
        camera_node_key, {})
    kept_setting_value_by_name.update(session.unsaved_setting_value_by_name)


def _convert_parameter_value_to_plain_python(parameter_value):
    """Return the parameter value as a plain Python value, which JSON and YAML can hold."""
    setting_value = parameter_value_to_python(parameter_value)
    # Array parameters arrive as array.array or similar
    if not isinstance(setting_value, (bool, int, float, str, type(None))):
        setting_value = list(setting_value)
    return setting_value


def join_node_name(node_namespace, node_name):
    if node_namespace.endswith('/'):
        return node_namespace + node_name
    return f'{node_namespace}/{node_name}'


def check_camera_process_runs(session):
    """Raise 409 when no preview runs or its camera has stopped. Hold the session lock."""
    camera_process = session.camera_process
    if camera_process is None:
        raise HTTPException(status_code=409, detail='No camera preview is running')
    camera_process_exit_code = camera_process.poll()
    if camera_process_exit_code is not None:
        # Keep the process until the next start or stop, so every request reports the same end
        raise HTTPException(status_code=409,
                            detail=f'The camera stopped (exit code {camera_process_exit_code}). '
                                   f'Is it connected? Last output:\n'
                                   f'{_read_camera_process_log_tail()}')


def _find_own_camera_driver_node_name(session):
    """Return the node publishing /camera/image_raw for this preview; 503 while there is none."""
    # Simplification: the camera's settings are taken from the node publishing the colour image.
    # For a camera whose images come from a second node (e.g. the event camera, whose frames are
    # rendered by event_camera_renderer), that is the second node. Upgrade: the camera catalog
    # names the driver node for such cameras.
    node_name_by_publisher_gid = session.frame_receiver.get_camera_image_publishers()
    for publisher_gid, full_node_name in node_name_by_publisher_gid.items():
        # Publishers of earlier previews may still be in the graph; a node not known yet is
        # still starting
        if publisher_gid not in session.stopped_camera_publisher_gids and full_node_name:
            return full_node_name
    raise HTTPException(status_code=503,
                        detail=f'No node publishes {DEFAULT_TOPIC_NAME_CAMERA_IMAGE} yet; the '
                               f'camera may still be starting')


def get_driver_parameter_client(session):
    """Return the driver node's name and a parameter client for it, waiting for its services."""
    with session.session_lock:
        check_camera_process_runs(session)
        driver_node_name = _find_own_camera_driver_node_name(session)
    return driver_node_name, get_node_parameter_client(session, driver_node_name)


def get_node_parameter_client(session, full_node_name):
    """Return a parameter client for a node of the running launch, waiting for its services."""
    with session.session_lock:
        parameter_client = session.parameter_client_by_node_name.get(full_node_name)
        if parameter_client is None:
            parameter_client = AsyncParameterClient(session.frame_receiver, full_node_name)
            session.parameter_client_by_node_name[full_node_name] = parameter_client
    # Outside the lock: waiting for the node must not hold up the frames.
    if not parameter_client.wait_for_services(timeout_sec=PARAMETER_SERVICE_TIMEOUT_S):
        raise HTTPException(status_code=503,
                            detail=f'{full_node_name} does not answer yet; it may still be '
                                   f'starting')
    return parameter_client


def convert_setting_value(setting_value, parameter_type):
    """Return the value from the app in the parameter's type; 400 when it does not fit."""
    try:
        if parameter_type == Parameter.Type.BOOL and isinstance(setting_value, bool):
            return setting_value
        if parameter_type == Parameter.Type.INTEGER:
            return _convert_to_integer(setting_value)
        if parameter_type == Parameter.Type.DOUBLE:
            return float(setting_value)
        if parameter_type == Parameter.Type.STRING:
            return str(setting_value)
        if parameter_type == Parameter.Type.INTEGER_ARRAY:
            return [_convert_to_integer(element) for element in setting_value]
        if parameter_type == Parameter.Type.DOUBLE_ARRAY:
            return [float(element) for element in setting_value]
        if parameter_type == Parameter.Type.STRING_ARRAY:
            return [str(element) for element in setting_value]
        if parameter_type == Parameter.Type.BOOL_ARRAY:
            if all(isinstance(element, bool) for element in setting_value):
                return list(setting_value)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400,
                            detail=f'{setting_value!r} does not fit a {parameter_type.name} '
                                   f'setting: {error}') from error
    raise HTTPException(status_code=400,
                        detail=f'{setting_value!r} does not fit a {parameter_type.name} setting')


def _convert_to_integer(value):
    """Accept whole numbers only: silently cutting 2.5 to 2 would set another value than asked."""
    if isinstance(value, bool):
        raise ValueError('a bool is not a number')
    integer_value = int(value)
    if integer_value != value:
        raise ValueError(f'{value} is not a whole number')
    return integer_value


def read_node_settings(parameter_client):
    """Return every parameter of the node except ROS's own, sorted by name."""
    all_parameter_names = wait_for_driver_service_answer(
        parameter_client.list_parameters()).result.names
    parameter_names = []
    for parameter_name in all_parameter_names:
        if not _is_ros_infrastructure_parameter(parameter_name):
            parameter_names.append(parameter_name)
    if not parameter_names:
        return []
    descriptors = wait_for_driver_service_answer(
        parameter_client.describe_parameters(parameter_names)).descriptors
    parameter_values = wait_for_driver_service_answer(
        parameter_client.get_parameters(parameter_names)).values
    settings = []
    named_parameters = zip(parameter_names, descriptors, parameter_values)
    for parameter_name, descriptor, parameter_value in named_parameters:
        settings.append(_create_camera_setting(parameter_name, descriptor, parameter_value))
    settings.sort(key=lambda camera_setting: camera_setting.setting_name)
    return settings


def _is_ros_infrastructure_parameter(parameter_name):
    """Tell whether ROS 2 itself added the parameter, rather than the camera driver."""
    if parameter_name in ROS_INFRASTRUCTURE_PARAMETER_NAMES:
        return True
    if parameter_name.startswith(ROS_INFRASTRUCTURE_PARAMETER_PREFIXES):
        return True
    if parameter_name.endswith(ROS_INFRASTRUCTURE_PARAMETER_SUFFIXES):
        return True
    # A plugin's name sits between the topic and the setting, never first or last
    inner_name_parts = parameter_name.split('.')[1:-1]
    for name_part in inner_name_parts:
        if name_part in IMAGE_TRANSPORT_PLUGIN_NAMES:
            return True
    return False


def _create_camera_setting(parameter_name, descriptor, parameter_value):
    setting_value = _convert_parameter_value_to_plain_python(parameter_value)
    camera_setting = CameraSetting(
        setting_name=parameter_name,
        setting_value=setting_value,
        type_name=TYPE_NAME_BY_PARAMETER_TYPE.get(parameter_value.type, 'not set'),
        description=descriptor.description,
        additional_constraints=descriptor.additional_constraints,
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


def wait_for_driver_service_answer(service_future, timeout_s=PARAMETER_SERVICE_TIMEOUT_S):
    """Wait for a driver's service answer; the executor thread completes the future."""
    answer_received_event = threading.Event()
    service_future.add_done_callback(lambda done_future: answer_received_event.set())
    if not answer_received_event.wait(timeout=timeout_s):
        service_future.cancel()
        raise HTTPException(status_code=504, detail='The camera driver did not answer in time')
    return service_future.result()


def get_camera_preview_session() -> CameraPreviewSession:
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
    if camera_process is not None:
        # Simplification: every publisher present now counts as this camera's, assuming nothing
        # else started publishing during the preview (a start refuses to run beside another).
        session.stopped_camera_publisher_gids |= set(
            session.frame_receiver.get_camera_image_publishers())
    session.camera_process = None
    _keep_unsaved_settings_for_new_profile(session)
    session.camera_name = None
    session.profile_name = None
    session.unsaved_setting_value_by_name = {}
    session.unsaved_settings_node_name = None
    session.running_preview_id = None
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
    log_lines = read_camera_process_log_lines()
    if not log_lines:
        return '(no output)'
    return '\n'.join(log_lines[-CAMERA_PROCESS_LOG_TAIL_LINE_COUNT:])


def read_camera_process_log_lines() -> list[str]:
    """Return the output of the latest camera launch, line by line; [] without any."""
    try:
        with open(CAMERA_PROCESS_LOG_PATH) as camera_process_log_file:
            return camera_process_log_file.read().splitlines()
    except OSError:
        return []


def convert_image_message_to_frame(image_message):
    """Return the frame at full size as a uint8 array (gray or BGR); None for other encodings."""
    encoding = image_message.encoding
    if encoding in CHANNEL_COUNT_BY_8_BIT_ENCODING:
        return _read_8_bit_frame(image_message)
    if encoding in NUMPY_TYPE_BY_SCALED_ENCODING:
        return _read_scaled_frame(image_message)
    return None


def _convert_image_message_to_preview_frame(image_message):
    """Return the frame as a uint8 array for OpenCV (gray or BGR), scaled down for the preview."""
    frame = convert_image_message_to_frame(image_message)
    if frame is None:
        return None

    frame_width_px = image_message.width
    if frame_width_px <= PREVIEW_MAXIMUM_WIDTH_PX:
        return frame
    scale_factor = PREVIEW_MAXIMUM_WIDTH_PX / frame_width_px
    preview_height_px = max(1, round(image_message.height * scale_factor))
    return cv2.resize(frame, (PREVIEW_MAXIMUM_WIDTH_PX, preview_height_px),
                      interpolation=cv2.INTER_AREA)


def _read_8_bit_frame(image_message):
    """Return an 8-bit image as gray or BGR, as OpenCV expects."""
    # The same row handling as scripts/focus_preview.py, but keeping the colours
    channel_count = CHANNEL_COUNT_BY_8_BIT_ENCODING[image_message.encoding]
    rows = np.frombuffer(image_message.data, dtype=np.uint8).reshape(image_message.height,
                                                                     image_message.step)
    # step may include padding at the end of each row
    pixel_rows = rows[:, :image_message.width * channel_count]
    if channel_count == 1:
        return pixel_rows
    frame = pixel_rows.reshape(image_message.height, image_message.width, channel_count)
    if image_message.encoding == 'rgb8':
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    if image_message.encoding == 'bgra8':
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    if image_message.encoding == 'rgba8':
        return cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
    return frame


def _read_scaled_frame(image_message):
    """Return a depth or 16-bit image as 8-bit gray, its valid pixels' range stretched to 0-255."""
    numpy_type = np.dtype(NUMPY_TYPE_BY_SCALED_ENCODING[image_message.encoding])
    if image_message.is_bigendian:
        numpy_type = numpy_type.newbyteorder('>')
    bytes_per_pixel = numpy_type.itemsize
    rows = np.frombuffer(image_message.data, dtype=np.uint8).reshape(image_message.height,
                                                                     image_message.step)
    pixel_rows = rows[:, :image_message.width * bytes_per_pixel]
    frame_values = np.ascontiguousarray(pixel_rows).view(numpy_type).astype(np.float32)
    # 0 and NaN mean "no measurement" in depth images; they stay black
    is_valid_pixel = np.isfinite(frame_values) & (frame_values > 0)
    gray_frame = np.zeros(frame_values.shape, dtype=np.uint8)
    if not np.any(is_valid_pixel):
        return gray_frame
    valid_values = frame_values[is_valid_pixel]
    lowest_shown_value = np.percentile(valid_values, SCALED_FEED_CLIPPED_PERCENT)
    highest_shown_value = np.percentile(valid_values, 100 - SCALED_FEED_CLIPPED_PERCENT)
    shown_value_span = max(highest_shown_value - lowest_shown_value, 1e-6)
    scaled_values = (frame_values - lowest_shown_value) / shown_value_span * 255
    gray_frame[is_valid_pixel] = np.clip(scaled_values[is_valid_pixel], 0, 255).astype(np.uint8)
    return gray_frame
