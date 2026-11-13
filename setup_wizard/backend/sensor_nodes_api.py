# Written by Claude Code
"""
Sensor nodes API of the setup wizard backend: a profile's sensor processing nodes, their settings.

Generic, through the ament index and ROS conventions, so a third-party node works without code
here:
- The nodes are the packages registered under launch_helpers.SENSOR_NODE_RESOURCE_TYPE; each
  entry names its display name, description and the nodes it needs.
- The selection is the profile's par_launch lists (par_launch.<package>: [<camera name>, ...]),
  which par.launch.py reads; a node's required nodes are selected along with it, on the same
  camera.
- The profile's apps (par_launch.apps and the projector app) may require sensor nodes too (their
  entries' required_launch_switches). par.launch.py starts them on the cameras each app reads, so
  they are listed and run here by the same rule (launch_helpers.get_par_app_sensor_node_camera_names),
  but never written into the selection: removing an app or binding it to another camera moves them
  along.
- A run is par.launch.py with the profile, started as the preview's camera process
  (camera_launch_session.start_camera_launch), so stop and watchdog work as for a preview. It
  starts every camera of the profile with its sensor nodes, each in /cameras/<camera>; the app
  shows any camera's image by its topic. The apps and RViz stay off (the sensor nodes the apps
  require run, start_projector_app:=false), and every node gets
  debug:=true, so each one that has a debug parameter opens its preview window on this machine.
- Settings are read and saved per camera by node_settings_api.py, without a run; a run started
  again picks up what was saved.
- What a node publishes is listed from the ROS graph: its sensor_msgs/Image topics are shown as
  frames (camera_preview_api's frame endpoint), every other topic as its latest message in text.
  The preview's ROS node keeps those subscriptions only while the run's launch runs.
"""

from dataclasses import dataclass, field
import time

from backend_ros_node import join_node_name
from camera_launch_session import (check_camera_process_runs, get_camera_launch_session,
                                   PreviewCamera, read_camera_process_log_lines,
                                   start_camera_launch)
from fastapi import APIRouter, HTTPException
from par_framework_core.launch_helpers import (get_app_input_camera_names,
                                               get_camera_namespace,
                                               get_par_app_sensor_node_camera_names,
                                               get_sensor_node_name,
                                               get_sensor_node_names_by_camera,
                                               get_sensor_node_package_names,
                                               PAR_APP_ENTRY_INPUTS_KEY, PROJECTOR_APP_NONE,
                                               read_offered_par_app_names, read_par_app_entry,
                                               read_sensor_node_entry, RENDERING_MANAGER_APP_NAME)
from profile_files import (PAR_LAUNCH_NODE_NAME, read_profile_cameras_or_raise,
                           read_profile_launch_section, write_node_settings_into_profile)
from pydantic import BaseModel
from rclpy.exceptions import InvalidTopicNameException
from rclpy.validate_topic_name import validate_topic_name
from rosidl_runtime_py import message_to_yaml
from rosidl_runtime_py.utilities import get_message

SENSOR_NODES_LAUNCH_FILE_NAME = 'par.launch.py'
# A run shows the cameras and the sensor nodes, also those the profile's apps require; the apps
# themselves and RViz would take the projector or open another window. debug:=true is par.launch.py's
# switch for the debug parameter of every node it starts (their preview windows).
RUN_LAUNCH_ARGUMENTS = ['start_projector_app:=false', 'rviz:=false', 'debug:=true']
IMAGE_MESSAGE_TYPE_NAME = 'sensor_msgs/msg/Image'
# Topics every node has, which say nothing about its output
ROS_INFRASTRUCTURE_TOPIC_NAMES = ('/rosout', '/parameter_events')
# Long arrays (e.g. landmarks of several hands) are cut, so the text stays readable
OUTPUT_MESSAGE_ARRAY_TRUNCATE_LENGTH = 8
OUTPUT_MESSAGE_MAXIMUM_LENGTH_CHARS = 4000
# The launch's last output lines shown once it has ended
LAUNCH_LOG_TAIL_LINE_COUNT = 8

sensor_nodes_router = APIRouter()


