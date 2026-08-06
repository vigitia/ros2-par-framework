"""Calibration run: camera plus the surface selector.

Start this once per physical setup to mark the projection area in the camera
image; the resulting corners are what the rest of the framework warps against.
The projector window opens on the display given by `display_id` in the
parameter file.
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

        Node(
            package='surface_selector',
            executable='surface_selector',
            name='surface_selector_node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file],
        ),
    ])
