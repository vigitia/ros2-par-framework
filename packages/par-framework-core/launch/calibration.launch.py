"""Calibration run: camera plus the surface selector.

Start this once per physical setup to mark the projection area in the camera
image; the resulting corners are what the rest of the framework warps against.
The projector window opens on the display given by `display_id` in the
parameter file.
The selected corners are stored by projection_calibration_server_node in
config/calibration/extrinsics/projection_corners_<camera>.yaml (added with the help of Claude
Code).
camera:=kinect uses the Azure Kinect instead of the Brio, camera:=webcam a generic webcam (both
added with the help of Claude Code), and the launch ends once the corners are
stored or the selection is cancelled with Esc (added with the help of Claude Code).
Camera calibrations are config/calibration/intrinsics/camera_info_<camera>.yaml, shared by all
profiles (changed with the
help of Claude Code).
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (camera_nodes, chosen_camera,
                                               projection_calibration_server_node)

PACKAGE_NAME = 'par_framework_core'


# Written by Claude Code
def camera_and_surface_selector(context):
    """Start the chosen camera, the surface selector on its image and the corners owner."""
    camera = chosen_camera(context)
    # The corners owner stores what surface_selector sends, in the camera's own file, and
    # publishes it on /projection_corners
    return camera_nodes(context, camera) + projection_calibration_server_node(camera) + [Node(
        package='surface_selector',
        executable='surface_selector',
        name='surface_selector_node',
        output='screen',
        emulate_tty=True,
        # Its topic_name_frame is /camera/image_raw, which every camera publishes
        parameters=[LaunchConfiguration('params_file')],
        # Corners stored (projection_calibration_server_node writes them before it answers) or
        # selection cancelled: the camera and the corners owner are not needed any longer
        on_exit=Shutdown(reason='projection corners selected'),
    )]


# Co-authored by Claude Code
def generate_launch_description():
    default_params = os.path.join(
        get_package_share_directory(PACKAGE_NAME), 'config', 'par_setup.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Parameter file describing this physical PAR setup.'),
        DeclareLaunchArgument(
            'camera',
            default_value='',
            description='brio, kinect or webcam. Empty uses par_launch.camera from params_file.'),

        OpaqueFunction(function=camera_and_surface_selector),
    ])