class SensorNodeSummary(BaseModel):
    package_name: str
    display_name: str
    description: str
    required_sensor_nodes: list[str]
    # The cameras par_launch.<package> lists, in the order of par_launch.cameras; empty when the
    # profile does not start the node
    camera_names: list[str]
    # {camera name: [app display name]}: the cameras it runs on because apps of the profile need it
    # there (directly or through a node an app needs); not part of the profile's selection
    needing_app_names_by_camera: dict[str, list[str]] = {}
    # Why the node's entry cannot be used; empty otherwise
    entry_error_text: str = ''


class SensorNodeListResponse(BaseModel):
    profile_name: str
    # par_launch.cameras in its order; the first is the main camera
    camera_names: list[str]
    sensor_nodes: list[SensorNodeSummary]
    # Per app whose sensor nodes cannot be placed (e.g. an input not bound to a camera): why
    app_requirement_error_texts: list[str] = []


class SensorNodeSelectionRequest(BaseModel):
    profile_name: str
    # {package: [camera name]}; a package left out or with [] does not run
    camera_names_by_package: dict[str, list[str]]


class SensorNodeSelectionResponse(BaseModel):
    # The selection as stored, with the nodes the selected ones need on the same camera; only
    # packages that run somewhere
    camera_names_by_package: dict[str, list[str]]


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
    camera_name: str
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


@sensor_nodes_router.get('/api/sensor-nodes')
def get_sensor_node_list(profile_name: str) -> SensorNodeListResponse:
    """List the installed sensor nodes, and on which cameras the profile starts each."""
    launch_section = read_profile_launch_section(profile_name)
    profile_camera_names = _read_profile_camera_names(profile_name)
    app_requirements = _get_app_requirements(launch_section, profile_camera_names)
    sensor_nodes = []
    for package_name in get_sensor_node_package_names():
        camera_names = _read_listed_camera_names(launch_section, package_name,
                                                 profile_camera_names)
        needing_app_names_by_camera = (
            app_requirements.needing_app_names_by_camera_by_package.get(package_name, {}))
        try:
            sensor_node_entry = read_sensor_node_entry(package_name)
        except RuntimeError as error:
            # One broken entry from another repo must not hide the other nodes
            sensor_nodes.append(SensorNodeSummary(
                package_name=package_name, display_name=package_name, description='',
                required_sensor_nodes=[], camera_names=camera_names,
                needing_app_names_by_camera=needing_app_names_by_camera,
                entry_error_text=str(error)))
            continue
        sensor_nodes.append(SensorNodeSummary(
            package_name=package_name,
            display_name=sensor_node_entry['display_name'],
            description=sensor_node_entry['description'],
            required_sensor_nodes=sensor_node_entry['required_sensor_nodes'],
            camera_names=camera_names,
            needing_app_names_by_camera=needing_app_names_by_camera))
    return SensorNodeListResponse(
        profile_name=profile_name, camera_names=profile_camera_names, sensor_nodes=sensor_nodes,
        app_requirement_error_texts=app_requirements.error_texts)


@sensor_nodes_router.put('/api/sensor-nodes/selection')
def set_sensor_node_selection(request: SensorNodeSelectionRequest) -> SensorNodeSelectionResponse:
    """Store on which cameras the profile starts each sensor node, with the nodes they need."""
    profile_camera_names = _read_profile_camera_names(request.profile_name)
    installed_package_names = get_sensor_node_package_names()
    unknown_package_names = sorted(set(request.camera_names_by_package)
                                   - set(installed_package_names))
    if unknown_package_names:
        raise HTTPException(status_code=400,
                            detail=f'No installed sensor nodes: {unknown_package_names}')
    for package_name, camera_names in request.camera_names_by_package.items():
        unknown_camera_names = sorted(set(camera_names) - set(profile_camera_names))
        if unknown_camera_names:
            raise HTTPException(status_code=400,
                                detail=f'{package_name}: {request.profile_name} has no cameras '
                                       f'{unknown_camera_names}')
    stored_camera_names_by_package = _add_required_sensor_node_cameras(
        request.camera_names_by_package, profile_camera_names)
    # One list per installed node; par_setup.yaml has every list empty, so a node that runs
    # nowhere leaves the profile
    camera_list_by_package = {}
    for package_name in installed_package_names:
        camera_list_by_package[package_name] = stored_camera_names_by_package.get(package_name, [])
    write_node_settings_into_profile(request.profile_name, PAR_LAUNCH_NODE_NAME,
                                     camera_list_by_package)
    return SensorNodeSelectionResponse(camera_names_by_package=stored_camera_names_by_package)


