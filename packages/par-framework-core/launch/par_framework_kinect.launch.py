# Written by Claude Code
"""
Bring up the PAR framework with the Azure Kinect instead of the Brio.

Starts the Azure Kinect driver, its mount transform, the object detector, the fiducials detector,
hand landmarks, the projection owners, rviz_bridge and RViz, which also shows the Kinect's depth
point cloud. The driver's settings and its mount pose are k4a_ros_device_node and
/kinect_tf_publisher in par_setup.yaml:

    ros2 launch par_framework_core par_framework_kinect.launch.py

The Kinect ships with a factory calibration in its camera_info, so no camera calibration is needed.
The framework nodes are pointed at the Kinect's topics by remapping (KINECT_REMAPPINGS in
launch_helpers.py).
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (KINECT_REMAPPINGS, mount_tf_publisher,
                                               projection_corners_node,
                                               projection_mapping_node)

PACKAGE_NAME = 'par_framework_core'


def generate_launch_description():
    default_params = os.path.join(
        get_package_share_directory(PACKAGE_NAME), 'config', 'par_setup.yaml')
    params_file = LaunchConfiguration('params_file')

    def framework_node(package, name, *overrides):
        return Node(
            package=package,
            executable=package,
            name=name,
            output='screen',
            emulate_tty=True,
            parameters=[params_file, *overrides],
            remappings=KINECT_REMAPPINGS,
        )

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
        # Where the Kinect is mounted: world -> camera_base. The driver itself publishes
        # camera_base -> depth_camera_link -> rgb_camera_link.
        OpaqueFunction(function=mount_tf_publisher, args=['kinect_tf_publisher', 'camera_base']),

        # Raw frames: the driver publishes no JPEGs, and compressing 1080p at 30 fps only for the
        # detector to decode it again would cost CPU, latency and image quality
        framework_node('object_detector', 'object_detector_node',
                       {'topic_name_frame': '/rgb/image_raw'}),
        framework_node('fiducials_detector', 'fiducials_detector_node'),
        framework_node('hand_landmarks', 'hand_landmarks_node'),

        # Publish the stored projection corners and table-to-projector mapping
        OpaqueFunction(function=projection_corners_node),
        OpaqueFunction(function=projection_mapping_node, args=['kinect']),

        framework_node('rviz_bridge', 'rviz_bridge_node'),
        Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', os.path.join(
                get_package_share_directory(PACKAGE_NAME), 'config', 'par_framework_kinect.rviz')],
        ),
    ])
