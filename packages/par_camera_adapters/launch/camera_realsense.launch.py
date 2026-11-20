# Written by Claude Code
"""
Start an Intel RealSense (e.g. D435) with realsense2_camera as a PAR framework camera (realsense).

The framework includes this file for the camera type's entry (resource/par_framework_cameras/
realsense) and passes the arguments every camera launch file declares
(README.md of par_framework_core).
The driver publishes its factory calibration, so camera_info_url is ignored. Settings under
/cameras/*/realsense in the parameter files.
"""

from launch import LaunchDescription
from launch.actions import OpaqueFunction
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from par_framework_core.launch_helpers import (create_camera_launch_arguments,
                                               read_camera_launch_arguments)

DRIVER_NODE_NAME = 'realsense'


def launch_setup(context):
    camera = read_camera_launch_arguments(context)
    namespace = camera['namespace']
    # camera_name prefixes the driver's TF frames (<camera_name>_link, ...), which the mount
    # transform attaches to, so it is set here and not in the parameter files
    driver_parameters = {'camera_name': camera['camera_name']}
    if camera['serial']:
        driver_parameters['serial_no'] = ParameterValue(camera['serial'], value_type=str)
    # Simplification: assumes the driver publishes below its node name, as it does while
    # camera_name and the node name are the same (camera type realsense). Not checked with
    # another camera name; check with ros2 topic list once profiles name their cameras
    driver_topic_prefix = f'{namespace}/{DRIVER_NODE_NAME}'
    return [Node(
        package='realsense2_camera',
        executable='realsense2_camera_node',
        name=DRIVER_NODE_NAME,
        namespace=namespace,
        output='screen',
        emulate_tty=True,
        parameters=[*camera['params_files'], driver_parameters],
        remappings=[
            (f'{driver_topic_prefix}/color/image_raw', f'{namespace}/image_raw'),
            (f'{driver_topic_prefix}/color/camera_info', f'{namespace}/camera_info'),
            # Its depth on the colour image's pixel grid, published with align_depth.enable
            (f'{driver_topic_prefix}/aligned_depth_to_color/image_raw',
             f'{namespace}/depth_registered/image_raw'),
        ],
    )]


def generate_launch_description():
    return LaunchDescription([
        *create_camera_launch_arguments(),
        OpaqueFunction(function=launch_setup),
    ])