@sensor_nodes_router.post('/api/sensor-nodes/run/start')
def start_sensor_nodes_run(request: SensorNodesRunStartRequest) -> SensorNodesRunStartResponse:
    """Start the profile's camera with its selected sensor nodes, ending the running preview."""
    # Only checked here: 404 for no such profile, 409 for one a launch cannot read
    read_profile_launch_section(request.profile_name)
    preview_id = _start_run(request.profile_name)
    return SensorNodesRunStartResponse(preview_id=preview_id)


@sensor_nodes_router.get('/api/sensor-nodes/run/state')
def get_sensor_nodes_run_state(profile_name: str) -> SensorNodesRunState:
    """Return which selected nodes run and what each publishes."""
    launch_section = read_profile_launch_section(profile_name)
    preview_session = get_camera_launch_session()
    with preview_session.session_lock:
        launch_process = preview_session.camera_process
        is_launch_running = launch_process is not None and launch_process.poll() is None
        if is_launch_running:
            # Asking for the state counts as watching, also while no frames are fetched
            preview_session.record_preview_request()
    launch_log_lines = []
    if not is_launch_running:
        launch_log_lines = read_camera_process_log_lines()[
            -LAUNCH_LOG_TAIL_LINE_COUNT:]

    preview_ros_node = preview_session.preview_ros_node
    running_full_node_names = set()
    for node_name, node_namespace in preview_ros_node.get_node_names_and_namespaces():
        full_node_name = join_node_name(node_namespace, node_name)
        running_full_node_names.add(full_node_name)
    profile_camera_names = _read_profile_camera_names(profile_name)
    needing_app_names_by_camera_by_package = _get_app_requirements(
        launch_section, profile_camera_names).needing_app_names_by_camera_by_package
    camera_names_by_package = {}
    for package_name in get_sensor_node_package_names():
        listed_camera_names = _read_listed_camera_names(launch_section, package_name,
                                                        profile_camera_names)
        app_camera_names = list(needing_app_names_by_camera_by_package.get(package_name, {}))
        camera_names_by_package[package_name] = listed_camera_names + app_camera_names
    running_sensor_nodes = []
    for package_name, camera_names in _add_required_sensor_node_cameras(
            camera_names_by_package, profile_camera_names).items():
        for camera_name in camera_names:
            camera_namespace = get_camera_namespace(camera_name)
            node_name = get_sensor_node_name(package_name)
            full_node_name = join_node_name(camera_namespace, node_name)
            is_running = full_node_name in running_full_node_names
            output_topics = []
            if is_running:
                output_topics = _list_output_topics(preview_ros_node, node_name,
                                                    camera_namespace)
            running_sensor_nodes.append(RunningSensorNode(
                package_name=package_name, camera_name=camera_name,
                full_node_name=full_node_name, is_running=is_running,
                output_topics=output_topics))
    return SensorNodesRunState(is_launch_running=is_launch_running,
                               launch_log_lines=launch_log_lines,
                               sensor_nodes=running_sensor_nodes)


@sensor_nodes_router.get('/api/sensor-nodes/output-message')
def get_sensor_node_output_message(topic_name: str) -> SensorNodeOutputMessage:
    """
    Return the latest message on a node's output topic as text, subscribing on first ask.

    409 while no run's launch runs: the subscription ends with the launch.
    """
    # Comes from the network and ends up in a subscription: must be a valid ROS topic name
    try:
        validate_topic_name(topic_name)
    except InvalidTopicNameException as error:
        raise HTTPException(status_code=400, detail=f'Not a topic name: {error}') from error
    preview_session = get_camera_launch_session()
    preview_ros_node = preview_session.preview_ros_node
    # Under the session lock, so the subscription is made only while the launch runs and is
    # dropped when it stops
    with preview_session.session_lock:
        check_camera_process_runs(preview_session)
        output_receiver = preview_ros_node.get_output_receiver(topic_name)
        if output_receiver is None:
            output_receiver = _subscribe_to_output_topic(preview_ros_node, topic_name)
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


def _read_listed_camera_names(launch_section, package_name, profile_camera_names):
    """Return the profile cameras par_launch.<package> lists, in par_launch.cameras order."""
    listed_camera_names = launch_section.get(package_name)
    # Anything else than a list (par.launch.py refuses it with a message) counts as none here, so
    # the area still opens and saving writes a valid list
    if not isinstance(listed_camera_names, list):
        return []
    camera_names = []
    for camera_name in profile_camera_names:
        if camera_name in listed_camera_names:
            camera_names.append(camera_name)
    return camera_names


