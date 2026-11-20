"""Calibration run: camera plus the projection corner selector.

Start this once per physical setup to mark the projection area in the camera
image; the resulting corners are what the rest of the framework warps against.
The projector window opens on the projector's display: par_launch.projector_display_id, or
projector_display_id:=<n> for one run (added with the help of Claude Code).
The selected corners are stored by projection_calibration_server_node in
config/calibration/extrinsics/projection_corners_<camera>.yaml (added with the help of Claude
Code).
camera:= chooses the camera when the profile has several, a name of par_launch.cameras (added
with the help of Claude Code), and the launch ends once the corners are
stored or the selection is cancelled with Esc (added with the help of Claude Code).
Camera calibrations are config/calibration/intrinsics/camera_info_<type>[_<serial>].yaml (changed
with the help of Claude Code). With profile:=<name>, the camera calibration and the corners are that
setup's own, in config/calibration/intrinsics/<name>/ and config/calibration/extrinsics/<name>/
(added with the help of Claude Code).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (create_camera_actions,
                                               create_camera_choice_launch_argument,
                                               create_camera_stream_remappings,
                                               create_profile_launch_argument,
                                               create_projection_calibration_server_node,
                                               create_projector_display_id_launch_argument,
                                               get_camera_to_calibrate,
                                               get_installed_par_setup_path, get_params_file_paths,
                                               get_projector_display_id, read_launch_section)


# Written by Claude Code; the remappings of the camera streams and the projector display
# co-authored by Claude Code
def create_camera_and_projection_corner_selector(context):
    """Create the chosen camera, the projection corner selector on its image, the corners owner."""
    camera_to_calibrate = get_camera_to_calibrate(context)
    camera = camera_to_calibrate.camera_name
    projection_corner_selector_parameters = get_params_file_paths(context)
    # The same display the projector app and the projection calibration get; without one, the
    # selector's own default applies
    projector_display_id = get_projector_display_id(context, read_launch_section(context))
    if projector_display_id is not None:
        projection_corner_selector_parameters.append({'display_id': projector_display_id})
    projection_corner_selector_node = Node(
        package='projection_calibration',
        executable='projection_corner_selector',
        name='projection_corner_selector_node',
        output='screen',
        emulate_tty=True,
        parameters=projection_corner_selector_parameters,
        # Its relative camera stream names point at the camera started here
        remappings=create_camera_stream_remappings(camera),
        # Corners stored (projection_calibration_server_node writes them before it answers) or
        # selection cancelled: the camera and the corners owner are not needed any longer
        on_exit=Shutdown(reason='projection corners selected'),
    )
    # The corners owner stores what projection_corner_selector sends, in the camera's own file, and
    # publishes it on /cameras/<camera>/projection_corners
    return [*create_camera_actions(context, camera_to_calibrate),
            *create_projection_calibration_server_node(context, camera),
            projection_corner_selector_node]


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

        OpaqueFunction(function=create_camera_and_projection_corner_selector),
    ])
