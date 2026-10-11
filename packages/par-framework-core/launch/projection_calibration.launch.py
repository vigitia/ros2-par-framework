# Written by Claude Code
r"""
Automatic table-to-projector calibration.

The projector shows ArUco markers at known projector pixels (display_id under
projection_calibrator_node in par_setup.yaml; the resolution is read from that display),
fiducials_detector finds them in the camera image, and projection_calibrator fits the homography
from the table plane to projector pixels. It is stored by projection_calibration_server_node in
config/calibration/extrinsics/projection_mapping_<camera>.yaml, and published latched on
/projection_mapping. The launch ends when the calibrator is done. camera:= (brio, kinect or
webcam) picks the camera; without it, par_launch.camera from params_file.

Needs the camera calibration and the camera pose (/<camera>_tf_publisher in par_setup.yaml), and
a clear table. The camera calibration is config/calibration/intrinsics/camera_info_<camera>.yaml;
the Kinect publishes its factory calibration.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (camera_nodes, chosen_camera,
                                               projection_calibration_server_node)

PACKAGE_NAME = 'par_framework_core'


def launch_setup(context):
    camera = chosen_camera(context)
    params_file = LaunchConfiguration('params_file')
    # The calibration converts camera pixels to the table plane, so the camera pose is needed.
    # The camera publishes on /camera/..., where both nodes below subscribe
    return camera_nodes(context, camera) + [
        Node(
            package='fiducials_detector',
            executable='fiducials_detector',
            name='fiducials_detector_node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file],
        ),
        *projection_calibration_server_node(camera),
        Node(
            package='surface_selector',
            executable='projection_calibrator',
            name='projection_calibrator_node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file],
            # Stored or failed: the camera and the projector are not needed any longer
            on_exit=Shutdown(reason='projection calibration finished'),
        ),
    ]


def generate_launch_description():
    default_params = os.path.join(
        get_package_share_directory(PACKAGE_NAME), 'config', 'par_setup.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Parameter file describing this physical PAR setup.'),
        DeclareLaunchArgument(
            'camera',
            default_value='',
            description='brio, kinect or webcam. Empty uses par_launch.camera from params_file.'),
        OpaqueFunction(function=launch_setup),
    ])
