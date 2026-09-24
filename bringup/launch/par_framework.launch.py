"""Bring up the PAR framework: camera source plus the processing pipeline.

Every node reads its parameters from config/par_setup.yaml, so a different
physical setup means a different parameter file, not different code:

    ros2 launch par_framework_bringup par_framework.launch.py \\
        params_file:=/path/to/other_setup.yaml
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PACKAGE_NAME = 'par_framework_bringup'


def generate_launch_description():
    default_params = os.path.join(
        get_package_share_directory(PACKAGE_NAME), 'config', 'par_setup.yaml')

    params_file = LaunchConfiguration('params_file')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Parameter file describing this physical PAR setup.'),

        Node(
            package='logitech_brio',
            executable='logitech_brio',
            name='logitech_brio_node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file],
        ),

        # Co-authored by Claude Code
        # Where the Brio is mounted: world -> brio_link, pose from params_file. The node itself
        # publishes brio_link -> brio_optical_frame. Frame names must match the Brio node.
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='brio_tf_publisher',
            parameters=[params_file, {'frame_id': 'world', 'child_frame_id': 'brio_link'}],
        ),
    ])
