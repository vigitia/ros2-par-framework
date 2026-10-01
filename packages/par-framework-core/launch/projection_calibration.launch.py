# Written by Claude Code
r"""
Automatic table-to-projector calibration.

The projector shows ArUco markers at known projector pixels (display_id under
projection_calibrator_node in par_setup.yaml; the resolution is read from that display),
fiducials_detector finds them in the camera image, and projection_calibrator fits the homography
from the table plane to projector pixels. It is stored by projection_mapping_node in
config/projection_mapping_brio.yaml, next to par_setup.yaml (the Kinect has its own file), and
published latched on /projection_mapping. The launch ends when the calibrator is done.

Needs the camera calibration and the camera pose (/brio_tf_publisher in par_setup.yaml), and a
clear table. On the host, from the repo root:

    ros2 launch par_framework_core projection_calibration.launch.py \
        camera_info_url:="file://$PWD/src/logitech_brio/calibration/\${NAME}.yaml"
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (logitech_brio_node, mount_tf_publisher,
                                               projection_mapping_node)

PACKAGE_NAME = 'par_framework_core'


def generate_launch_description():
    default_params = os.path.join(
        get_package_share_directory(PACKAGE_NAME), 'config', 'par_setup.yaml')
    params_file = LaunchConfiguration('params_file')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Parameter file describing this physical PAR setup.'),
        DeclareLaunchArgument(
            'camera_info_url',
            default_value='',
            description='Overrides the Brio calibration URL from params_file, e.g. for a host '
                        'run: file://<repo>/src/logitech_brio/calibration/${NAME}.yaml. '
                        'Empty keeps the one from params_file.'),

        OpaqueFunction(function=logitech_brio_node),
        # The calibration converts camera pixels to the table plane, so the camera pose is needed
        OpaqueFunction(function=mount_tf_publisher, args=['brio_tf_publisher', 'brio_link']),
        Node(
            package='fiducials_detector',
            executable='fiducials_detector',
            name='fiducials_detector_node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file],
        ),
        OpaqueFunction(function=projection_mapping_node, args=['brio']),
        Node(
            package='surface_selector',
            executable='projection_calibrator',
            name='projection_calibrator_node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file],
            # Stored or failed: the camera and the projector are not needed any longer
            on_exit=Shutdown(reason='projection calibration finished'),
        ),
    ])
