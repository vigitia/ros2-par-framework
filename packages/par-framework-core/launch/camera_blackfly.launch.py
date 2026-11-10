# Written by Claude Code
"""
Start a FLIR Blackfly S with spinnaker_camera_driver as a PAR framework camera (type blackfly).

The framework includes this file for the camera type's entry (resource/par_framework_cameras/
blackfly) and passes the arguments every camera launch file declares (templates/par_camera/).
Started alone, e.g. to check one unit, it needs at least namespace and camera_name, e.g.
namespace:=/cameras/blackfly camera_name:=blackfly serial:=22260470.

Settings under /cameras/*/blackfly (all units) or /cameras/<camera name>/blackfly (one unit) in the
parameter files.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import OpaqueFunction
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from par_framework_core.launch_helpers import (create_camera_launch_arguments,
                                               create_optical_frame_tf_publisher,
                                               read_camera_launch_arguments)

# The driver's node name, which its topics are created below
DRIVER_NODE_NAME = 'blackfly'


def launch_setup(context):
    camera = read_camera_launch_arguments(context)
    namespace = camera['namespace']
    # The driver maps its ROS parameters onto the camera's settings with this file: the driver's
    # own for the whole Blackfly S series plus a software trigger (trigger_software), which a camera
    # in trigger mode needs and a freely running one ignores
    camera_settings_mapping_path = os.path.join(
        get_package_share_directory('par_framework_core'), 'config',
        'blackfly_s_software_trigger.yaml')
    # frame_id must match the optical frame transform below, so it is set here and not in the
    # parameter files. The driver spells its calibration parameter camerainfo_url
    driver_parameters = {'parameter_file': camera_settings_mapping_path,
                         'camerainfo_url': camera['camera_info_url'],
                         'frame_id': f'{camera["camera_name"]}_optical_frame'}
    if camera['serial']:
        # As text: launch would read a serial of digits as a number, which the driver refuses
        driver_parameters['serial_number'] = ParameterValue(camera['serial'], value_type=str)
    driver_topic_prefix = f'{namespace}/{DRIVER_NODE_NAME}'
    return [
        Node(
            package='spinnaker_camera_driver',
            executable='camera_driver_node',
            name=DRIVER_NODE_NAME,
            namespace=namespace,
            output='screen',
            emulate_tty=True,
            parameters=[*camera['params_files'], driver_parameters],
            remappings=[
                # The driver publishes below its node name
                (f'{driver_topic_prefix}/image_raw', f'{namespace}/image_raw'),
                (f'{driver_topic_prefix}/camera_info', f'{namespace}/camera_info'),
                # Its calibration service ignores the node's namespace and is created at the root
                ('/set_camera_info', f'{namespace}/set_camera_info'),
            ],
        ),
        create_optical_frame_tf_publisher(camera['camera_name'], namespace),
    ]


def generate_launch_description():
    return LaunchDescription([
        *create_camera_launch_arguments(),
        OpaqueFunction(function=launch_setup),
    ])
