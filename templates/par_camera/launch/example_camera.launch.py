# Written by Claude Code
"""
Start the example camera's driver as a PAR framework camera.

par.launch.py includes this file for the camera type's entry and passes the five arguments below.
It imports nothing from the framework, so the driver's repo does not depend on it. Started alone,
it needs at least namespace and camera_name, e.g.
namespace:=/cameras/example_camera camera_name:=example_camera.
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

# The driver's node name; its section in the parameter files is /cameras/*/<name> (every camera of
# the type) or /cameras/<camera name>/<name> (one camera)
DRIVER_NODE_NAME = 'example_camera_node'


def launch_setup(context):
    namespace = LaunchConfiguration('namespace').perform(context)
    camera_name = LaunchConfiguration('camera_name').perform(context)
    serial = LaunchConfiguration('serial').perform(context)
    camera_info_url = LaunchConfiguration('camera_info_url').perform(context)
    params_files_text = LaunchConfiguration('params_files').perform(context)
    params_file_paths = []
    if params_files_text:
        params_file_paths = params_files_text.split(os.pathsep)

    # What the framework decides, set here and not in the parameter files: the frame names
    # (<camera name>_..., so two cameras never share a frame), the unit and its intrinsics. Use the
    # driver's own parameter names
    driver_parameters = {'frame_id': f'{camera_name}_optical_frame'}
    if serial:
        # As text: launch would read a serial of digits as a number
        driver_parameters['serial'] = ParameterValue(serial, value_type=str)
    if camera_info_url:
        driver_parameters['camera_info_url'] = camera_info_url

    return [
        Node(
            package='example_camera',
            executable='example_camera',
            name=DRIVER_NODE_NAME,
            namespace=namespace,
            output='screen',
            emulate_tty=True,
            parameters=[*params_file_paths, driver_parameters],
            # Map the driver's own names onto the stream names of the entry, below the namespace.
            # Absolute names on both sides, so it is clear what is matched: e.g. a driver that
            # publishes below its node name, or creates a service at the root
            remappings=[
                (f'{namespace}/{DRIVER_NODE_NAME}/image_raw', f'{namespace}/image_raw'),
                (f'{namespace}/{DRIVER_NODE_NAME}/camera_info', f'{namespace}/camera_info'),
                ('/set_camera_info', f'{namespace}/set_camera_info'),
            ],
        ),
        # Only for a driver that does not publish <camera name>_link -> <camera name>_optical_frame
        # itself: z forward, y down (REP 103)
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='optical_tf_publisher',
            namespace=namespace,
            arguments=['--frame-id', f'{camera_name}_link',
                       '--child-frame-id', f'{camera_name}_optical_frame',
                       '--qx', '-0.5', '--qy', '0.5', '--qz', '-0.5', '--qw', '0.5'],
        ),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('namespace',
                              description='Namespace of the camera: its streams are '
                                          '<namespace>/image_raw, ...'),
        DeclareLaunchArgument('camera_name',
                              description='Prefix of every TF frame the camera publishes.'),
        DeclareLaunchArgument('serial', default_value='',
                              description='Serial of the unit to open; empty opens the first one.'),
        DeclareLaunchArgument('camera_info_url', default_value='',
                              description='file:// URL of the intrinsics; empty for none.'),
        DeclareLaunchArgument('params_files', default_value='',
                              description='Parameter files joined with the path separator (:), '
                                          'applied in this order.'),
        OpaqueFunction(function=launch_setup),
    ])
