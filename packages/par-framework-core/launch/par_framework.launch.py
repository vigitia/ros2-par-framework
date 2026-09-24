"""Bring up the PAR framework: camera source plus the processing pipeline.

Every node reads its parameters from config/par_setup.yaml, so a different
physical setup means a different parameter file, not different code:

    ros2 launch par_framework_core par_framework.launch.py \\
        params_file:=/path/to/other_setup.yaml

Add rviz:=true to open RViz with the TF frames, the Brio frustum and its image, plus
rviz_bridge, which shows the object detector's /objects on the table (the detector itself is
started separately).
params_file points the Brio calibration into the container; on the host, from the repo root:

    ros2 launch par_framework_core par_framework.launch.py \\
        camera_info_url:="file://$PWD/src/logitech_brio/calibration/\\${NAME}.yaml"

The Brio mount transform and the RViz option were written with the help of Claude Code.
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import yaml

PACKAGE_NAME = 'par_framework_core'


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
            'rviz',
            default_value='false',
            description='Open RViz with the TF frames, the Brio frustum and its image.'),
        DeclareLaunchArgument(
            'camera_info_url',
            default_value='',
            description='Overrides the Brio calibration URL from params_file, e.g. for a host '
                        'run: file://<repo>/src/logitech_brio/calibration/${NAME}.yaml. '
                        'Empty keeps the one from params_file.'),

        OpaqueFunction(function=logitech_brio_node),

        # Where the Brio is mounted: world -> brio_link, pose from params_file. The node itself
        # publishes brio_link -> brio_optical_frame. Frame names must match the Brio node.
        OpaqueFunction(function=brio_tf_publisher),

        Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', os.path.join(
                get_package_share_directory(PACKAGE_NAME), 'config', 'par_framework.rviz')],
            condition=IfCondition(LaunchConfiguration('rviz')),
        ),
        # Turns outputs RViz cannot display, like /objects in image pixels, into markers
        Node(
            package='rviz_bridge',
            executable='rviz_bridge',
            name='rviz_bridge_node',
            output='screen',
            emulate_tty=True,
            condition=IfCondition(LaunchConfiguration('rviz')),
        ),
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
def brio_tf_publisher(context):
    """Publish world -> brio_link with the pose from the parameter file."""
    # static_transform_publisher takes its transform only as command-line flags: parameters from a
    # file are overridden by the flags' defaults, and without --frame-id it does not start. So the
    # pose is read from the parameter file here, which is only possible once params_file is known.
    with open(LaunchConfiguration('params_file').perform(context)) as f:
        pose = yaml.safe_load(f)['/brio_tf_publisher']['ros__parameters']
    arguments = ['--frame-id', 'world', '--child-frame-id', 'brio_link']
    for axis in 'xyz':
        arguments += [f'--{axis}', str(pose[f'translation.{axis}'])]
    for axis in 'xyzw':
        arguments += [f'--q{axis}', str(pose[f'rotation.{axis}'])]
    return [Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='brio_tf_publisher',
        arguments=arguments,
    )]
