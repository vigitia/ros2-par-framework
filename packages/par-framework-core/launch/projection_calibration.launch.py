# Written by Claude Code
r"""
Automatic table-to-projector calibration.

The projector shows ArUco markers at known projector pixels (on par_launch.projector_display_id,
or projector_display_id:=<n> for one run; the resolution is read from that display),
fiducials_detector finds them in the camera image, and projection_calibrator fits the homography
from the table plane to projector pixels. It is stored by projection_calibration_server_node in
config/calibration/extrinsics/projection_mapping_<camera>.yaml, and published latched on
/cameras/<camera>/projection_mapping. The launch ends when the calibrator is done. camera:= picks
the camera when the profile has several (a name of par_launch.cameras).

With a measured camera pose (camera_pose_<camera>.yaml), world becomes the projected image's:
origin at its bottom left corner on the table, x along its bottom edge. The mapping is stored from
that world and the pose file gets the matching x, y and rotation about the vertical, so all
cameras that see the projection share one world. Without one, the camera keeps its own world.

Needs the camera calibration and the camera pose (camera_pose_<camera>.yaml, else the placeholder
pose in the parameter files), and a clear table. The camera calibration is
config/calibration/intrinsics/camera_info_<type>[_<serial>].yaml; a camera whose driver publishes
its factory calibration needs none. With profile:=<name>, the camera
calibration and the mapping are that setup's own, in config/calibration/intrinsics/<name>/ and
config/calibration/extrinsics/<name>/.

projector_center:=true runs the second step instead, which the projection mask needs: hold a flat
board above the table and move it through the projection. The depth camera locates the markers
on the board in 3D, and with the stored homography each marker corner gives one projector ray; the
rays meet at the projector's optical centre, which is stored with the mapping. Needs a camera
with depth on its colour image (depth_registered/image_raw in its entry's streams) and a mapping
from the first step; re-running the first step clears the centre again.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (create_camera_actions,
                                               create_camera_choice_launch_argument,
                                               create_profile_launch_argument,
                                               create_projection_calibration_server_node,
                                               create_projector_display_id_launch_argument,
                                               get_camera_namespace, get_camera_to_calibrate,
                                               get_extrinsics_relative_path,
                                               get_installed_par_setup_path, get_params_file_paths,
                                               get_path_in_config_folder,
                                               get_projector_display_id, read_camera_entry,
                                               read_launch_section)

# The stream the projector centre step needs: depth registered to the colour image
DEPTH_REGISTERED_STREAM_NAME = 'depth_registered/image_raw'
# The projected markers are large and lie still, unlike the printed ones a profile may tune
# fiducials_detector for (small, moving, found by tracking): detection runs with its general
# settings, whatever the profile sets. The values are those of par_setup.yaml
FIDUCIALS_DETECTOR_GENERAL_DETECTION_PARAMETERS = {
    'tracking_mode': False,
    'adaptive_thresh_win_size_min_px': 3,
    'adaptive_thresh_win_size_max_px': 23,
    'bit_sample_px_per_cell': 4,
    'bit_ignored_margin_per_cell': 0.13,
}


def launch_setup(context):
    camera_to_calibrate = get_camera_to_calibrate(context)
    camera = camera_to_calibrate.camera_name
    params_file_paths = get_params_file_paths(context)
    projector_center_argument = LaunchConfiguration('projector_center').perform(context)
    if projector_center_argument not in ('true', 'false'):
        raise RuntimeError(f'[projection_calibration.launch]: '
                           f'projector_center:={projector_center_argument}: use true or false')
    is_projector_center_run = projector_center_argument == 'true'
    # With a measured pose, the calibrator moves the camera into the projected image's world
    camera_pose_file_path = get_path_in_config_folder(
        get_extrinsics_relative_path(context, 'camera_pose', camera))
    projection_calibrator_parameters = [*params_file_paths,
                                        {'projector_center': is_projector_center_run,
                                         'camera_pose_file': camera_pose_file_path}]
    # The same display the projector app gets; without one, the calibrator's own default applies
    projector_display_id = get_projector_display_id(context, read_launch_section(context))
    if projector_display_id is not None:
        projection_calibrator_parameters.append({'display_id': projector_display_id})
    camera_stream_names = read_camera_entry(camera_to_calibrate.camera_type)['streams']
    is_depth_camera = DEPTH_REGISTERED_STREAM_NAME in camera_stream_names
    if is_projector_center_run and not is_depth_camera:
        raise RuntimeError(f'[projection_calibration.launch]: projector_center:=true needs a '
                           f'camera with depth on its colour image ({DEPTH_REGISTERED_STREAM_NAME} '
                           f'in its entry\'s streams), but the camera is {camera}: run it with '
                           f'camera:= set to a camera that offers it')
    fiducials_detector_node = Node(
        package='fiducials_detector',
        executable='fiducials_detector',
        name='fiducials_detector_node',
        namespace=get_camera_namespace(camera),
        output='screen',
        emulate_tty=True,
        # The projector centre needs the markers in 3D (corners_3d)
        parameters=[*params_file_paths,
                    FIDUCIALS_DETECTOR_GENERAL_DETECTION_PARAMETERS,
                    {'use_depth': is_projector_center_run}],
    )
    projection_calibrator_node = Node(
        package='projection_calibration',
        executable='projection_calibrator',
        name='projection_calibrator_node',
        namespace=get_camera_namespace(camera),
        output='screen',
        emulate_tty=True,
        parameters=projection_calibrator_parameters,
        # Stored or failed: the camera and the projector are not needed any longer
        on_exit=Shutdown(reason='projection calibration finished'),
    )
    # The calibration converts camera pixels to the table plane, so the camera pose is needed.
    # Both nodes run in the camera's namespace, /cameras/<camera>, like the camera's sensor nodes
    # and its projection calibration server: their relative names resolve to its streams, its
    # fiducials and its server, and they get the parameter sections /cameras/*/<node>
    return [*create_camera_actions(context, camera_to_calibrate),
            fiducials_detector_node,
            *create_projection_calibration_server_node(context, camera),
            projection_calibrator_node]


# Co-authored by Claude Code
def generate_launch_description():
    default_params_file_path = get_installed_par_setup_path()

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params_file_path,
            description='Parameter file describing this physical PAR setup.'),
        create_profile_launch_argument(),
        create_projector_display_id_launch_argument(),
        create_camera_choice_launch_argument(),
        DeclareLaunchArgument(
            'projector_center',
            default_value='false',
            description='true: find the projector centre with a raised board instead of fitting '
                        'the homography. Needs a camera with depth on its colour image and a '
                        'stored mapping.'),
        OpaqueFunction(function=launch_setup),
    ])
