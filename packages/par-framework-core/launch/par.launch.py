# Written by Claude Code
"""
Bring up the PAR framework as the parameter file's par_launch section describes it.

The framework's one entry point for every camera. par_launch names the camera (brio, kinect,
realsense or webcam) and switches each node on or off. With another parameter file:

    ros2 launch par_framework_core par.launch.py params_file:=/path/to/<file>.yaml

Each of them can be overridden for one run, e.g. camera:=kinect rviz:=true hand_landmarks:=false;
an argument left empty keeps the parameter file's value. With a depth camera (kinect, realsense)
the detectors also use its depth. camera_only:=true starts just the camera and its mount transform,
e.g. for a preview or a calibration. Camera calibrations are
config/calibration/intrinsics/camera_info_<camera>.yaml, shared by all parameter files.
"""

import os

from ament_index_python.packages import get_package_share_directory
from ament_index_python.resources import has_resource
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (create_camera_nodes,
                                               create_projection_calibration_server_node,
                                               get_chosen_camera, read_launch_section)

PACKAGE_NAME = 'par_framework_core'
# The node switches of par_launch, each also a launch argument that overrides it for one run
DETECTORS = ('object_detector', 'fiducials_detector', 'hand_landmarks', 'page_locator',
             'gesture_detector')
LAUNCH_SWITCHES = DETECTORS + ('projection_mask', 'demo_app', 'rviz')
# Per camera: parameter overrides for each detector, and the RViz configuration. Every camera
# publishes on the same /camera/... topics (launch_helpers.CAMERA_DRIVER_REMAPPINGS); the overrides
# cover what the cameras offer differently.
DEPTH_CAMERA_OVERRIDES = {
    'object_detector': {'use_depth': True},
    'fiducials_detector': {'use_depth': True},
    'hand_landmarks': {'use_depth': True},
}
CAMERA_OVERRIDES = {
    # The Brio's driver passes the camera's own JPEGs through on /camera/image_raw/compressed:
    # object_detector decodes them itself, so the driver only decodes for raw subscribers
    'brio': {'object_detector': {'use_compressed': True}},
    'kinect': DEPTH_CAMERA_OVERRIDES,
    'realsense': DEPTH_CAMERA_OVERRIDES,
}
RVIZ_CONFIG_FILE_NAMES = {'brio': 'par_framework_brio.rviz',
                          'kinect': 'par_framework_kinect.rviz',
                          'realsense': 'par_framework_realsense.rviz',
                          'webcam': 'par_framework_webcam.rviz'}


def launch_setup(context):
    params_file_path = LaunchConfiguration('params_file').perform(context)
    launch_section = read_launch_section(context)
    camera = get_chosen_camera(context)

    def is_enabled(switch):
        switch_value = LaunchConfiguration(switch).perform(context)
        if switch_value not in ('', 'true', 'false'):
            raise RuntimeError(f'[par.launch]: {switch}:={switch_value}: use true or false, or '
                               f'leave it out to keep par_launch.{switch} from the params_file')
        if switch_value == '':
            return launch_section.get(switch, False)
        return switch_value == 'true'

    launch_actions = create_camera_nodes(context, camera)
    if LaunchConfiguration('camera_only').perform(context) == 'true':
        return launch_actions

    def create_framework_node(package, parameter_overrides=None):
        node_parameters = [params_file_path]
        if parameter_overrides:
            node_parameters.append(parameter_overrides)
        return Node(
            package=package,
            executable=package,
            name=f'{package}_node',
            output='screen',
            emulate_tty=True,
            parameters=node_parameters,
        )

    # page_locator only reads /fiducials and gesture_detector only /hand_landmarks, so they need
    # fiducials_detector and hand_landmarks but no camera overrides
    for detector in DETECTORS:
        if is_enabled(detector):
            camera_overrides = CAMERA_OVERRIDES.get(camera, {})
            detector_overrides = camera_overrides.get(detector)
            launch_actions.append(create_framework_node(detector, detector_overrides))

    # Publish the stored projection corners and table-to-projector mapping. Calibration is
    # optional: without ros2-par-framework-calibration the framework runs in camera pixels.
    if has_resource('packages', 'projection_calibration_server'):
        launch_actions += create_projection_calibration_server_node(camera)
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

    if is_enabled('rviz'):
        launch_actions.append(create_framework_node('rviz_bridge'))
        rviz_config_path = os.path.join(get_package_share_directory(PACKAGE_NAME), 'config',
                                        'rviz', RVIZ_CONFIG_FILE_NAMES[camera])
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
        DeclareLaunchArgument(
            'camera',
            default_value='',
            description='brio, kinect, realsense or webcam. Empty uses par_launch.camera from '
                        'params_file.'),
        DeclareLaunchArgument(
            'camera_only',
            default_value='false',
            description='true: start only the camera and its mount transform.'),
        *switch_arguments,
        OpaqueFunction(function=launch_setup),
    ])
