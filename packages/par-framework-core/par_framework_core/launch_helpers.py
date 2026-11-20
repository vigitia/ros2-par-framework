# Written by Claude Code
"""
Launch arguments and launch actions shared by the launch files of a PAR setup.

Only this module reads the launch context: the functions that take it are used inside
OpaqueFunction(function=...), because they need the resolved value of a launch argument
(params_file, profile, camera, projector_display_id) to decide how a node is started. They pass
the values on to the modules that hold the logic and import nothing from launch: setup_files,
par_launch_cameras, camera_types, camera_poses, par_apps, sensor_nodes and connected_displays.
"""

import os

from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.camera_poses import (get_camera_tf_publisher_name,
                                             get_invalid_pose_keys,
                                             OPTICAL_FRAME_ROTATION_QUATERNION_XYZW,
                                             PLACEHOLDER_CAMERA_POSE_SECTION_NAME,
                                             POSE_ROTATION_KEYS, POSE_TRANSLATION_KEYS,
                                             read_published_camera_pose)
from par_framework_core.camera_types import (CAMERA_ENTRY_INTRINSICS_KEY,
                                             CAMERA_INTRINSICS_SOURCE_CALIBRATABLE,
                                             CAMERA_RESOURCE_TYPE, CAMERA_STREAM_NAMES,
                                             get_camera_body_frame_id,
                                             get_camera_launch_file_path,
                                             get_camera_type_params_file_paths,
                                             read_camera_entry)
from par_framework_core.connected_displays import find_profile_projector_display_id
from par_framework_core.par_launch_cameras import (get_camera_namespace,
                                                   PAR_LAUNCH_CAMERAS_KEY, parse_camera_unit_text,
                                                   ProfileCamera, read_profile_cameras)
from par_framework_core.setup_files import (check_profile_name, create_folder_of_file,
                                            FOLDER_PATH_PROFILES, get_extrinsics_relative_path,
                                            get_params_file_paths_of_profile,
                                            get_path_in_config_folder,
                                            get_unit_intrinsics_file_path, read_launch_section)


# Each camera's projection calibration server publishes and serves these below the camera's
# namespace, because corners and mapping hold for one camera only (relative names, as the streams)
CAMERA_PROJECTION_CALIBRATION_NAMES = ('projection_corners', 'projection_mapping',
                                       'set_projection_corners', 'set_projection_mapping')
# The launch arguments every camera launch file declares (README.md of par_framework_core)
CAMERA_LAUNCH_ARGUMENT_NAMES = ('namespace', 'camera_name', 'serial', 'camera_info_url',
                                'params_files')
# The camera launch arguments with a default, so a camera launch file can also be started alone
OPTIONAL_CAMERA_LAUNCH_ARGUMENT_NAMES = ('serial', 'camera_info_url', 'params_files')


def create_profile_launch_argument():
    """Create the profile launch argument, which every launch file of a setup declares."""
    return DeclareLaunchArgument(
        'profile',
        default_value='',
        description=f'Name of a setup profile: config/{FOLDER_PATH_PROFILES}/<profile>.yaml '
                    f'overrides params_file, and the profile has its own camera pose and '
                    f'projection calibration. Empty uses params_file alone.')


def get_profile_name(context):
    """Return the profile launch argument, or '' without a profile."""
    profile_name = LaunchConfiguration('profile').perform(context)
    check_profile_name(profile_name)
    return profile_name


def get_params_file_paths(context):
    """Return the parameter files in the order ROS applies them: params_file, then the profile."""
    params_file_path = LaunchConfiguration('params_file').perform(context)
    return get_params_file_paths_of_profile(params_file_path, get_profile_name(context))


def create_camera_choice_launch_argument():
    """Create the camera launch argument, read by get_cameras_to_start."""
    return DeclareLaunchArgument(
        'camera',
        default_value='',
        description=f'One camera for this run: <name> of par_launch.{PAR_LAUNCH_CAMERAS_KEY}, or '
                    f'<type>[:<serial>] of a camera the profile does not name (a type installed '
                    f'in the ament index, {CAMERA_RESOURCE_TYPE}, e.g. webcam or '
                    f'blackfly:22260470). Empty starts every camera of par_launch.'
                    f'{PAR_LAUNCH_CAMERAS_KEY}.')


def get_cameras_to_start(context):
    """
    Return the cameras a launch starts, as ProfileCamera tuples; the first one is the main camera.

    Without camera:=, every camera of par_launch.cameras. camera:=<name> starts that camera of
    the profile; camera:=<type>[:<serial>] starts a unit the profile does not name, named after
    its type, e.g. to preview or calibrate it.
    """
    params_file_paths = get_params_file_paths(context)
    camera_argument = context.launch_configurations.get('camera', '')
    if not camera_argument:
        return read_profile_cameras(params_file_paths)
    # A camera:= without a profile list must not fail on the missing list
    if PAR_LAUNCH_CAMERAS_KEY in read_launch_section(params_file_paths):
        for profile_camera in read_profile_cameras(params_file_paths):
            if profile_camera.camera_name == camera_argument:
                return [profile_camera]
    camera_type, serial = parse_camera_unit_text(camera_argument, f'camera:={camera_argument}')
    return [ProfileCamera(camera_type, camera_type, serial)]


