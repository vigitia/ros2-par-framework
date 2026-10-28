# Written by Claude Code
"""
Measure the Azure Kinect's pose from the clear table and store it.

camera_pose_calibrator fits the table plane in the Kinect's registered depth and writes
config/calibration/extrinsics/camera_pose_kinect.yaml (with profile:=<name>, in extrinsics/<name>/
instead), which the Kinect launch files then use
instead of the placeholder /kinect_tf_publisher (height and tilt are measured, the rotation about
the vertical is kept from the placeholder). The launch ends when the calibrator is done. Keep the
table clear:

    ros2 launch par_framework_core camera_pose_calibration_kinect.launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (create_kinect_driver_node,
                                               create_profile_launch_argument,
                                               get_extrinsics_folder_path,
                                               get_path_in_config_folder, POSE_ROTATION_KEYS,
                                               read_merged_parameters)

PACKAGE_NAME = 'par_framework_core'


def launch_setup(context):
    merged_parameters = read_merged_parameters(context)
    placeholder_pose = merged_parameters['/kinect_tf_publisher']['ros__parameters']
    placeholder_rotation = [float(placeholder_pose[key]) for key in POSE_ROTATION_KEYS]
    extrinsics_folder_path = get_extrinsics_folder_path(context)
    camera_pose_relative_path = f'{extrinsics_folder_path}/camera_pose_kinect.yaml'
    camera_pose_file_path = get_path_in_config_folder(camera_pose_relative_path)
    return [
        create_kinect_driver_node(context),
        Node(
            package='camera_pose_calibrator',
            executable='camera_pose_calibrator',
            name='camera_pose_calibrator_node',
            output='screen',
            emulate_tty=True,
            parameters=[{
                'camera_pose_file': camera_pose_file_path,
                'base_frame': 'camera_base',
                'placeholder_rotation': placeholder_rotation,
            }],
            # The driver is remapped onto /camera/..., where the calibrator subscribes
            # Stored or failed: the camera is not needed any longer
            on_exit=Shutdown(reason='camera pose calibration finished'),
        ),
    ]


def generate_launch_description():
    default_params_file_path = os.path.join(
        get_package_share_directory(PACKAGE_NAME), 'config', 'par_setup.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params_file_path,
            description='Parameter file describing this physical PAR setup.'),
        create_profile_launch_argument(),
        OpaqueFunction(function=launch_setup),
    ])
