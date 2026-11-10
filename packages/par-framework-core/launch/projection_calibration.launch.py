# Written by Claude Code
r"""
Automatic table-to-projector calibration.

The projector shows ArUco markers at known projector pixels (on par_launch.projector_display_id,
or projector_display_id:=<n> for one run; the resolution is read from that display),
fiducials_detector finds them in the camera image, and projection_calibrator fits the homography
from the table plane to projector pixels. It is stored by projection_calibration_server_node in
config/calibration/extrinsics/projection_mapping_<camera>.yaml, and published latched on
/projection_mapping. The launch ends when the calibrator is done. camera:= (brio, kinect,
realsense, webcam, blackfly, cu40 or event) picks the camera; without it, par_launch.camera
from params_file.

Needs the camera calibration and the camera pose (/<camera>_tf_publisher in par_setup.yaml), and
a clear table. The camera calibration is config/calibration/intrinsics/camera_info_<camera>.yaml;
the Kinect and the RealSense publish their factory calibrations. With profile:=<name>, the camera
calibration and the mapping are that setup's own, in config/calibration/intrinsics/<name>/ and
config/calibration/extrinsics/<name>/.

projector_center:=true runs the second step instead, which the projection mask needs: hold a flat
board above the table and move it through the projection. The depth camera locates the markers
on the board in 3D, and with the stored homography each marker corner gives one projector ray; the
rays meet at the projector's optical centre, which is stored with the mapping. Needs a depth
camera (kinect or realsense) and a mapping from the first step; re-running the first step clears
the centre again.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (create_camera_actions,
                                               create_camera_stream_remappings,
                                               create_profile_launch_argument,
                                               create_projection_calibration_server_node,
                                               create_projector_display_id_launch_argument,
                                               get_chosen_camera, get_params_file_paths,
                                               get_projector_display_id, read_camera_entry,
                                               read_launch_section)

PACKAGE_NAME = 'par_framework_core'
# The stream the projector centre step needs: depth registered to the colour image
DEPTH_REGISTERED_STREAM_NAME = 'depth_registered/image_raw'
# The projected markers are large and lie still, unlike the printed ones a profile may tune
# fiducials_detector for (small, moving, found by tracking): detection runs with its general
# settings, whatever the profile sets. The values are those of par_setup.yaml
FIDUCIALS_DETECTOR_GENERAL_DETECTION_PARAMETERS = {
    'tracking_window_size_px': 0,
    'adaptive_thresh_win_size_min_px': 3,
    'adaptive_thresh_win_size_max_px': 23,
    'bit_sample_px_per_cell': 4,
    'bit_ignored_margin_per_cell': 0.13,
}


def launch_setup(context):
    camera = get_chosen_camera(context)
    params_file_paths = get_params_file_paths(context)
    projector_center_argument = LaunchConfiguration('projector_center').perform(context)
    if projector_center_argument not in ('true', 'false'):
        raise RuntimeError(f'[projection_calibration.launch]: '
                           f'projector_center:={projector_center_argument}: use true or false')
    is_projector_center_run = projector_center_argument == 'true'
    projection_calibrator_parameters = [*params_file_paths,
                                        {'projector_center': is_projector_center_run}]
    # The same display the projector app gets; without one, the calibrator's own default applies
    projector_display_id = get_projector_display_id(context, read_launch_section(context))
    if projector_display_id is not None:
        projection_calibrator_parameters.append({'display_id': projector_display_id})
    is_depth_camera = DEPTH_REGISTERED_STREAM_NAME in read_camera_entry(camera)['streams']
    if is_projector_center_run and not is_depth_camera:
        raise RuntimeError(f'[projection_calibration.launch]: projector_center:=true needs a '
                           f'camera with depth on its colour image ({DEPTH_REGISTERED_STREAM_NAME} '
                           f'in its entry\'s streams), but the camera is {camera}: run it with '
                           f'e.g. camera:=kinect or camera:=realsense')
    fiducials_detector_node = Node(
        package='fiducials_detector',
        executable='fiducials_detector',
        name='fiducials_detector_node',
        output='screen',
        emulate_tty=True,
        # The projector centre needs the markers in 3D (corners_3d)
        parameters=[*params_file_paths,
                    FIDUCIALS_DETECTOR_GENERAL_DETECTION_PARAMETERS,
                    {'use_depth': is_projector_center_run}],
        remappings=create_camera_stream_remappings(camera),
    )
    projection_calibrator_node = Node(
        package='surface_selector',
        executable='projection_calibrator',
        name='projection_calibrator_node',
        output='screen',
        emulate_tty=True,
        parameters=projection_calibrator_parameters,
        remappings=create_camera_stream_remappings(camera),
        # Stored or failed: the camera and the projector are not needed any longer
        on_exit=Shutdown(reason='projection calibration finished'),
    )
    # The calibration converts camera pixels to the table plane, so the camera pose is needed.
    # The camera publishes in /cameras/<camera>, where the remappings point both nodes' camera
    # streams
    return [*create_camera_actions(context, camera),
            fiducials_detector_node,
            *create_projection_calibration_server_node(context, camera),
            projection_calibrator_node]


def generate_launch_description():
    default_params_file_path = os.path.join(
        get_package_share_directory(PACKAGE_NAME), 'config', 'par_setup.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params_file_path,
            description='Parameter file describing this physical PAR setup.'),
        create_profile_launch_argument(),
        create_projector_display_id_launch_argument(),
        DeclareLaunchArgument(
            'camera',
            default_value='',
            description='Camera type, one installed in the ament index (par_framework_cameras), '
                        'e.g. webcam or blackfly. Empty uses par_launch.camera from params_file.'),
        DeclareLaunchArgument(
            'projector_center',
            default_value='false',
            description='true: find the projector centre with a raised board instead of fitting '
                        'the homography. Needs a depth camera (kinect, realsense) and a stored '
                        'mapping.'),
        OpaqueFunction(function=launch_setup),
    ])
