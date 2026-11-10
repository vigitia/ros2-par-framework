# Written by Claude Code
"""
Sensor nodes API of the setup wizard backend: a profile's sensor processing nodes, their settings.

Generic, through the ament index and ROS conventions, so a third-party node works without code
here:
- The nodes are the packages registered under launch_helpers.SENSOR_NODE_RESOURCE_TYPE; each
  entry names its display name, description and the nodes it needs.
- The selection is the profile's par_launch switches (par_launch.<package>: true), which
  par.launch.py reads; a node's required nodes are selected along with it.
- A run is par.launch.py with the profile, started as the preview's camera process
  (camera_preview_api.start_camera_launch), so the camera image, stop and watchdog work as for a
  preview. It starts every camera of the profile and shows the first, the one the sensor nodes
  use. The projector app and RViz stay off, and every node gets debug:=true, so each one that has
  a debug parameter opens its preview window on this machine.
- Settings are read and saved by node_settings_api.py, without a run; a run started again picks
  up what was saved.
- What a node publishes is listed from the ROS graph: its sensor_msgs/Image topics are shown as
  frames (camera_preview_api's frame endpoint), every other topic as its latest message in text.
"""

import threading
import time

import camera_preview_api
from fastapi import APIRouter, HTTPException
from par_framework_core.launch_helpers import (add_required_sensor_nodes,
                                               get_sensor_node_package_names,
                                               read_profile_cameras, read_sensor_node_entry)
import profiles_api
from pydantic import BaseModel
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from rclpy.validate_topic_name import validate_topic_name
from rosidl_runtime_py import message_to_yaml
from rosidl_runtime_py.utilities import get_message

SENSOR_NODES_LAUNCH_FILE_NAME = 'par.launch.py'
# A run shows the cameras and the sensor nodes; the projector app and RViz would take the
# projector or open another window. debug:=true is par.launch.py's switch for the debug parameter
# of every node it starts (their preview windows).
RUN_LAUNCH_ARGUMENTS = ['projector_app:=none', 'rviz:=false', 'debug:=true']
# par.launch.py names each sensor node <package>_node, without a namespace
SENSOR_NODE_NAME_SUFFIX = '_node'
IMAGE_MESSAGE_TYPE_NAME = 'sensor_msgs/msg/Image'
# Topics every node has, which say nothing about its output
ROS_INFRASTRUCTURE_TOPIC_NAMES = ('/rosout', '/parameter_events')
# Long arrays (e.g. landmarks of several hands) are cut, so the text stays readable
OUTPUT_MESSAGE_ARRAY_TRUNCATE_LENGTH = 8
OUTPUT_MESSAGE_MAXIMUM_LENGTH_CHARS = 4000
# Outputs are usually published reliably, frames best effort; a best-effort subscriber gets both
OUTPUT_MESSAGE_QOS = QoSProfile(reliability=QoSReliabilityPolicy.BEST_EFFORT,
                                history=QoSHistoryPolicy.KEEP_LAST, depth=1)

sensor_nodes_router = APIRouter()

# Subscriptions to the nodes' non-image outputs, made when the app first asks for a topic:
# {topic name: _OutputMessageReceiver}; changed under _output_receivers_lock
_output_receiver_by_topic = {}
_output_receivers_lock = threading.Lock()


class SensorNodeSummary(BaseModel):
    package_name: str
    display_name: str
    description: str
    required_sensor_nodes: list[str]
    # par_launch.<package> is true in the profile
    is_selected: bool
    # Why the node's entry cannot be used; empty otherwise
    entry_error_text: str = ''


class SensorNodeListResponse(BaseModel):
    profile_name: str
    # The camera the nodes run on: the first of par_launch.cameras
    camera_name: str
    sensor_nodes: list[SensorNodeSummary]


class SensorNodeSelectionRequest(BaseModel):
    profile_name: str
    selected_package_names: list[str]


class SensorNodeSelectionResponse(BaseModel):
    # The selection as stored, with the nodes the selected ones need
    selected_package_names: list[str]


class SensorNodesRunStartRequest(BaseModel):
    profile_name: str


class SensorNodesRunStartResponse(BaseModel):
    # The run's camera is the preview with this id: its frames, and stop with this id
    preview_id: int


class SensorNodeOutputTopic(BaseModel):
    topic_name: str
    type_name: str
    is_image: bool


class RunningSensorNode(BaseModel):
    package_name: str
    full_node_name: str
    # The node is in the ROS graph; False while it starts, or after it ended
    is_running: bool
    output_topics: list[SensorNodeOutputTopic]


class SensorNodesRunState(BaseModel):
    is_launch_running: bool
    # The launch's last output lines once it has ended, e.g. why a node could not start
    launch_log_lines: list[str]
    sensor_nodes: list[RunningSensorNode]


class SensorNodeOutputMessage(BaseModel):
    type_name: str
    # The latest message as YAML, long arrays cut; empty before the first one
    message_text: str
    # How long ago it arrived; None before the first one
    received_age_s: float | None