def get_camera_to_calibrate(context):
    """Return the one camera a calibration launch measures; camera:= chooses it among several."""
    cameras_to_start = get_cameras_to_start(context)
    if len(cameras_to_start) > 1:
        camera_names_text = ', '.join(camera.camera_name for camera in cameras_to_start)
        raise RuntimeError(f'[launch_helpers]: the profile has several cameras '
                           f'({camera_names_text}): choose the one to calibrate with '
                           f'camera:=<name>')
    return cameras_to_start[0]


def create_projector_display_id_launch_argument():
    """Create the projector_display_id launch argument of every launch that draws on it."""
    return DeclareLaunchArgument(
        'projector_display_id',
        default_value='',
        description='Display of the projector, counted like SDL/pygame (0 = primary), passed to '
                    'the node that draws on it as display_id. Empty finds the projector by the '
                    'identity par_launch stores (EDID make, model, serial, connector), or else '
                    'uses par_launch.projector_display_id from params_file.')


def get_projector_display_id(context, launch_section):
    """
    Return the projector's display (SDL/pygame index), None when nothing sets it.

    projector_display_id:= wins for one run; otherwise the projector par_launch names
    (find_profile_projector_display_id).
    """
    projector_display_id_text = LaunchConfiguration('projector_display_id').perform(context)
    if not projector_display_id_text:
        return find_profile_projector_display_id(launch_section)
    try:
        return int(projector_display_id_text)
    except ValueError:
        raise RuntimeError(f'[launch_helpers]: projector_display_id:={projector_display_id_text}: '
                           f'use the display number, 0 for the primary display')


def create_camera_stream_remappings(camera_name):
    """
    Return the remappings that point a framework node at camera_name's topics and services.

    Its camera streams and its projection calibration (corners, mapping and their set services).
    """
    # Simplification: the framework nodes run in the root namespace, where their relative names
    # would resolve to /image_raw etc. Upgrade (the multi-camera plan): start each node in its
    # camera's namespace, where they resolve without remappings
    camera_namespace = get_camera_namespace(camera_name)
    camera_stream_remappings = []
    for camera_topic_name in CAMERA_STREAM_NAMES + CAMERA_PROJECTION_CALIBRATION_NAMES:
        camera_stream_remappings.append((camera_topic_name,
                                         f'{camera_namespace}/{camera_topic_name}'))
    return camera_stream_remappings


def get_camera_info_url(profile_name, camera_type, serial):
    """Return the file:// URL of a camera unit's intrinsics file, the drivers' camera_info_url."""
    intrinsics_file_path = get_unit_intrinsics_file_path(profile_name, camera_type, serial)
    # The driver writes the file there when a calibration is committed through set_camera_info
    create_folder_of_file(intrinsics_file_path)
    return f'file://{intrinsics_file_path}'


def create_camera_actions(context, profile_camera):
    """
    Create a camera (a ProfileCamera) from its type's entry: its launch file and mount transform.

    The camera runs in /cameras/<camera name>, its frames are named after it, and its unit opens
    with the unit's intrinsics.
    """
    camera_name, camera_type, serial = profile_camera
    camera_entry = read_camera_entry(camera_type)
    launch_file_path = get_camera_launch_file_path(camera_type, camera_entry)
    camera_info_url = ''
    if camera_entry[CAMERA_ENTRY_INTRINSICS_KEY] == CAMERA_INTRINSICS_SOURCE_CALIBRATABLE:
        camera_info_url = get_camera_info_url(get_profile_name(context), camera_type, serial)
    camera_launch_arguments = {
        'namespace': get_camera_namespace(camera_name),
        'camera_name': camera_name,
        'serial': serial,
        'camera_info_url': camera_info_url,
        # The type's defaults first, so the parameter files override them
        'params_files': os.pathsep.join(get_camera_type_params_file_paths(camera_entry)
                                        + get_params_file_paths(context)),
    }
    return [IncludeLaunchDescription(PythonLaunchDescriptionSource(launch_file_path),
                                     launch_arguments=camera_launch_arguments.items()),
            *create_mount_tf_publisher(context, camera_name,
                                       get_camera_body_frame_id(camera_name, camera_entry))]


def create_camera_launch_arguments():
    """Create the launch arguments every camera launch file of this package declares."""
    descriptions = {
        'namespace': 'Namespace of the camera: its streams are <namespace>/image_raw, ...',
        'camera_name': 'Prefix of every TF frame the camera publishes: <camera_name>_link, ...',
        'serial': 'Serial of the unit to open; empty opens the first one found.',
        'camera_info_url': 'file:// URL of the intrinsics; empty for none.',
        'params_files': f'Parameter files joined with {os.pathsep!r}, applied in this order.',
    }
    launch_arguments = []
    for argument_name in CAMERA_LAUNCH_ARGUMENT_NAMES:
        default_value = None
        if argument_name in OPTIONAL_CAMERA_LAUNCH_ARGUMENT_NAMES:
            default_value = ''
        launch_arguments.append(DeclareLaunchArgument(
            argument_name, default_value=default_value,
            description=descriptions[argument_name]))
    return launch_arguments


