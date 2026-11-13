# Written by Claude Code
"""
Bring up the PAR framework as the parameter file's par_launch section describes it.

The framework's one entry point for every camera. par_launch.cameras names the setup's cameras,
each with its unit, e.g. {overhead: 'blackfly:22260470'} (camera types are installed in the ament
index, par_framework_cameras), and par_launch switches each node on or off. Every camera runs in
/cameras/<name>, e.g. /cameras/overhead/image_raw. A sensor node runs once on each camera its
par_launch key lists, e.g. fiducials_detector: [overhead], in that camera's namespace, so its
outputs are the camera's too (/cameras/overhead/fiducials). With another parameter file:

    ros2 launch par_framework_core par.launch.py params_file:=/path/to/<file>.yaml

profile:=<name> adds config/profiles/<name>.yaml on top of it: only what differs for another
physical setup, which also gets its own camera pose and projection calibration in
config/calibration/extrinsics/<name>/.

Each of them can be overridden for one run, e.g. camera:=kinect rviz:=true hand_landmarks:=false;
an argument left empty keeps the parameter file's value. camera:= starts one camera instead of all:
a name of par_launch.cameras, or <type>[:<serial>] for a unit the profile does not name. Every
camera gets its own projection calibration (/cameras/<name>/projection_mapping and
projection_corners). RViz and the rendering manager use the first camera (the main camera) and
its projection calibration. With a camera that offers depth on its colour image's grid
(depth_registered in its entry's streams) the detectors also use its depth. camera_only:=true
starts just the cameras and their mount transforms, e.g. for a preview or a calibration. An event
camera (event) delivers its events collected into images, and the raw events on
/cameras/<name>/events; it has no calibration. Camera intrinsics are
config/calibration/intrinsics/<profile>/camera_info_<type>[_<serial>].yaml, per unit; without
profile:= the shared config/calibration/intrinsics/ folder.

debug:=true turns on the debug windows of every started node that has one, e.g. for testing
gestures: camera:=kinect hand_landmarks:=true gesture_detector:=true debug:=true.

par_launch.projector_app (or projector_app:=<name>) chooses the one app that owns the projector,
on par_launch.projector_display_id: none, an installed PAR app (a package registered in the ament
index under par_framework_apps, see templates/par_app/; the framework nodes it requires are
started too), or rendering_manager, the Wayland compositor whose ROS bridge shows one app on every
detected page. A PAR app reads the cameras its entry's inputs name: par_launch.app_inputs binds
each input to a camera, e.g. app_inputs: {demo_app: {camera: overhead}}; an input left unbound
reads the only camera of the run. The app's required sensor nodes run on its bound cameras;
start_projector_app:=false starts only those, not the app (the setup wizard's sensor node run).

A camera taking single high-resolution frames on request (e.g. a Blackfly S in software trigger
mode, see par_setup.yaml) is an ordinary camera of par_launch.cameras with its own settings.
"""

import os

from ament_index_python.packages import get_package_share_directory
from ament_index_python.resources import has_resource
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess, GroupAction,
                            IncludeLaunchDescription, LogInfo, OpaqueFunction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, SetRemap
from par_framework_core.launch_helpers import (create_camera_actions,
                                               create_camera_choice_launch_argument,
                                               create_camera_stream_remappings,
                                               create_profile_launch_argument,
                                               create_projection_calibration_server_node,
                                               create_projector_display_id_launch_argument,
                                               get_app_input_camera_names,
                                               get_camera_namespace, get_cameras_to_start,
                                               get_par_app_sensor_node_camera_names,
                                               get_installed_par_setup_path, get_params_file_paths,
                                               get_profile_name, get_projector_display_id,
                                               get_sensor_node_name,
                                               get_sensor_node_names_by_camera,
                                               get_sensor_node_package_names,
                                               PAR_APP_ENTRY_INPUTS_KEY,
                                               PAR_LAUNCH_CAMERAS_KEY, PROJECTOR_APP_NONE,
                                               read_camera_entry, read_launch_section,
                                               read_par_app_entry, read_profile_cameras,
                                               RENDERING_MANAGER_APP_NAME,
                                               SENSOR_NODE_RESOURCE_TYPE)