class _OutputMessageReceiver:
    """Keeps the latest message of one output topic."""

    def __init__(self, type_name):
        self.type_name = type_name
        self.subscription = None
        self.latest_message_lock = threading.Lock()
        self.latest_message = None
        self.latest_message_monotonic_s = None

    def keep_latest_message(self, output_message):
        with self.latest_message_lock:
            self.latest_message = output_message
            self.latest_message_monotonic_s = time.monotonic()


@sensor_nodes_router.get('/api/sensor-nodes')
def get_sensor_node_list(profile_name: str) -> SensorNodeListResponse:
    """List the installed sensor nodes, and which ones the profile starts."""
    launch_section = profiles_api.read_profile_launch_section(profile_name)
    sensor_nodes = []
    for package_name in get_sensor_node_package_names():
        is_selected = launch_section.get(package_name) is True
        try:
            sensor_node_entry = read_sensor_node_entry(package_name)
        except RuntimeError as error:
            # One broken entry from another repo must not hide the other nodes
            sensor_nodes.append(SensorNodeSummary(
                package_name=package_name, display_name=package_name, description='',
                required_sensor_nodes=[], is_selected=is_selected,
                entry_error_text=str(error)))
            continue
        sensor_nodes.append(SensorNodeSummary(
            package_name=package_name,
            display_name=sensor_node_entry['display_name'],
            description=sensor_node_entry['description'],
            required_sensor_nodes=sensor_node_entry['required_sensor_nodes'],
            is_selected=is_selected))
    return SensorNodeListResponse(profile_name=profile_name,
                                  camera_name=_read_main_camera(profile_name).camera_name,
                                  sensor_nodes=sensor_nodes)


@sensor_nodes_router.put('/api/sensor-nodes/selection')
def set_sensor_node_selection(request: SensorNodeSelectionRequest) -> SensorNodeSelectionResponse:
    """Store which sensor nodes the profile starts, with the nodes they need."""
    profiles_api.check_profile_exists(request.profile_name)
    installed_package_names = get_sensor_node_package_names()
    unknown_package_names = sorted(set(request.selected_package_names)
                                   - set(installed_package_names))
    if unknown_package_names:
        raise HTTPException(status_code=400,
                            detail=f'No installed sensor nodes: {unknown_package_names}')
    try:
        selected_package_names = add_required_sensor_nodes(request.selected_package_names)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    switch_value_by_name = {}
    for package_name in installed_package_names:
        switch_value_by_name[package_name] = package_name in selected_package_names
    # par_setup.yaml has every switch false, so an unselected node's key leaves the profile
    profiles_api.write_node_settings_into_profile(request.profile_name, '/par_launch',
                                                  switch_value_by_name)
    return SensorNodeSelectionResponse(selected_package_names=selected_package_names)


@sensor_nodes_router.post('/api/sensor-nodes/run/start')
def start_sensor_nodes_run(request: SensorNodesRunStartRequest) -> SensorNodesRunStartResponse:
    """Start the profile's camera with its selected sensor nodes, ending the running preview."""
    # Only checked here: 404 for no such profile, 409 for one a launch cannot read
    profiles_api.read_profile_launch_section(request.profile_name)
    preview_id = _start_run(request.profile_name)
    return SensorNodesRunStartResponse(preview_id=preview_id)


@sensor_nodes_router.get('/api/sensor-nodes/run/state')
def get_sensor_nodes_run_state(profile_name: str) -> SensorNodesRunState:
    """Return which selected nodes run and what each publishes."""
    launch_section = profiles_api.read_profile_launch_section(profile_name)
    preview_session = camera_preview_api.get_camera_preview_session()
    with preview_session.session_lock:
        launch_process = preview_session.camera_process
        is_launch_running = launch_process is not None and launch_process.poll() is None
        if is_launch_running:
            # Asking for the state counts as watching, also while no frames are fetched
            preview_session.last_preview_request_monotonic_s = time.monotonic()
    launch_log_lines = []
    if not is_launch_running:
        launch_log_lines = camera_preview_api.read_camera_process_log_lines()[-8:]

    preview_ros_node = preview_session.preview_ros_node
    running_full_node_names = set()
    for node_name, node_namespace in preview_ros_node.get_node_names_and_namespaces():
        full_node_name = camera_preview_api.join_node_name(node_namespace, node_name)
        running_full_node_names.add(full_node_name)
    running_sensor_nodes = []
    for package_name in _get_selected_package_names(launch_section):
        full_node_name = '/' + package_name + SENSOR_NODE_NAME_SUFFIX
        is_running = full_node_name in running_full_node_names
        output_topics = []
        if is_running:
            output_topics = _list_output_topics(preview_ros_node, package_name)
        running_sensor_nodes.append(RunningSensorNode(
            package_name=package_name, full_node_name=full_node_name, is_running=is_running,
            output_topics=output_topics))
    return SensorNodesRunState(is_launch_running=is_launch_running,
                               launch_log_lines=launch_log_lines,
                               sensor_nodes=running_sensor_nodes)


