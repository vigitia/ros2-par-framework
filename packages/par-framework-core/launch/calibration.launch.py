"""Calibration run: camera plus the surface selector.

Start this once per physical setup to mark the projection area in the camera
image; the resulting corners are what the rest of the framework warps against.
The projector window opens on the display given by `display_id` in the
parameter file.
The selected corners are stored by projection_corners_node in
config/projection_corners.yaml, next to par_setup.yaml (added with the help of Claude Code).
params_file points the Brio calibration into the container; on the host, from the repo root:

    ros2 launch par_framework_core calibration.launch.py \\
        camera_info_url:="file://$PWD/src/logitech_brio/calibration/\\${NAME}.yaml"
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PACKAGE_NAME = 'par_framework_core'


# Co-authored by Claude Code
def generate_launch_description():
    default_params = os.path.join(
        get_package_share_directory(PACKAGE_NAME), 'config', 'par_setup.yaml')

    params_file = LaunchConfiguration('params_file')

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

        OpaqueFunction(function=logitech_brio_node),

        Node(
            package='surface_selector',
            executable='surface_selector',
            name='surface_selector_node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file],
        ),

        # Stores the corners surface_selector sends and publishes them on /projection_corners
        OpaqueFunction(function=projection_corners_node),
    ])


# Co-authored by Claude Code
def logitech_brio_node(context):
    """Start the Brio with params_file, and camera_info_url on top if it is given."""
    parameters = [LaunchConfiguration('params_file').perform(context)]
    # Only added when set: an empty value would replace the URL from params_file with '', which
    # the node reads as the default ~/.ros/camera_info/ instead
    camera_info_url = LaunchConfiguration('camera_info_url').perform(context)
    if camera_info_url:
        parameters.append({'camera_info_url': camera_info_url})
    return [Node(
        package='logitech_brio',
        executable='logitech_brio',
        name='logitech_brio_node',
        output='screen',
        emulate_tty=True,
        parameters=parameters,
    )]


# Co-authored by Claude Code
def projection_corners_node(context):
    """Start the projection corners owner with its file next to the real par_setup.yaml."""
    # realpath follows the --symlink-install links back to the source folder, so the file is saved
    # where it survives rebuilds, on the host and in the container alike
    params_file = os.path.realpath(LaunchConfiguration('params_file').perform(context))
    corners_file = os.path.join(os.path.dirname(params_file), 'projection_corners.yaml')
    return [Node(
        package='projection_corners',
        executable='projection_corners',
        name='projection_corners_node',
        output='screen',
        emulate_tty=True,
        parameters=[{'projection_corners_file': corners_file}],
    )]
