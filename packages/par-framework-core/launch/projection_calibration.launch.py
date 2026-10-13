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

projector_center:=true runs the second step instead, which the projection mask needs: hold a flat
board above the table and move it through the projection. The depth camera locates the markers
on the board in 3D, and with the stored homography each marker corner gives one projector ray; the
rays meet at the projector's optical centre, which is stored with the mapping. Needs the Kinect
(depth) and a mapping from the first step; re-running the first step clears the centre again.
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
# Cameras with depth registered to the colour image, which the projector centre step needs
DEPTH_CAMERAS = ('kinect',)


def launch_setup(context):
    camera = chosen_camera(context)
    params_file = LaunchConfiguration('params_file')
    projector_center = LaunchConfiguration('projector_center').perform(context)
    if projector_center not in ('true', 'false'):
        raise RuntimeError(f'[projection_calibration.launch]: '
                           f'projector_center:={projector_center}: use true or false')
    projector_center = projector_center == 'true'
    if projector_center and camera not in DEPTH_CAMERAS:
        raise RuntimeError(f'[projection_calibration.launch]: projector_center:=true needs a '
                           f'depth camera, but the camera is {camera}: run it with '
                           f'camera:=kinect')
    # The calibration converts camera pixels to the table plane, so the camera pose is needed.
    # The camera publishes on /camera/..., where both nodes below subscribe
    return camera_nodes(context, camera) + [
        Node(
            package='fiducials_detector',
            executable='fiducials_detector',
            name='fiducials_detector_node',
            output='screen',
            emulate_tty=True,
            # The projector centre needs the markers in 3D (corners_3d)
            parameters=[params_file, {'use_depth': projector_center}],
        ),
        *projection_calibration_server_node(camera),
        Node(
            package='surface_selector',
            executable='projection_calibrator',
            name='projection_calibrator_node',
            output='screen',
            emulate_tty=True,
            parameters=[params_file, {'projector_center': projector_center}],
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
        DeclareLaunchArgument(
            'projector_center',
            default_value='false',
            description='true: find the projector centre with a raised board instead of fitting '
                        'the homography. Needs camera:=kinect and a stored mapping.'),
        OpaqueFunction(function=launch_setup),
    ])
