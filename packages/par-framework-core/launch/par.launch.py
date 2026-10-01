# Written by Claude Code
"""
Bring up the PAR framework as the parameter file's par_launch section describes it.

par_launch names the camera (brio, kinect or webcam) and switches each node on or off; the setup
wizard (par_setup_wizard) writes it. Without the wizard:

    ros2 launch par_framework_core par.launch.py params_file:=/path/to/par_setup_<profile>.yaml

With the Kinect the detectors get its topics and its depth, as in par_framework_kinect.launch.py.
camera_only:=true starts just the camera and its mount transform, e.g. for a preview or a
calibration. On the host, the Brio calibration needs camera_info_url, see par_framework.launch.py.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (camera_nodes, CAMERA_REMAPPINGS,
                                               projection_corners_node, projection_mapping_node,
                                               read_launch_section)

PACKAGE_NAME = 'par_framework_core'
# Per camera: parameter overrides for each detector, and the RViz configuration
CAMERA_OVERRIDES = {
    'kinect': {
        # Raw frames: the driver publishes no JPEGs
        'object_detector': {'topic_name_frame': '/rgb/image_raw', 'use_depth': True},
        'fiducials_detector': {'use_depth': True},
        'hand_landmarks': {'use_depth': True},
    },
    # Raw frames: v4l2_camera publishes JPEGs only with compressed_image_transport installed
    'webcam': {'object_detector': {'topic_name_frame': '/camera/webcam/image_raw'}},
}
RVIZ_CONFIGS = {'brio': 'par_framework.rviz', 'kinect': 'par_framework_kinect.rviz',
                'webcam': 'par_framework_webcam.rviz'}


def launch_setup(context):
    params_file = LaunchConfiguration('params_file').perform(context)
    section = read_launch_section(context)
    camera = section['camera']
    actions = camera_nodes(context, camera)
    if LaunchConfiguration('camera_only').perform(context) == 'true':
        return actions

    # The detectors default to the Brio's topics
    remappings = CAMERA_REMAPPINGS[camera]

    def framework_node(package, overrides=None):
        return Node(
            package=package,
            executable=package,
            name=f'{package}_node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file] + ([overrides] if overrides else []),
            remappings=remappings,
        )

    # page_locator only reads /fiducials, so it needs fiducials_detector but no camera overrides
    for detector in ('object_detector', 'fiducials_detector', 'hand_landmarks', 'page_locator'):
        if section.get(detector, False):
            overrides = CAMERA_OVERRIDES.get(camera, {}).get(detector)
            actions.append(framework_node(detector, overrides))

    # Publish the stored projection corners and table-to-projector mapping
    actions += projection_corners_node(context)
    actions += projection_mapping_node(context, camera)

    if section.get('rviz', False):
        actions.append(framework_node('rviz_bridge'))
        actions.append(Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', os.path.join(get_package_share_directory(PACKAGE_NAME), 'config',
                                          RVIZ_CONFIGS[camera])],
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
            'camera_info_url',
            default_value='',
            description='Overrides the Brio calibration URL from params_file, e.g. for a host '
                        'run: file://<repo>/src/logitech_brio/calibration/${NAME}.yaml. '
                        'Empty keeps the one from params_file.'),
        DeclareLaunchArgument(
            'camera_only',
            default_value='false',
            description='true: start only the camera and its mount transform.'),
        OpaqueFunction(function=launch_setup),
    ])