@sensor_nodes_router.get('/api/sensor-nodes/output-message')
def get_sensor_node_output_message(topic_name: str) -> SensorNodeOutputMessage:
    """Return the latest message on a node's output topic as text, subscribing on first ask."""
    # Comes from the network and ends up in a subscription: must be a valid ROS topic name
    try:
        validate_topic_name(topic_name)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f'Not a topic name: {error}') from error
    preview_session = camera_preview_api.get_camera_preview_session()
    preview_ros_node = preview_session.preview_ros_node
    with _output_receivers_lock:
        output_receiver = _output_receiver_by_topic.get(topic_name)
        if output_receiver is None:
            output_receiver = _subscribe_to_output_topic(preview_ros_node, topic_name)
            _output_receiver_by_topic[topic_name] = output_receiver
    with output_receiver.latest_message_lock:
        latest_message = output_receiver.latest_message
        latest_message_monotonic_s = output_receiver.latest_message_monotonic_s
    if latest_message is None:
        return SensorNodeOutputMessage(type_name=output_receiver.type_name, message_text='',
                                       received_age_s=None)
    message_text = message_to_yaml(latest_message,
                                   truncate_length=OUTPUT_MESSAGE_ARRAY_TRUNCATE_LENGTH)
    if len(message_text) > OUTPUT_MESSAGE_MAXIMUM_LENGTH_CHARS:
        message_text = message_text[:OUTPUT_MESSAGE_MAXIMUM_LENGTH_CHARS] + '\n…'
    return SensorNodeOutputMessage(
        type_name=output_receiver.type_name, message_text=message_text,
        received_age_s=time.monotonic() - latest_message_monotonic_s)


def _get_selected_package_names(launch_section):
    """Return the installed sensor nodes the profile starts, with the nodes they need."""
    selected_package_names = []
    for package_name in get_sensor_node_package_names():
        if launch_section.get(package_name) is True:
            selected_package_names.append(package_name)
    try:
        return add_required_sensor_nodes(selected_package_names)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def _start_run(profile_name):
    main_camera = _read_main_camera(profile_name)
    # No camera:=, so every camera of the profile starts; the preview shows the main camera
    preview_camera = camera_preview_api.PreviewCamera(
        camera_name=main_camera.camera_name, camera_type=main_camera.camera_type,
        serial=main_camera.serial, camera_argument='', is_profile_camera=True)
    # A new run may publish other types on the same topics; subscriptions are made again
    _forget_output_receivers()
    return camera_preview_api.start_camera_launch(preview_camera, profile_name,
                                                  SENSOR_NODES_LAUNCH_FILE_NAME,
                                                  RUN_LAUNCH_ARGUMENTS)


# Written by Claude Code
def _read_main_camera(profile_name):
    """Return the profile's first camera, the one the sensor nodes use; 409 when unreadable."""
    profile_launch_context = profiles_api.create_profile_launch_context(profile_name)
    try:
        return read_profile_cameras(profile_launch_context)[0]
    except RuntimeError as error:
        raise HTTPException(status_code=409,
                            detail=f'Cannot read the cameras of {profile_name}: {error}'
                            ) from error


def _list_output_topics(preview_ros_node, package_name):
    """Return the topics the node publishes, without ROS's own, sorted."""
    output_topics = []
    topic_names_and_types = preview_ros_node.get_publisher_names_and_types_by_node(
        package_name + SENSOR_NODE_NAME_SUFFIX, '/')
    for topic_name, type_names in topic_names_and_types:
        if topic_name in ROS_INFRASTRUCTURE_TOPIC_NAMES or not type_names:
            continue
        type_name = type_names[0]
        output_topics.append(SensorNodeOutputTopic(
            topic_name=topic_name, type_name=type_name,
            is_image=type_name == IMAGE_MESSAGE_TYPE_NAME))
    output_topics.sort(key=lambda output_topic: output_topic.topic_name)
    return output_topics


def _subscribe_to_output_topic(preview_ros_node, topic_name):
    """Subscribe to a topic with the type its publishers have. Hold _output_receivers_lock."""
    publisher_infos = preview_ros_node.get_publishers_info_by_topic(topic_name)
    if not publisher_infos:
        raise HTTPException(status_code=404, detail=f'Nothing publishes {topic_name} (yet)')
    type_name = publisher_infos[0].topic_type
    try:
        message_class = get_message(type_name)
    except (AttributeError, ModuleNotFoundError, ValueError) as error:
        raise HTTPException(status_code=409,
                            detail=f'The type {type_name} of {topic_name} is not installed '
                                   f'here: {error}') from error
    output_receiver = _OutputMessageReceiver(type_name)
    output_receiver.subscription = preview_ros_node.create_subscription(
        message_class, topic_name, output_receiver.keep_latest_message, OUTPUT_MESSAGE_QOS)
    return output_receiver


def _forget_output_receivers():
    preview_session = camera_preview_api.get_camera_preview_session()
    with _output_receivers_lock:
        for output_receiver in _output_receiver_by_topic.values():
            preview_session.preview_ros_node.destroy_subscription(output_receiver.subscription)
        _output_receiver_by_topic.clear()
