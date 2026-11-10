"""Calibration run: camera plus the surface selector.

Start this once per physical setup to mark the projection area in the camera
image; the resulting corners are what the rest of the framework warps against.
The projector window opens on the display given by `display_id` in the
parameter file.
The selected corners are stored by projection_calibration_server_node in
config/calibration/extrinsics/projection_corners_<camera>.yaml (added with the help of Claude
Code).
camera:= chooses an installed camera type, e.g. kinect or webcam (added with the help of Claude
Code), and the launch ends once the corners are
stored or the selection is cancelled with Esc (added with the help of Claude Code).
Camera calibrations are config/calibration/intrinsics/camera_info_<camera>.yaml (changed with the
help of Claude Code). With profile:=<name>, the camera calibration and the corners are that
setup's own, in config/calibration/intrinsics/<name>/ and config/calibration/extrinsics/<name>/
(added with the help of Claude Code).
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (create_camera_actions,
                                               create_camera_stream_remappings,
                                               create_profile_launch_argument,
                                               create_projection_calibration_server_node,
                                               get_chosen_camera, get_params_file_paths)

PACKAGE_NAME = 'par_framework_core'


# Written by Claude Code; the remappings of the camera streams co-authored by Claude Code
def create_camera_and_surface_selector(context):
    """Create the chosen camera, the surface selector on its image and the corners owner."""
    camera = get_chosen_camera(context)
    surface_selector_node = Node(
        package='surface_selector',
        executable='surface_selector',
        name='surface_selector_node',
        output='screen',
        emulate_tty=True,
        parameters=get_params_file_paths(context),
        # Its relative camera stream names point at the camera started here
        remappings=create_camera_stream_remappings(camera),
        # Corners stored (projection_calibration_server_node writes them before it answers) or
        # selection cancelled: the camera and the corners owner are not needed any longer
        on_exit=Shutdown(reason='projection corners selected'),
    )
    # The corners owner stores what surface_selector sends, in the camera's own file, and
    # publishes it on /projection_corners
    return [*create_camera_actions(context, camera),
            *create_projection_calibration_server_node(context, camera),
            surface_selector_node]


# Co-authored by Claude Code
def generate_launch_description():
    default_params_file_path = os.path.join(
        get_package_share_directory(PACKAGE_NAME), 'config', 'par_setup.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params_file_path,
            description='Parameter file describing this physical PAR setup.'),
        create_profile_launch_argument(),
        DeclareLaunchArgument(
            'camera',
            default_value='',
            description='Camera type, one installed in the ament index (par_framework_cameras), '
                        'e.g. webcam or blackfly. Empty uses par_launch.camera from params_file.'),

        OpaqueFunction(function=create_camera_and_surface_selector),
    ])
