# Written by Claude Code
"""
Bring up the PAR framework as the parameter file's par_launch section describes it.

The framework's one entry point for every camera. par_launch names the camera (brio, kinect,
realsense, webcam, blackfly, cu40 or event) and switches each node on or off. With another
parameter file:

    ros2 launch par_framework_core par.launch.py params_file:=/path/to/<file>.yaml

profile:=<name> adds config/profiles/<name>.yaml on top of it: only what differs for another
physical setup, which also gets its own camera pose and projection calibration in
config/calibration/extrinsics/<name>/.

Each of them can be overridden for one run, e.g. camera:=kinect rviz:=true hand_landmarks:=false;
an argument left empty keeps the parameter file's value. With a depth camera (kinect, realsense)
the detectors also use its depth. camera_only:=true starts just the camera and its mount transform,
e.g. for a preview or a calibration. An event camera (event) delivers its events collected into
images, and the raw events on /camera/events; it has no calibration. Camera calibrations are
config/calibration/intrinsics/<profile>/camera_info_<camera>.yaml (a Brio or Blackfly with its
serial set: camera_info_<camera>_<serial>.yaml), each profile's own; without profile:= the shared
config/calibration/intrinsics/ folder.

debug:=true turns on the debug windows of every started node that has one, e.g. for testing
gestures: camera:=kinect hand_landmarks:=true gesture_detector:=true debug:=true.

par_launch.projector_app (or projector_app:=<name>) chooses the one app that owns the projector,
on par_launch.projector_display_id: none, an installed PAR app (a package registered in the ament
index under par_framework_apps, see templates/par_app/; the framework nodes it requires are
started too), or rendering_manager, the Wayland compositor whose ROS bridge shows one app on every
detected page.

capture_camera:=true also starts a second Blackfly S as /capture_camera/blackfly in software
trigger mode, for single high-resolution frames on request (see /capture_camera/blackfly in
par_setup.yaml); it needs its serial_number there or in the profile.
"""

import os

from ament_index_python.packages import get_package_share_directory
from ament_index_python.resources import has_resource
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription,
                            LogInfo, OpaqueFunction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (add_required_sensor_nodes, create_camera_nodes,
                                               create_capture_camera_node,
                                               create_profile_launch_argument,
                                               create_projection_calibration_server_node,
                                               create_projector_display_id_launch_argument,
                                               get_chosen_camera, get_params_file_paths,
                                               get_profile_name, get_projector_display_id,
                                               get_sensor_node_package_names,
                                               PROJECTOR_APP_NONE,
                                               read_launch_section, read_par_app_entry,
                                               RENDERING_MANAGER_APP_NAME,
                                               SENSOR_NODE_RESOURCE_TYPE)

PACKAGE_NAME = 'par_framework_core'
# The node switches of par_launch, each also a launch argument that overrides it for one run: one
# per installed sensor processing node (get_sensor_node_package_names, from the ament index) and
# these
NON_SENSOR_NODE_LAUNCH_SWITCH_NAMES = ('rviz', 'capture_camera')
# Per camera: parameter overrides for each detector. Every camera
# publishes on the same /camera/... topics (launch_helpers.CAMERA_DRIVER_REMAPPINGS); the overrides
# cover what the cameras offer differently.
DEPTH_CAMERA_OVERRIDES = {
    'object_detector': {'use_depth': True},
    'fiducials_detector': {'use_depth': True},
    'hand_landmarks': {'use_depth': True},
}
CAMERA_DETECTOR_PARAMETER_OVERRIDES = {
    # The Brio's driver passes the camera's own JPEGs through on /camera/image_raw/compressed:
    # object_detector, fiducials_detector and page_locator's debug preview decode them
    # themselves, so the driver only decodes for raw subscribers
    'brio': {'object_detector': {'use_compressed': True},
             'fiducials_detector': {'use_compressed': True},
             'page_locator': {'use_compressed': True}},
    'kinect': DEPTH_CAMERA_OVERRIDES,
    'realsense': DEPTH_CAMERA_OVERRIDES,
}
# One RViz configuration for every camera, since they all publish on the same topics
RVIZ_CONFIG_FILE_NAME = 'par_framework.rviz'
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
def create_rendering_manager_actions(params_file_paths, projector_display_id):
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
             parameters=bridge_parameters),
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
                           projector_display_id, debug_override):
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
                     parameters=app_node_parameters)]

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
    return [IncludeLaunchDescription(PythonLaunchDescriptionSource(launch_file_path),
                                     launch_arguments=app_launch_arguments.items())]


