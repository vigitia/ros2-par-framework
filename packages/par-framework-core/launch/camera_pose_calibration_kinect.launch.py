# Written by Claude Code
"""
Measure the Azure Kinect's pose from the clear table and store it.

camera_pose_calibrator fits the table plane in the Kinect's registered depth and writes
config/camera_pose_kinect.yaml next to par_setup.yaml, which the Kinect launch files then use
instead of the placeholder /kinect_tf_publisher (height and tilt are measured, the rotation about
the vertical is kept from the placeholder). The launch ends when the calibrator is done. Keep the
table clear:

    ros2 launch par_framework_core camera_pose_calibration_kinect.launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import kinect_driver_node, next_to_params_file
import yaml

PACKAGE_NAME = 'par_framework_core'


def launch_setup(context):
    with open(LaunchConfiguration('params_file').perform(context)) as f:
        placeholder = yaml.safe_load(f)['/kinect_tf_publisher']['ros__parameters']
    return [
        kinect_driver_node(context),
        Node(
            package='camera_pose_calibrator',
            executable='camera_pose_calibrator',
            name='camera_pose_calibrator_node',
            output='screen',
            emulate_tty=True,
            parameters=[{
                'camera_pose_file': next_to_params_file(context, 'camera_pose_kinect.yaml'),
                'base_frame': 'camera_base',
                'placeholder_rotation': [float(placeholder[f'rotation.{axis}'])
                                         for axis in 'xyzw'],
            }],
            # The driver is remapped onto /camera/..., where the calibrator subscribes
            # Stored or failed: the camera is not needed any longer
            on_exit=Shutdown(reason='camera pose calibration finished'),
        ),
    ]


def generate_launch_description():
    default_params = os.path.join(
        get_package_share_directory(PACKAGE_NAME), 'config', 'par_setup.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Parameter file describing this physical PAR setup.'),
        OpaqueFunction(function=launch_setup),
    ])