PACKAGE_NAME = 'par_framework_core'
# The node switches of par_launch, each also a launch argument that overrides it for one run: one
# per installed sensor processing node (get_sensor_node_package_names, from the ament index) and
# these
NON_SENSOR_NODE_LAUNCH_SWITCH_NAMES = ('rviz',)
# Co-authored by Claude Code: per stream a camera may offer (its entry's streams), the parameter
# that makes a detector use it, and the detectors that have that parameter. A camera passing its
# own JPEGs through (image_raw/compressed) lets the detectors decode them themselves, so its
# driver only decodes for raw subscribers; depth on the colour grid adds the third dimension.
# Simplification: the detectors are listed here; upgrade: each sensor node's entry names the
# streams it can use
DETECTOR_PARAMETER_BY_CAMERA_STREAM = {
    'image_raw/compressed': ('use_compressed',
                             ('object_detector', 'fiducials_detector', 'page_locator')),
    'depth_registered/image_raw': ('use_depth',
                                   ('object_detector', 'fiducials_detector', 'hand_landmarks')),
}
# One RViz configuration for every camera. The camera topics its displays name are remapped onto
# the running camera: (name in the configuration, name relative to the camera's namespace)
RVIZ_CONFIG_FILE_NAME = 'par_framework.rviz'
RVIZ_CAMERA_TOPIC_NAMES = (('/camera/image_raw', 'image_raw'),
                           ('/camera/camera_info', 'camera_info'),
                           ('/points2', 'points2'))
# The rendering manager is a Rust program in the repo of its ROS bridge, built by cargo
# (scripts/local_build.sh)
RENDERING_MANAGER_BRIDGE_PACKAGE_NAME = 'rendering_manager_bridge'
RENDERING_MANAGER_BINARY_RELATIVE_PATH = os.path.join('target', 'release', 'rendering_manager')
# A fixed Wayland socket name, so the bridge knows the control socket
# $XDG_RUNTIME_DIR/<name>.control; a second rendering manager with this name fails to start
# instead of taking another socket the bridge would not find. Apps get <name>-<app id>. Snap apps
# (e.g. Chromium) may only open sockets named wayland-<digit>..., and the desktop's automatic
# names are wayland-0, wayland-1, ..., so the name starts with a number far above those
RENDERING_MANAGER_SOCKET_NAME = 'wayland-99-par-tabletop'


def get_rendering_manager_binary_path():
    """Return the rendering manager program's path, in the repo of its installed bridge."""
    # Simplification: follows the --symlink-install link of the bridge's package.xml back to its
    # repo, as local_build.sh builds it; upgrade: install the program with the bridge
    installed_package_xml_path = os.path.join(
        get_package_share_directory(RENDERING_MANAGER_BRIDGE_PACKAGE_NAME), 'package.xml')
    bridge_package_path = os.path.dirname(os.path.realpath(installed_package_xml_path))
    repo_path = os.path.dirname(bridge_package_path)
    return os.path.join(repo_path, RENDERING_MANAGER_BINARY_RELATIVE_PATH)


