# Written by Claude Code
"""
Measure a camera's pose from a checkerboard on the table and store it.

Starts the camera (camera:= among several) and sheet_pose_calibrator, which fits the
plane of a checkerboard lying flat on the table and writes
config/calibration/extrinsics/camera_pose_<camera>.yaml (with profile:=<name>, in
extrinsics/<name>/ instead). The launch files then use it instead of the placeholder
/<camera>_tf_publisher: height and tilt are measured, the rotation about the vertical and the
position along the table are kept from the placeholder, so the board may lie anywhere in view and
turned any way. For cameras without depth; needs the camera's intrinsics. Stop other launches
using the camera first. The launch ends when the calibrator is done:

    ros2 launch par_framework_core camera_pose_calibration_sheet.launch.py profile:=office-all \
        square_size_mm:=19.2 board_columns:=11 board_rows:=7
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
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


# Co-authored by Claude Code: the pose file is per camera name
def launch_setup(context):
    camera_to_calibrate = get_camera_to_calibrate(context)
    camera = camera_to_calibrate.camera_name
    merged_parameters = read_merged_parameters(context)
    placeholder_pose = merged_parameters[f'/{camera}_tf_publisher']['ros__parameters']
    placeholder_rotation = [float(placeholder_pose[key]) for key in POSE_ROTATION_KEYS]
    camera_pose_relative_path = get_extrinsics_relative_path(context, 'camera_pose', camera)
    camera_pose_file_path = get_path_in_config_folder(camera_pose_relative_path)
    square_size_mm = float(LaunchConfiguration('square_size_mm').perform(context))
    board_columns = int(LaunchConfiguration('board_columns').perform(context))
    board_rows = int(LaunchConfiguration('board_rows').perform(context))
    return [
        *create_camera_actions(context, camera_to_calibrate),
        Node(
            package='camera_pose_calibrator',
            executable='sheet_pose_calibrator',
            name='sheet_pose_calibrator_node',
            output='screen',
            emulate_tty=True,
            parameters=[{
                'camera_pose_file': camera_pose_file_path,
                # The child of the camera's mount transform
                'base_frame': get_camera_body_frame_id(
                    camera, read_camera_entry(camera_to_calibrate.camera_type)),
                'placeholder_rotation': placeholder_rotation,
                'square_size_m': square_size_mm / 1000.0,
                'board_columns': board_columns,
                'board_rows': board_rows,
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
        DeclareLaunchArgument(
            'square_size_mm',
            description='Side of one square of the printed board, measured on the sheet, in '
                        'millimetres.'),
        # The defaults fit utils/checkerboard.png
        DeclareLaunchArgument(
            'board_columns',
            default_value='8',
            description='Inner corners of the checkerboard along its long side.'),
        DeclareLaunchArgument(
            'board_rows',
            default_value='6',
            description='Inner corners of the checkerboard along its short side.'),
        OpaqueFunction(function=launch_setup),
    ])
