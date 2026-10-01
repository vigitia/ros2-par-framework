"""Calibration run: camera plus the surface selector.

Start this once per physical setup to mark the projection area in the camera
image; the resulting corners are what the rest of the framework warps against.
The projector window opens on the display given by `display_id` in the
parameter file.
The selected corners are stored by projection_corners_node in
config/projection_corners.yaml, next to par_setup.yaml (added with the help of Claude Code).
camera:=kinect uses the Azure Kinect instead of the Brio, camera:=webcam a generic webcam (both
added with the help of Claude Code), and the launch ends once the corners are
stored or the selection is cancelled with Esc (added with the help of Claude Code).
params_file points the Brio calibration into the container; on the host, from the repo root:

    ros2 launch par_framework_core calibration.launch.py \\
        camera_info_url:="file://$PWD/src/logitech_brio/calibration/\\${NAME}.yaml"
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (camera_nodes, CAMERA_REMAPPINGS,
                                               projection_corners_node)

PACKAGE_NAME = 'par_framework_core'


# Written by Claude Code
def camera_and_surface_selector(context):
    """Start the chosen camera and the surface selector on its image."""
    camera = LaunchConfiguration('camera').perform(context)
    return camera_nodes(context, camera) + [Node(
        package='surface_selector',
        executable='surface_selector',
        name='surface_selector_node',
        output='screen',
        emulate_tty=True,
        parameters=[LaunchConfiguration('params_file')],
        # Its topic_name_frame is the Brio's image
        remappings=CAMERA_REMAPPINGS[camera],
        # Corners stored (projection_corners_node writes them before it answers) or selection
        # cancelled: the camera and the corners owner are not needed any longer
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
            'camera_info_url',
            default_value='',
            description='Overrides the Brio calibration URL from params_file, e.g. for a host '
                        'run: file://<repo>/src/logitech_brio/calibration/${NAME}.yaml. '
                        'Empty keeps the one from params_file.'),
        DeclareLaunchArgument(
            'camera',
            default_value='brio',
            description='brio, kinect or webcam.'),

        OpaqueFunction(function=camera_and_surface_selector),

        # Stores the corners surface_selector sends and publishes them on /projection_corners
        OpaqueFunction(function=projection_corners_node),
    ])