# Co-authored by Claude Code: the display comes from par_launch.projector_display_id
def create_rendering_manager_actions(params_file_paths, projector_display_id, camera_name):
    """Create the rendering manager, fullscreen on the projector, and its ROS bridge."""
    if not has_resource('packages', RENDERING_MANAGER_BRIDGE_PACKAGE_NAME):
        return [LogInfo(msg='[par.launch]: rendering_manager is not installed: add '
                            'ros2-par-framework-rendering-manager to config/nodes.list and run '
                            './scripts/local_build.sh')]
    binary_path = get_rendering_manager_binary_path()
    if not os.path.isfile(binary_path):
        return [LogInfo(msg=f'[par.launch]: {binary_path} is not built: run '
                            f'./scripts/local_build.sh (it builds the rendering manager with '
                            f'cargo)')]
    runtime_folder_path = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime_folder_path:
        raise RuntimeError('[par.launch]: XDG_RUNTIME_DIR is not set, so the rendering manager '
                           'has no place for its sockets: start the launch from a desktop '
                           'session terminal')

    rendering_manager_command = [binary_path, '--socket-name', RENDERING_MANAGER_SOCKET_NAME]
    # Without a display_id the desktop picks the display
    if projector_display_id is not None:
        rendering_manager_command += ['--display-id', str(projector_display_id)]
    control_socket_path = os.path.join(runtime_folder_path,
                                       f'{RENDERING_MANAGER_SOCKET_NAME}.control')
    bridge_parameters = list(params_file_paths)
    bridge_parameters.append({'control_socket_path': control_socket_path})
    return [
        ExecuteProcess(cmd=rendering_manager_command, name='rendering_manager', output='screen',
                       emulate_tty=True),
        # Starts together with the rendering manager and connects as soon as its socket exists
        Node(package=RENDERING_MANAGER_BRIDGE_PACKAGE_NAME,
             executable=RENDERING_MANAGER_BRIDGE_PACKAGE_NAME,
             name='rendering_manager_bridge_node',
             output='screen',
             emulate_tty=True,
             parameters=bridge_parameters,
             remappings=create_camera_stream_remappings(camera_name)),
    ]


# Written by Claude Code
def get_projector_app_name(context, launch_section):
    """Return the projector_app launch argument, else par_launch.projector_app (default none)."""
    projector_app_name = LaunchConfiguration('projector_app').perform(context)
    if not projector_app_name:
        projector_app_name = str(launch_section.get('projector_app', PROJECTOR_APP_NONE))
    return projector_app_name


# Written by Claude Code
def create_par_app_actions(context, app_package_name, par_app_entry, params_file_paths,
                           projector_display_id, debug_override, app_input_remappings):
    """Start a PAR app from its ament index entry: its executable as a node, or its launch file."""
    if par_app_entry['executable'] is not None:
        app_node_parameters = list(params_file_paths)
        # Convention for apps that draw on the projector: the display is their display_id
        if projector_display_id is not None:
            app_node_parameters.append({'display_id': projector_display_id})
        if debug_override is not None:
            app_node_parameters.append({'debug': debug_override})
        # No name: the node keeps the one it gives itself, which its parameter sections use
        return [Node(package=app_package_name,
                     executable=par_app_entry['executable'],
                     output='screen',
                     emulate_tty=True,
                     parameters=app_node_parameters,
                     remappings=app_input_remappings)]

    launch_file_path = os.path.join(get_package_share_directory(app_package_name), 'launch',
                                    par_app_entry['launch_file'])
    if not os.path.isfile(launch_file_path):
        raise RuntimeError(f'[par.launch]: the PAR app {app_package_name} names the launch file '
                           f'{launch_file_path}, which is not installed: install launch/ in its '
                           f'setup.py data_files (templates/par_app/) and run '
                           f'./scripts/local_build.sh')
    # The arguments every app launch file declares (templates/par_app/launch/)
    app_launch_arguments = {
        'params_file': LaunchConfiguration('params_file').perform(context),
        'profile': get_profile_name(context),
        'display_id': '' if projector_display_id is None else str(projector_display_id),
    }
    # The remappings reach every node the app's launch file starts
    app_input_remap_actions = []
    for app_topic_name, camera_topic_name in app_input_remappings:
        app_input_remap_actions.append(SetRemap(src=app_topic_name, dst=camera_topic_name))
    return [GroupAction([
        *app_input_remap_actions,
        IncludeLaunchDescription(PythonLaunchDescriptionSource(launch_file_path),
                                 launch_arguments=app_launch_arguments.items()),
    ])]


