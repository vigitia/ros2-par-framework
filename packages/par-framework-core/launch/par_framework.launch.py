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

The Brio mount transform, the RViz option and the projection nodes were written with the help
of Claude Code; the start functions live in par_framework_core/launch_helpers.py.
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (logitech_brio_node, mount_tf_publisher,
                                               projection_corners_node,
                                               projection_mapping_node)

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
        OpaqueFunction(function=mount_tf_publisher, args=['brio_tf_publisher', 'brio_link']),

        # Publishes the stored projection corners on /projection_corners
        OpaqueFunction(function=projection_corners_node),
        # Publishes the stored table-to-projector mapping on /projection_mapping
        OpaqueFunction(function=projection_mapping_node, args=['brio']),

        Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', os.path.join(
                get_package_share_directory(PACKAGE_NAME), 'config', 'par_framework_brio.rviz')],
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