def read_camera_launch_arguments(context):
    """Return the camera launch arguments as a dict; params_files as a list of paths."""
    camera_launch_argument_values = {}
    for argument_name in CAMERA_LAUNCH_ARGUMENT_NAMES:
        camera_launch_argument_values[argument_name] = LaunchConfiguration(
            argument_name).perform(context)
    params_files_text = camera_launch_argument_values['params_files']
    params_file_paths = []
    if params_files_text:
        params_file_paths = params_files_text.split(os.pathsep)
    camera_launch_argument_values['params_files'] = params_file_paths
    return camera_launch_argument_values


def create_optical_frame_tf_publisher(camera_name, namespace):
    """Create the publisher of <camera_name>_link -> <camera_name>_optical_frame in namespace."""
    # The standard optical frame rotation (REP 103), as drivers that publish it themselves use
    transform_arguments = ['--frame-id', f'{camera_name}_link',
                           '--child-frame-id', f'{camera_name}_optical_frame']
    for axis, quaternion_component in zip('xyzw', OPTICAL_FRAME_ROTATION_QUATERNION_XYZW):
        transform_arguments += [f'--q{axis}', str(quaternion_component)]
    return Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='optical_tf_publisher',
        namespace=namespace,
        arguments=transform_arguments,
    )


def create_mount_tf_publisher(context, camera_name, child_frame_id):
    """
    Create the publisher of world -> child_frame_id: the measured camera pose, or the placeholder.

    The pose is the one read_published_camera_pose returns for camera_name.
    """
    # static_transform_publisher takes its transform only as command-line flags: parameters from
    # a file are overridden by the flags' defaults, and without --frame-id it does not start. So
    # the pose is read from the file here, which is only possible once params_file is known.
    publisher_name = get_camera_tf_publisher_name(camera_name)
    camera_pose, pose_source_text, is_pose_measured = read_published_camera_pose(
        get_params_file_paths(context), get_profile_name(context), camera_name)
    if is_pose_measured:
        fix_hint = ('re-run the camera pose calibration, or delete the file to use the '
                    'placeholder pose in the parameter files')
    else:
        fix_hint = (f'set them under {PLACEHOLDER_CAMERA_POSE_SECTION_NAME} (every camera) or '
                    f'/{publisher_name} (this camera) ros__parameters in the parameter files')
    # Both files can be edited by hand or cut short, and every launch with this camera reads
    # them: a gap is reported here with its file instead of ending as a bare KeyError
    invalid_keys = get_invalid_pose_keys(camera_pose)
    if invalid_keys:
        raise RuntimeError(f'[launch_helpers]: {pose_source_text} has no finite number for '
                           f'{", ".join(invalid_keys)}: {fix_hint}')
    print(f'[launch_helpers]: {publisher_name}: camera pose from {pose_source_text}')
    transform_arguments = ['--frame-id', 'world', '--child-frame-id', child_frame_id]
    for axis, pose_key in zip('xyz', POSE_TRANSLATION_KEYS):
        transform_arguments += [f'--{axis}', str(camera_pose[pose_key])]
    for axis, pose_key in zip('xyzw', POSE_ROTATION_KEYS):
        transform_arguments += [f'--q{axis}', str(camera_pose[pose_key])]
    return [Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name=publisher_name,
        arguments=transform_arguments,
    )]


def create_projection_calibration_server_node(context, camera_name):
    """Create the owner of the projection corners and mapping, with the camera's files."""
    # One file per camera each: the corners are pixels of one camera's image, so another camera's
    # would point elsewhere. And while the camera poses in par_setup.yaml are placeholders, each
    # camera's table plane is its own, so a mapping only fits the camera it was calibrated with.
    # Per profile as well: another setup has another table and projector
    profile_name = get_profile_name(context)
    corners_file_path = get_path_in_config_folder(
        get_extrinsics_relative_path(profile_name, 'projection_corners', camera_name))
    mapping_file_path = get_path_in_config_folder(
        get_extrinsics_relative_path(profile_name, 'projection_mapping', camera_name))
    # The server writes both files when a calibration sets them; they share one folder
    create_folder_of_file(mapping_file_path)
    # In the camera's namespace, so each camera has its own server, topics and services, e.g.
    # /cameras/overhead/projection_mapping
    return [Node(
        package='projection_calibration_server',
        executable='projection_calibration_server',
        name='projection_calibration_server_node',
        namespace=get_camera_namespace(camera_name),
        output='screen',
        emulate_tty=True,
        parameters=[{
            'projection_corners_file': corners_file_path,
            'projection_mapping_file': mapping_file_path,
        }],
    )]