# Written by Claude Code
def create_app_input_remappings(app_inputs, camera_name_by_input):
    """
    Return the remappings that point an app's input topics at the cameras bound to its inputs.

    An app with one input reads plain names (pages -> /cameras/overhead/pages); an app with
    several prefixes each with its input (tracking/pages -> /cameras/overhead/pages).
    """
    is_single_input_app = len(app_inputs) == 1
    app_input_remappings = []
    for input_name, topic_names in app_inputs.items():
        camera_namespace = get_camera_namespace(camera_name_by_input[input_name])
        for topic_name in topic_names:
            app_topic_name = f'{input_name}/{topic_name}'
            if is_single_input_app:
                app_topic_name = topic_name
            app_input_remappings.append((app_topic_name, f'{camera_namespace}/{topic_name}'))
    return app_input_remappings


# Written by Claude Code
def create_uninstalled_switch_messages(launch_section, launch_switch_names, profile_camera_names):
    """Name every par_launch key that lists cameras but belongs to no installed sensor node."""
    uninstalled_switch_messages = []
    for switch_name, switch_value in launch_section.items():
        if switch_name in launch_switch_names or not isinstance(switch_value, list):
            continue
        # Other par_launch lists (e.g. apps) hold no camera names
        is_list_of_camera_names = bool(switch_value) and all(
            camera_name in profile_camera_names for camera_name in switch_value)
        if not is_list_of_camera_names:
            continue
        uninstalled_switch_messages.append(LogInfo(
            msg=f'[par.launch]: par_launch.{switch_name} lists cameras, but no installed package '
                f'registers {switch_name} as a sensor node (ament index '
                f'{SENSOR_NODE_RESOURCE_TYPE}): add its repo to config/nodes.list and run '
                f'./scripts/local_build.sh'))
    return uninstalled_switch_messages


# Written by Claude Code
def read_sensor_node_camera_names(launch_section, sensor_node_name, profile_camera_names):
    """Return the cameras par_launch.<sensor node> lists, checked against par_launch.cameras."""
    listed_camera_names = launch_section.get(sensor_node_name, [])
    is_list_of_texts = isinstance(listed_camera_names, list) and all(
        isinstance(camera_name, str) for camera_name in listed_camera_names)
    example_camera_name = 'overhead'
    if profile_camera_names:
        example_camera_name = profile_camera_names[0]
    if not is_list_of_texts:
        raise RuntimeError(f'[par.launch]: par_launch.{sensor_node_name}: '
                           f'{listed_camera_names!r}: list the cameras of par_launch.cameras it '
                           f'runs on, e.g. {sensor_node_name}: [{example_camera_name}], or [] for '
                           f'none')
    unknown_camera_names = []
    for camera_name in listed_camera_names:
        if camera_name not in profile_camera_names:
            unknown_camera_names.append(camera_name)
    if unknown_camera_names:
        raise RuntimeError(f'[par.launch]: par_launch.{sensor_node_name} names '
                           f'{unknown_camera_names}, which par_launch.cameras does not have; '
                           f'known: {profile_camera_names}')
    return listed_camera_names