def _add_required_sensor_node_cameras(camera_names_by_package, profile_camera_names):
    """
    Return {package: [camera name]} with the nodes the listed ones need on the same camera.

    Only packages that run on a camera; cameras in par_launch.cameras order. 409 when a node needs
    one that is not installed.
    """
    try:
        sensor_node_names_by_camera = get_sensor_node_names_by_camera(camera_names_by_package,
                                                                      profile_camera_names)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    camera_names_by_running_package = {}
    for camera_name in profile_camera_names:
        for package_name in sensor_node_names_by_camera[camera_name]:
            camera_names_by_running_package.setdefault(package_name, []).append(camera_name)
    return camera_names_by_running_package


@dataclass
class _AppRequirements:
    # {package: {camera name: [app display name]}}, with the nodes those need in turn
    needing_app_names_by_camera_by_package: dict = field(default_factory=dict)
    # Per app whose binding or entry is broken: why
    error_texts: list = field(default_factory=list)


def _get_app_requirements(launch_section, profile_camera_names):
    """
    Return where the profile's apps need sensor nodes, as a run without an app starts them.

    The apps are those of par_launch.apps and the projector app, PAR apps only. A run starts
    every camera of the profile, so the inputs are bound among all of them. A broken entry or
    binding gives an error text for that app instead, so the other nodes still show.
    """
    requirements = _AppRequirements()
    if not profile_camera_names:
        return requirements
    try:
        app_names = read_offered_par_app_names(launch_section)
    except RuntimeError as error:
        requirements.error_texts.append(str(error))
        app_names = []
    projector_app_name = str(launch_section.get('projector_app', PROJECTOR_APP_NONE))
    is_par_projector_app = projector_app_name not in (PROJECTOR_APP_NONE,
                                                      RENDERING_MANAGER_APP_NAME)
    if is_par_projector_app and projector_app_name not in app_names:
        app_names.append(projector_app_name)
    main_camera_name = profile_camera_names[0]
    for app_name in app_names:
        try:
            par_app_entry = read_par_app_entry(app_name)
            camera_name_by_input = get_app_input_camera_names(
                launch_section, app_name, par_app_entry[PAR_APP_ENTRY_INPUTS_KEY],
                profile_camera_names, profile_camera_names)
        except RuntimeError as error:
            requirements.error_texts.append(str(error))
            continue
        app_camera_names_by_package = _add_required_sensor_node_cameras(
            get_par_app_sensor_node_camera_names(par_app_entry, camera_name_by_input,
                                                 main_camera_name,
                                                 get_sensor_node_package_names()),
            profile_camera_names)
        for package_name, camera_names in app_camera_names_by_package.items():
            needing_app_names_by_camera = (
                requirements.needing_app_names_by_camera_by_package.setdefault(package_name, {}))
            for camera_name in camera_names:
                needing_app_names = needing_app_names_by_camera.setdefault(camera_name, [])
                needing_app_names.append(par_app_entry['display_name'])
    return requirements


def _start_run(profile_name):
    main_camera = read_profile_cameras_or_raise(profile_name)[0]
    # No camera:=, so every camera of the profile starts. The preview session is named after the
    # main camera; the app shows each camera's image by its topic
    preview_camera = PreviewCamera(
        camera_name=main_camera.camera_name, camera_type=main_camera.camera_type,
        serial=main_camera.serial, camera_argument='', is_profile_camera=True)
    return start_camera_launch(preview_camera, profile_name, SENSOR_NODES_LAUNCH_FILE_NAME,
                               RUN_LAUNCH_ARGUMENTS)


def _read_profile_camera_names(profile_name):
    profile_camera_names = []
    for profile_camera in read_profile_cameras_or_raise(profile_name):
        profile_camera_names.append(profile_camera.camera_name)
    return profile_camera_names


def _list_output_topics(preview_ros_node, node_name, node_namespace):
    """Return the topics the node publishes, without ROS's own, sorted."""
    output_topics = []
    topic_names_and_types = preview_ros_node.get_publisher_names_and_types_by_node(
        node_name, node_namespace)
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
    """Subscribe to a topic with the type its publishers have. Hold the session lock."""
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
    return preview_ros_node.subscribe_to_output_topic(topic_name, type_name, message_class)
