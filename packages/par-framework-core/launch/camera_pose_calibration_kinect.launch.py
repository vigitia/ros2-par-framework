# Written by Claude Code
"""
Measure a depth camera's pose (e.g. the Azure Kinect's) from the clear table and store it.

camera_pose_calibrator fits the table plane in the camera's registered depth and writes
config/calibration/extrinsics/camera_pose_<camera>.yaml (with profile:=<name>, in
extrinsics/<name>/ instead), which the launch files then use instead of the placeholder
/<camera>_tf_publisher (height and tilt are measured, the rotation about the vertical is kept from
the placeholder). camera:= chooses the camera when the profile has several. The launch ends when
the calibrator is done. Keep the table clear:

    ros2 launch par_framework_core camera_pose_calibration_kinect.launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (create_camera_actions,
                                               create_camera_choice_launch_argument,
                                               create_camera_stream_remappings,
                                               create_profile_launch_argument,
                                               get_camera_body_frame_id,
                                               get_camera_to_calibrate,
                                               get_extrinsics_relative_path,
                                               get_path_in_config_folder, POSE_ROTATION_KEYS,
                                               read_camera_entry, read_merged_parameters)

PACKAGE_NAME = 'par_framework_core'
# The stream this launch measures: depth registered to the colour image
DEPTH_REGISTERED_STREAM_NAME = 'depth_registered/image_raw'


# Co-authored by Claude Code: the pose file is named after the camera, any depth camera
def launch_setup(context):
    camera_to_calibrate = get_camera_to_calibrate(context)
    camera = camera_to_calibrate.camera_name
    camera_entry = read_camera_entry(camera_to_calibrate.camera_type)
    if DEPTH_REGISTERED_STREAM_NAME not in camera_entry['streams']:
        raise RuntimeError(f'[camera_pose_calibration_kinect.launch]: the camera {camera} offers '
                           f'no {DEPTH_REGISTERED_STREAM_NAME}: measure its pose with '
                           f'camera_pose_calibration_sheet.launch.py instead')
    merged_parameters = read_merged_parameters(context)
    placeholder_pose = merged_parameters[f'/{camera}_tf_publisher']['ros__parameters']
    placeholder_rotation = [float(placeholder_pose[key]) for key in POSE_ROTATION_KEYS]
    camera_pose_relative_path = get_extrinsics_relative_path(context, 'camera_pose', camera)
    camera_pose_file_path = get_path_in_config_folder(camera_pose_relative_path)
    return [
        *create_camera_actions(context, camera_to_calibrate),
        Node(
            package='camera_pose_calibrator',
            executable='camera_pose_calibrator',
            name='camera_pose_calibrator_node',
            output='screen',
            emulate_tty=True,
            parameters=[{
                'camera_pose_file': camera_pose_file_path,
                'base_frame': get_camera_body_frame_id(camera, camera_entry),
                'placeholder_rotation': placeholder_rotation,
            }],
            # The camera publishes in /cameras/<camera>, where these remappings point the
            # calibrator's camera streams
            remappings=create_camera_stream_remappings(camera),
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
        create_camera_choice_launch_argument(),
        OpaqueFunction(function=launch_setup),
    ])