# Written by Claude Code
def get_camera_names_by_sensor_node(context, launch_section, sensor_node_names,
                                    profile_camera_names, started_camera_names,
                                    app_camera_names_by_sensor_node):
    """
    Return, per sensor node, the started cameras it runs on, in the order of the started cameras.

    par_launch.<sensor node> lists them. The launch argument <sensor node>:=false turns every
    run off for one run, :=true runs the node on the only started camera. A sensor node the
    projector app requires also runs where app_camera_names_by_sensor_node says
    (get_par_app_sensor_node_camera_names).
    """
    camera_names_by_sensor_node = {}
    for sensor_node_name in sensor_node_names:
        argument_value = LaunchConfiguration(sensor_node_name).perform(context)
        if argument_value == '':
            listed_camera_names = read_sensor_node_camera_names(launch_section, sensor_node_name,
                                                                profile_camera_names)
        elif argument_value == 'false':
            listed_camera_names = []
        elif argument_value == 'true':
            if len(started_camera_names) > 1:
                raise RuntimeError(f'[par.launch]: {sensor_node_name}:=true runs the node on the '
                                   f'only camera, but this run starts {started_camera_names}: '
                                   f'list its cameras in par_launch.{sensor_node_name}, or start '
                                   f'one camera with camera:=<name>')
            listed_camera_names = list(started_camera_names)
        else:
            raise RuntimeError(f'[par.launch]: {sensor_node_name}:={argument_value}: use true or '
                               f'false, or leave it out to keep par_launch.{sensor_node_name} '
                               f'from the params_file')
        app_camera_names = app_camera_names_by_sensor_node.get(sensor_node_name, [])
        listed_camera_names = list(listed_camera_names) + app_camera_names
        # Cameras the profile lists but this run does not start (camera:=<name>) are left out
        camera_names = []
        for started_camera_name in started_camera_names:
            if started_camera_name in listed_camera_names:
                camera_names.append(started_camera_name)
        camera_names_by_sensor_node[sensor_node_name] = camera_names
    return camera_names_by_sensor_node


