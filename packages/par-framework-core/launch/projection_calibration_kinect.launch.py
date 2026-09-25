# Written by Claude Code
"""
Automatic table-to-projector calibration with the Azure Kinect instead of the Brio.

Same procedure as projection_calibration.launch.py: the projector shows ArUco markers,
fiducials_detector finds them in the Kinect's colour image, and projection_calibrator stores the
fitted homography through projection_mapping_node in config/projection_mapping_kinect.yaml (the
Brio has its own file). The launch ends when the calibrator is done.

Needs the Kinect's mount pose (/kinect_tf_publisher in par_setup.yaml) and a clear table. The
camera calibration comes from the Kinect itself.

    ros2 launch par_framework_core projection_calibration_kinect.launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (KINECT_REMAPPINGS, mount_tf_publisher,
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

        # No name override: the driver runs several rclcpp nodes in one process, and name= would
        # rename all of them
        Node(
            package='azure_kinect_ros_driver',
            executable='node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file],
        ),
        # The calibration converts camera pixels to the table plane, so the camera pose is needed
        OpaqueFunction(function=mount_tf_publisher, args=['kinect_tf_publisher', 'camera_base']),
        Node(
            package='fiducials_detector',
            executable='fiducials_detector',
            name='fiducials_detector_node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file],
            remappings=KINECT_REMAPPINGS,
        ),
        OpaqueFunction(function=projection_mapping_node, args=['kinect']),
        Node(
            package='surface_selector',
            executable='projection_calibrator',
            name='projection_calibrator_node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file],
            remappings=KINECT_REMAPPINGS,
            # Stored or failed: the camera and the projector are not needed any longer
            on_exit=Shutdown(reason='projection calibration finished'),
        ),
    ])
