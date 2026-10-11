# Written by Claude Code
"""
Bring up the PAR framework as the parameter file's par_launch section describes it.

The framework's one entry point for every camera. par_launch names the camera (brio, kinect or
webcam) and switches each node on or off; the setup wizard (par_setup_wizard) writes it. Without
the wizard:

    ros2 launch par_framework_core par.launch.py params_file:=/path/to/profiles/<profile>.yaml

Each of them can be overridden for one run, e.g. camera:=kinect rviz:=true hand_landmarks:=false;
an argument left empty keeps the profile's value. With the Kinect the detectors also use its
depth. camera_only:=true starts just the camera and its mount transform, e.g. for a preview or a
calibration. Camera calibrations are config/calibration/intrinsics/camera_info_<camera>.yaml,
shared by all profiles.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (CAMERA_IMAGE, camera_nodes, chosen_camera,
                                               projection_corners_node, projection_mapping_node,
                                               read_launch_section)

PACKAGE_NAME = 'par_framework_core'
# The node switches of par_launch, each also a launch argument that overrides it for one run
DETECTORS = ('object_detector', 'fiducials_detector', 'hand_landmarks', 'page_locator')
SWITCHES = DETECTORS + ('rviz',)
# Per camera: parameter overrides for each detector, and the RViz configuration. Every camera
# publishes on the same /camera/... topics (launch_helpers.DRIVER_REMAPPINGS); the overrides cover
# what the cameras offer differently.
CAMERA_OVERRIDES = {
    'kinect': {
        # Raw frames: the driver publishes no JPEGs
        'object_detector': {'topic_name_frame': CAMERA_IMAGE, 'use_depth': True},
        'fiducials_detector': {'use_depth': True},
        'hand_landmarks': {'use_depth': True},
    },
    # Raw frames: v4l2_camera publishes JPEGs only with compressed_image_transport installed
    'webcam': {'object_detector': {'topic_name_frame': CAMERA_IMAGE}},
}
RVIZ_CONFIGS = {'brio': 'par_framework_brio.rviz', 'kinect': 'par_framework_kinect.rviz',
                'webcam': 'par_framework_webcam.rviz'}


def launch_setup(context):
    params_file = LaunchConfiguration('params_file').perform(context)
    section = read_launch_section(context)
    camera = chosen_camera(context)

    def enabled(switch):
        value = LaunchConfiguration(switch).perform(context)
        if value not in ('', 'true', 'false'):
            raise RuntimeError(f'[par.launch]: {switch}:={value}: use true or false, or leave it '
                               f'out to keep par_launch.{switch} from the params_file')
        return section.get(switch, False) if value == '' else value == 'true'

    actions = camera_nodes(context, camera)
    if LaunchConfiguration('camera_only').perform(context) == 'true':
        return actions

    def framework_node(package, overrides=None):
        return Node(
            package=package,
            executable=package,
            name=f'{package}_node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file] + ([overrides] if overrides else []),
        )

    # page_locator only reads /fiducials, so it needs fiducials_detector but no camera overrides
    for detector in DETECTORS:
        if enabled(detector):
            overrides = CAMERA_OVERRIDES.get(camera, {}).get(detector)
            actions.append(framework_node(detector, overrides))

    # Publish the stored projection corners and table-to-projector mapping
    actions += projection_corners_node(camera)
    actions += projection_mapping_node(camera)

    if enabled('rviz'):
        actions.append(framework_node('rviz_bridge'))
        actions.append(Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', os.path.join(get_package_share_directory(PACKAGE_NAME), 'config',
                                          'rviz', RVIZ_CONFIGS[camera])],
        ))
    return actions


def generate_launch_description():
    default_params = os.path.join(
        get_package_share_directory(PACKAGE_NAME), 'config', 'par_setup.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Parameter file describing this physical PAR setup, with a par_launch '
                        'section.'),
        DeclareLaunchArgument(
            'camera',
            default_value='',
            description='brio, kinect or webcam. Empty uses par_launch.camera from params_file.'),
        DeclareLaunchArgument(
            'camera_only',
            default_value='false',
            description='true: start only the camera and its mount transform.'),
        *[DeclareLaunchArgument(
            switch,
            default_value='',
            description=f'true or false: start {switch} or not. Empty uses '
                        f'par_launch.{switch} from params_file.') for switch in SWITCHES],
        OpaqueFunction(function=launch_setup),
    ])