# Written by Claude Code
def create_uninstalled_switch_messages(launch_section, launch_switch_names):
    """Name every par_launch switch that is true but belongs to no installed sensor node."""
    uninstalled_switch_messages = []
    for switch_name, switch_value in launch_section.items():
        if switch_value is not True or switch_name in launch_switch_names:
            continue
        uninstalled_switch_messages.append(LogInfo(
            msg=f'[par.launch]: par_launch.{switch_name} is true, but no installed package '
                f'registers {switch_name} as a sensor node (ament index '
                f'{SENSOR_NODE_RESOURCE_TYPE}): add its repo to config/nodes.list and run '
                f'./scripts/local_build.sh'))
    return uninstalled_switch_messages


# Co-authored by Claude Code: starts the capture camera, the projector app and the sensor
# processing nodes registered in the ament index
def launch_setup(context):
    params_file_paths = get_params_file_paths(context)
    launch_section = read_launch_section(context)
    camera = get_chosen_camera(context)

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
    # Only looked up when an app draws on it, so a run without one works with the projector off
    projector_display_id = None
    if projector_app_name != PROJECTOR_APP_NONE:
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
        # Simplification: the app's requirement wins over switch:=false. Upgrade: refuse the
        # combination with a message, if starting an app without its nodes turns out to be useful
        if switch in required_launch_switch_names:
            return True
        switch_value = read_true_false_argument(switch)
        if switch_value is None:
            return launch_section.get(switch, False)
        return switch_value

    launch_actions = create_camera_nodes(context, camera)
    if LaunchConfiguration('camera_only').perform(context) == 'true':
        return launch_actions

    # A second camera next to the main one, for single high-resolution frames on request
    if is_enabled('capture_camera'):
        launch_actions.append(create_capture_camera_node(context))

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
        )

    # A node that reads another one's output (required_sensor_nodes, e.g. page_locator reads
    # /fiducials) starts that one along with it
    switched_on_sensor_node_names = []
    for sensor_node_name in sensor_node_names:
        if is_enabled(sensor_node_name):
            switched_on_sensor_node_names.append(sensor_node_name)
    for sensor_node_name in add_required_sensor_nodes(switched_on_sensor_node_names):
        camera_overrides = CAMERA_DETECTOR_PARAMETER_OVERRIDES.get(camera, {})
        sensor_node_overrides = camera_overrides.get(sensor_node_name)
        launch_actions.append(create_framework_node(sensor_node_name, sensor_node_overrides))
    launch_actions += create_uninstalled_switch_messages(launch_section, launch_switch_names)

    # Publish the stored projection corners and table-to-projector mapping. Calibration is
    # optional: without ros2-par-framework-calibration the framework runs in camera pixels.
    if has_resource('packages', 'projection_calibration_server'):
        launch_actions += create_projection_calibration_server_node(context, camera)
    else:
        launch_actions.append(LogInfo(msg='[par.launch]: projection_calibration_server is not '
                                          'installed (ros2-par-framework-calibration): running '
                                          'without a projection calibration'))

    # One app owns the projector: a fullscreen window can only have one on top
    if is_par_app:
        launch_actions += create_par_app_actions(context, projector_app_name, par_app_entry,
                                                 params_file_paths, projector_display_id,
                                                 debug_override)
    elif projector_app_name == RENDERING_MANAGER_APP_NAME:
        launch_actions += create_rendering_manager_actions(params_file_paths, projector_display_id)

    if is_enabled('rviz'):
        launch_actions.append(create_framework_node('rviz_bridge'))
        rviz_config_path = os.path.join(get_package_share_directory(PACKAGE_NAME), 'config',
                                        'rviz', RVIZ_CONFIG_FILE_NAME)
        launch_actions.append(Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', rviz_config_path],
        ))
    return launch_actions


def generate_launch_description():
    default_params_file_path = os.path.join(
        get_package_share_directory(PACKAGE_NAME), 'config', 'par_setup.yaml')

    switch_arguments = []
    for switch in tuple(get_sensor_node_package_names()) + NON_SENSOR_NODE_LAUNCH_SWITCH_NAMES:
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
        DeclareLaunchArgument(
            'camera',
            default_value='',
            description='brio, kinect, realsense, webcam, blackfly, cu40 or event. Empty uses '
                        'par_launch.camera from params_file.'),
        DeclareLaunchArgument(
            'camera_only',
            default_value='false',
            description='true: start only the camera and its mount transform.'),
        *switch_arguments,
        DeclareLaunchArgument(
            'projector_app',
            default_value='',
            description=f'The app on the projector: {PROJECTOR_APP_NONE}, '
                        f'{RENDERING_MANAGER_APP_NAME} or the package of an installed PAR app '
                        f'(ament_index par_framework_apps). Empty uses par_launch.projector_app '
                        f'from params_file.'),
        create_projector_display_id_launch_argument(),
        DeclareLaunchArgument(
            'debug',
            default_value='',
            description='true or false: the debug parameter of every framework node started here '
                        '(debug windows and previews, needs a display). Empty keeps the values '
                        'from params_file.'),
        OpaqueFunction(function=launch_setup),
    ])
