# Written by Claude Code
"""
Start an Azure Kinect with azure_kinect_ros_driver as a PAR framework camera (camera type kinect).

The framework includes this file for the camera type's entry (resource/par_framework_cameras/
kinect) and passes the arguments every camera launch file declares
(README.md of par_framework_core).
The driver publishes its factory calibration, so camera_info_url is ignored. Settings under
/cameras/*/k4a_ros_device_node in the parameter files.
"""

from launch import LaunchDescription
from launch.actions import OpaqueFunction
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from par_framework_core.launch_helpers import (create_camera_launch_arguments,
                                               read_camera_launch_arguments)


def launch_setup(context):
    camera = read_camera_launch_arguments(context)
    namespace = camera['namespace']
    # tf_prefix puts the camera's name in front of every frame the driver publishes
    # (<camera_name>_camera_base, ..._rgb_camera_link, ...), so two Kinects never share a frame
    driver_parameters = {'tf_prefix': f'{camera["camera_name"]}_'}
    if camera['serial']:
        driver_parameters['sensor_sn'] = ParameterValue(camera['serial'], value_type=str)
    return [Node(
        package='azure_kinect_ros_driver',
        executable='node',
        # No name override: the driver runs several rclcpp nodes in one process, and name= would
        # rename all of them. The namespace applies to all of them
        namespace=namespace,
        output='screen',
        emulate_tty=True,
        parameters=[*camera['params_files'], driver_parameters],
        # The driver's own names are relative, so they lie in the namespace already
        remappings=[
            (f'{namespace}/rgb/image_raw', f'{namespace}/image_raw'),
            (f'{namespace}/rgb/camera_info', f'{namespace}/camera_info'),
            (f'{namespace}/depth_to_rgb/image_raw', f'{namespace}/depth_registered/image_raw'),
            # Infrared transformed onto the colour image's grid by the driver (its depth_ir is on
            # the depth grid). image_transport applies these rules twice, so no target here may be
            # another rule's source, or a topic is moved on to that rule's target
            (f'{namespace}/ir_to_rgb/image_raw', f'{namespace}/ir/image_raw'),
            # The depth sensor's own infrared and depth, e.g. for hand_landmarks with use_ir
            (f'{namespace}/depth_ir/image_raw', f'{namespace}/depth_sensor/ir/image_raw'),
            (f'{namespace}/depth/image_raw', f'{namespace}/depth_sensor/depth/image_raw'),
            (f'{namespace}/depth/camera_info', f'{namespace}/depth_sensor/camera_info'),
        ],
    )]


def generate_launch_description():
    return LaunchDescription([
        *create_camera_launch_arguments(),
        OpaqueFunction(function=launch_setup),
    ])