# Co-authored by Claude Code: starts every camera of the profile, the projector app and the
# sensor processing nodes registered in the ament index
def launch_setup(context):
    params_file_paths = get_params_file_paths(context)
    launch_section = read_launch_section(context)
    cameras_to_start = get_cameras_to_start(context)
    # Simplification: RViz and the rendering manager use the first camera. Upgrade: bind their
    # inputs to cameras as for a PAR app
    camera = cameras_to_start[0].camera_name
    # read_profile_cameras, not launch_section: the merged section would mix par_setup.yaml's
    # default cameras into the profile's. Empty when camera:=<type> runs without a camera list
    profile_camera_names = []
    if PAR_LAUNCH_CAMERAS_KEY in launch_section:
        for profile_camera in read_profile_cameras(context):
            profile_camera_names.append(profile_camera.camera_name)

    def read_true_false_argument(argument_name):
        """Return True or False from a true/false launch argument, None when it is left empty."""
        argument_value = LaunchConfiguration(argument_name).perform(context)
        if argument_value == '':
            return None
        if argument_value not in ('true', 'false'):
            raise RuntimeError(f'[par.launch]: {argument_name}:={argument_value}: use true or '
                               f'false, or leave it out to keep the value from the params_file')
        return argument_value == 'true'

    sensor_node_names = get_sensor_node_package_names()
    launch_switch_names = tuple(sensor_node_names) + NON_SENSOR_NODE_LAUNCH_SWITCH_NAMES
    # Read before the switches: the framework nodes a PAR app requires are switched on for it
    projector_app_name = get_projector_app_name(context, launch_section)
    # false: everything the app needs runs (its sensor nodes on its cameras), but not the app
    # itself, e.g. to tune those nodes in the setup wizard without the app taking the projector
    is_projector_app_started = (
        LaunchConfiguration('start_projector_app').perform(context) != 'false')
    # Only looked up when an app draws on it, so a run without one works with the projector off
    projector_display_id = None
    if projector_app_name != PROJECTOR_APP_NONE and is_projector_app_started:
        projector_display_id = get_projector_display_id(context, launch_section)
    par_app_entry = None
    required_launch_switch_names = []
    is_par_app = projector_app_name not in (PROJECTOR_APP_NONE, RENDERING_MANAGER_APP_NAME)
    if is_par_app:
        par_app_entry = read_par_app_entry(projector_app_name)
        required_launch_switch_names = par_app_entry['required_launch_switches']
        unknown_switch_names = sorted(set(required_launch_switch_names) - set(launch_switch_names))
        if unknown_switch_names:
            raise RuntimeError(f'[par.launch]: the PAR app {projector_app_name} requires unknown '
                               f'launch switches {unknown_switch_names}; known: '
                               f'{list(launch_switch_names)} (a sensor node is known once its '
                               f'package is installed)')

    def is_enabled(switch):
        """Return whether a true/false switch (rviz) is on."""
        # Simplification: the app's requirement wins over switch:=false. Upgrade: refuse the
        # combination with a message, if starting an app without its nodes turns out to be useful
        if switch in required_launch_switch_names:
            return True
        switch_value = read_true_false_argument(switch)
        if switch_value is None:
            return launch_section.get(switch, False)
        return switch_value

    launch_actions = []
    for camera_to_start in cameras_to_start:
        launch_actions += create_camera_actions(context, camera_to_start)
    if LaunchConfiguration('camera_only').perform(context) == 'true':
        return launch_actions
    if len(cameras_to_start) > 1:
        launch_actions.append(LogInfo(msg=f'[par.launch]: RViz and the rendering manager use the '
                                          f'main camera {camera} (the first of '
                                          f'par_launch.cameras)'))

    # Set for every framework node; nodes without a debug parameter ignore it
    debug_override = read_true_false_argument('debug')

    def create_framework_node(package, parameter_overrides=None):
        node_parameters = list(params_file_paths)
        if parameter_overrides:
            node_parameters.append(parameter_overrides)
        if debug_override is not None:
            node_parameters.append({'debug': debug_override})
        return Node(
            package=package,
            executable=package,
            name=f'{package}_node',
            output='screen',
            emulate_tty=True,
            parameters=node_parameters,
            remappings=create_camera_stream_remappings(camera),
        )

    def create_sensor_node(package, camera_name, parameter_overrides):
        """Create a sensor node in its camera's namespace; its sections are /cameras/*/<node>."""
        node_parameters = list(params_file_paths)
        node_parameters.append(parameter_overrides)
        if debug_override is not None:
            node_parameters.append({'debug': debug_override})
        return Node(
            package=package,
            executable=package,
            name=get_sensor_node_name(package),
            namespace=get_camera_namespace(camera_name),
            output='screen',
            emulate_tty=True,
            parameters=node_parameters,
        )

    # Each sensor node runs once per camera it is listed for, in the camera's namespace, where its
    # relative names resolve to that camera's streams and its outputs stay apart from another
    # camera's, e.g. /cameras/overhead/fiducials
    started_camera_names = []
    for camera_to_start in cameras_to_start:
        started_camera_names.append(camera_to_start.camera_name)
    app_input_remappings = []
    app_camera_names_by_sensor_node = {}
    if is_par_app:
        app_inputs = par_app_entry[PAR_APP_ENTRY_INPUTS_KEY]
        camera_name_by_input = get_app_input_camera_names(
            launch_section, projector_app_name, app_inputs, profile_camera_names,
            started_camera_names)
        app_input_remappings = create_app_input_remappings(app_inputs, camera_name_by_input)
        app_camera_names_by_sensor_node = get_par_app_sensor_node_camera_names(
            par_app_entry, camera_name_by_input, camera, sensor_node_names)
    camera_names_by_sensor_node = get_camera_names_by_sensor_node(
        context, launch_section, sensor_node_names, profile_camera_names, started_camera_names,
        app_camera_names_by_sensor_node)
    # A node that reads another one's output (required_sensor_nodes, e.g. page_locator reads
    # fiducials) starts that one along with it, on the same camera
    sensor_node_names_by_camera = get_sensor_node_names_by_camera(camera_names_by_sensor_node,
                                                                  started_camera_names)
    for camera_to_start in cameras_to_start:
        camera_stream_names = read_camera_entry(camera_to_start.camera_type)['streams']
        for sensor_node_name in sensor_node_names_by_camera[camera_to_start.camera_name]:
            sensor_node_overrides = {}
            for stream_name, (parameter_name, detector_names) in (
                    DETECTOR_PARAMETER_BY_CAMERA_STREAM.items()):
                if stream_name in camera_stream_names and sensor_node_name in detector_names:
                    sensor_node_overrides[parameter_name] = True
            launch_actions.append(create_sensor_node(sensor_node_name,
                                                     camera_to_start.camera_name,
                                                     sensor_node_overrides))
    launch_actions += create_uninstalled_switch_messages(launch_section, launch_switch_names,
                                                         profile_camera_names)

    # Publish each camera's stored projection corners and table-to-projector mapping. Calibration
    # is optional: without ros2-par-framework-calibration the framework runs in camera pixels.
    if has_resource('packages', 'projection_calibration_server'):
        for started_camera in cameras_to_start:
            launch_actions += create_projection_calibration_server_node(
                context, started_camera.camera_name)
    else:
        launch_actions.append(LogInfo(msg='[par.launch]: projection_calibration_server is not '
                                          'installed (ros2-par-framework-calibration): running '
                                          'without a projection calibration'))

    # One app owns the projector: a fullscreen window can only have one on top
    if not is_projector_app_started:
        launch_actions.append(LogInfo(msg=f'[par.launch]: start_projector_app:=false: '
                                          f'{projector_app_name} is not started, only what it '
                                          f'needs'))
    elif is_par_app:
        launch_actions += create_par_app_actions(context, projector_app_name, par_app_entry,
                                                 params_file_paths, projector_display_id,
                                                 debug_override, app_input_remappings)
    elif projector_app_name == RENDERING_MANAGER_APP_NAME:
        launch_actions += create_rendering_manager_actions(params_file_paths, projector_display_id,
                                                           camera)

    if is_enabled('rviz'):
        launch_actions.append(create_framework_node('rviz_bridge'))
        rviz_config_path = os.path.join(get_package_share_directory(PACKAGE_NAME), 'config',
                                        'rviz', RVIZ_CONFIG_FILE_NAME)
        rviz_remappings = []
        for configured_topic_name, camera_topic_name in RVIZ_CAMERA_TOPIC_NAMES:
            rviz_remappings.append((configured_topic_name,
                                    f'{get_camera_namespace(camera)}/{camera_topic_name}'))
        launch_actions.append(Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', rviz_config_path],
            remappings=rviz_remappings,
        ))
    return launch_actions


