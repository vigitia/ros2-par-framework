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
config/calibration/intrinsics/camera_info_<camera>.yaml (a Brio or Blackfly with its serial set:
camera_info_<camera>_<serial>.yaml), shared by all parameter files and profiles.

debug:=true turns on the debug windows of every started node that has one, e.g. for testing
gestures: camera:=kinect hand_landmarks:=true gesture_detector:=true debug:=true.

rendering_manager:=true starts the rendering manager (a Wayland compositor) fullscreen on the
projector and its ROS bridge, which shows one app on every detected page.

capture_camera:=true also starts a second Blackfly S as /capture_camera/blackfly in software
trigger mode, for single high-resolution frames on request (see /capture_camera/blackfly in
par_setup.yaml); it needs its serial_number there or in the profile.
"""

import os

from ament_index_python.packages import get_package_share_directory
from ament_index_python.resources import has_resource
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (create_camera_nodes, create_capture_camera_node,
                                               create_profile_launch_argument,
                                               create_projection_calibration_server_node,
                                               get_chosen_camera, get_params_file_paths,
                                               read_launch_section, read_merged_parameters)

PACKAGE_NAME = 'par_framework_core'
# The node switches of par_launch, each also a launch argument that overrides it for one run
DETECTORS = ('object_detector', 'fiducials_detector', 'hand_landmarks', 'page_locator',
             'gesture_detector')
LAUNCH_SWITCHES = DETECTORS + ('projection_mask', 'demo_app', 'rendering_manager', 'rviz',
                               'capture_camera')
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
# Its section in the parameter files, read here: the program is no ROS node
RENDERING_MANAGER_PARAMETERS_KEY = 'rendering_manager'
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


def create_rendering_manager_actions(context, params_file_paths):
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
    rendering_manager_section = read_merged_parameters(context).get(
        RENDERING_MANAGER_PARAMETERS_KEY, {})
    rendering_manager_parameters = rendering_manager_section.get('ros__parameters', {})
    display_id = rendering_manager_parameters.get('display_id')
    # Without a display_id the desktop picks the display
    if display_id is not None:
        rendering_manager_command += ['--display-id', str(display_id)]
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


# Co-authored by Claude Code: starts the capture camera
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

    def is_enabled(switch):
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

    # page_locator reads /fiducials and gesture_detector /hand_landmarks, so they need
    # fiducials_detector and hand_landmarks; page_locator reads frames only for its debug preview
    for detector in DETECTORS:
        if is_enabled(detector):
            camera_overrides = CAMERA_DETECTOR_PARAMETER_OVERRIDES.get(camera, {})
            detector_overrides = camera_overrides.get(detector)
            launch_actions.append(create_framework_node(detector, detector_overrides))

    # Publish the stored projection corners and table-to-projector mapping. Calibration is
    # optional: without ros2-par-framework-calibration the framework runs in camera pixels.
    if has_resource('packages', 'projection_calibration_server'):
        launch_actions += create_projection_calibration_server_node(context, camera)
    else:
        launch_actions.append(LogInfo(msg='[par.launch]: projection_calibration_server is not '
                                          'installed (ros2-par-framework-calibration): running '
                                          'without a projection calibration'))

    # The mask is optional too, and its own repo: start it only when that is installed
    if is_enabled('projection_mask'):
        if has_resource('packages', 'projection_mask'):
            launch_actions.append(create_framework_node('projection_mask'))
        else:
            launch_actions.append(LogInfo(msg='[par.launch]: projection_mask is not installed: '
                                              'add ros2-par-framework-projection-mask to '
                                              'config/nodes.list and run '
                                              './scripts/local_build.sh'))

    # The demo application is its own repo as well
    if is_enabled('demo_app'):
        if has_resource('packages', 'demo_app'):
            launch_actions.append(create_framework_node('demo_app'))
        else:
            launch_actions.append(LogInfo(msg='[par.launch]: demo_app is not installed: add '
                                              'ros2-par-framework-demo-application to '
                                              'config/nodes.list and run '
                                              './scripts/local_build.sh'))

    if is_enabled('rendering_manager'):
        # Both open a fullscreen window on the projector, and only one can be on top
        if is_enabled('demo_app'):
            launch_actions.append(LogInfo(msg='[par.launch]: demo_app and rendering_manager both '
                                              'draw on the projector; start only one of them, '
                                              'e.g. demo_app:=false'))
        launch_actions += create_rendering_manager_actions(context, params_file_paths)

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
    for switch in LAUNCH_SWITCHES:
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
            'debug',
            default_value='',
            description='true or false: the debug parameter of every framework node started here '
                        '(debug windows and previews, needs a display). Empty keeps the values '
                        'from params_file.'),
        OpaqueFunction(function=launch_setup),
    ])
