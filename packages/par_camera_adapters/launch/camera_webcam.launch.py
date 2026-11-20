# Written by Claude Code
"""
Start a generic UVC webcam with v4l2_camera as a PAR framework camera (camera type webcam).

The framework includes this file for the camera type's entry (resource/par_framework_cameras/
webcam) and passes the arguments every camera launch file declares
(README.md of par_framework_core).
Started alone, e.g. to check it, it needs at least namespace and camera_name, e.g.
namespace:=/cameras/webcam camera_name:=webcam.

v4l2_camera exposes no serial, so serial is ignored and every webcam shares one intrinsics file.
Settings (device, size, encoding) under /cameras/*/webcam_node in the parameter files.
"""

from launch import LaunchDescription
from launch.actions import OpaqueFunction
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (create_camera_launch_arguments,
                                               create_optical_frame_tf_publisher,
                                               read_camera_launch_arguments)


def launch_setup(context):
    camera = read_camera_launch_arguments(context)
    namespace = camera['namespace']
    # The optical frame must match the transform below, so it is set here and not in the
    # parameter files
    driver_parameters = {'camera_frame_id': f'{camera["camera_name"]}_optical_frame'}
    if camera['camera_info_url']:
        driver_parameters['camera_info_url'] = camera['camera_info_url']
    return [
        # Publishes image_raw and camera_info relative to its namespace
        Node(
            package='v4l2_camera',
            executable='v4l2_camera_node',
            name='webcam_node',
            namespace=namespace,
            output='screen',
            emulate_tty=True,
            parameters=[*camera['params_files'], driver_parameters],
            # Its calibration service ignores the node's namespace and is created at the root
            remappings=[('/set_camera_info', f'{namespace}/set_camera_info')],
        ),
        create_optical_frame_tf_publisher(camera['camera_name'], namespace),
    ]


def generate_launch_description():
    return LaunchDescription([
        *create_camera_launch_arguments(),
        OpaqueFunction(function=launch_setup),
    ])