# Co-authored by Claude Code
def generate_launch_description():
    default_params_file_path = get_installed_par_setup_path()

    switch_arguments = []
    for sensor_node_name in get_sensor_node_package_names():
        switch_arguments.append(DeclareLaunchArgument(
            sensor_node_name,
            default_value='',
            description=f'false: no {sensor_node_name} in this run; true: run it on the only '
                        f'started camera. Empty runs it on the cameras par_launch.'
                        f'{sensor_node_name} lists in params_file.'))
    for switch in NON_SENSOR_NODE_LAUNCH_SWITCH_NAMES:
        switch_arguments.append(DeclareLaunchArgument(
            switch,
            default_value='',
            description=f'true or false: start {switch} or not. Empty uses '
                        f'par_launch.{switch} from params_file.'))

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params_file_path,
            description='Parameter file describing this physical PAR setup, with a par_launch '
                        'section.'),
        create_profile_launch_argument(),
        create_camera_choice_launch_argument(),
        DeclareLaunchArgument(
            'camera_only',
            default_value='false',
            description='true: start only the cameras and their mount transforms.'),
        *switch_arguments,
        DeclareLaunchArgument(
            'projector_app',
            default_value='',
            description=f'The app on the projector: {PROJECTOR_APP_NONE}, '
                        f'{RENDERING_MANAGER_APP_NAME} or the package of an installed PAR app '
                        f'(ament_index par_framework_apps). Empty uses par_launch.projector_app '
                        f'from params_file.'),
        DeclareLaunchArgument(
            'start_projector_app',
            default_value='true',
            description='false: start the sensor nodes the projector app requires, on the cameras '
                        'it reads, but not the app itself.'),
        create_projector_display_id_launch_argument(),
        DeclareLaunchArgument(
            'debug',
            default_value='',
            description='true or false: the debug parameter of every framework node started here '
                        '(debug windows and previews, needs a display). Empty keeps the values '
                        'from params_file.'),
        OpaqueFunction(function=launch_setup),
    ])
