# Co-authored by Claude Code: written by Claude Code, since edited by hand; Claude Code also added
# the setup profiles (profile launch argument, merged parameter files, per-profile extrinsics,
# per-unit Brio intrinsics, per-profile intrinsics and extrinsics), the PAR app entries in the
# ament index, and the camera types registered there, each started by its own launch file
"""
Start functions shared by the launch files of par_framework_core.

Those that take the launch context are used inside OpaqueFunction(function=...), because they
need the resolved value of a launch argument (params_file, profile, camera) to decide how the node
is started.
"""

import math
import os
import re

from ament_index_python.packages import get_package_share_directory
from ament_index_python.resources import get_resource, get_resources
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.connected_displays import (find_projector_display_ids,
                                                   get_projector_identity_title_text,
                                                   PROJECTOR_IDENTITY_PARAMETER_NAMES,
                                                   read_connected_displays)
import yaml


# Co-authored by Claude Code: the streams a camera may offer, named relative to its namespace by
# the image_pipeline convention. Framework nodes subscribe to them by these relative names; a
# camera's launch file maps its driver's own names onto them below the camera's namespace
CAMERA_STREAM_NAMES = ('image_raw', 'image_raw/compressed', 'camera_info', 'set_camera_info',
                       'depth_registered/image_raw', 'ir/image_raw', 'depth_sensor/ir/image_raw',
                       'depth_sensor/depth/image_raw', 'depth_sensor/camera_info', 'events')
# Every camera runs in CAMERAS_NAMESPACE/<camera name>, e.g. /cameras/blackfly
CAMERAS_NAMESPACE = '/cameras'

# Camera types register in the ament index under this resource type, like PAR apps: a marker file
# share/ament_index/resource_index/par_framework_cameras/<camera type> whose content is the type's
# entry, a YAML mapping (blueprint and format: templates/par_camera/ of ros2-par-framework). The
# entry names the launch file that starts the driver; core never knows a driver itself
CAMERA_RESOURCE_TYPE = 'par_framework_cameras'
CAMERA_ENTRY_TEXT_KEYS = ('display_name', 'description')
# package and launch_file: the launch file is share/<package>/launch/<launch_file>
CAMERA_ENTRY_NAME_KEYS = ('package', 'launch_file')
# The child frame of the camera's mount transform is <camera name>_<body_frame>
CAMERA_ENTRY_BODY_FRAME_KEY = 'body_frame'
CAMERA_ENTRY_STREAMS_KEY = 'streams'
# calibratable: intrinsics file per unit, written by run_cameracalibrator.sh; factory: the driver
# publishes its own; none: no camera_info
CAMERA_ENTRY_INTRINSICS_KEY = 'intrinsics'
CAMERA_INTRINSICS_SOURCES = ('calibratable', 'factory', 'none')
# The launch arguments every camera launch file declares (templates/par_camera/)
CAMERA_LAUNCH_ARGUMENT_NAMES = ('namespace', 'camera_name', 'serial', 'camera_info_url',
                                'params_files')

# The machine-local calibrations below config/ (gitignored), for get_path_in_config_folder: the
# camera intrinsics, and where camera and projection sit relative to the table
FOLDER_PATH_CAMERA_INTRINSICS = 'calibration/intrinsics'
FOLDER_PATH_EXTRINSICS = 'calibration/extrinsics'
# Setup profiles below config/ (gitignored): profiles/<name>.yaml holds only what differs from
# params_file, and each profile keeps its calibrations in FOLDER_PATH_CAMERA_INTRINSICS/<name> and
# FOLDER_PATH_EXTRINSICS/<name>
FOLDER_PATH_PROFILES = 'profiles'
# Profile names and camera serials become parts of file names: nothing that could leave the folder
FILE_NAME_PART_PATTERN = re.compile(r'[A-Za-z0-9_-]+')
CAPTURE_CAMERA_NODE_PARAMETERS_KEY = '/capture_camera/blackfly'
# Driver mapping of the capture camera's ROS parameters onto its settings, next to par_setup.yaml
CAPTURE_CAMERA_SETTINGS_MAPPING_FILE_NAME = 'blackfly_s_software_trigger.yaml'
# The cameras whose driver opens one unit by its serial: the driver's node name (its section in
# the parameter files is /cameras/<camera name>/<node name>) and its serial parameter, which also
# make the intrinsics file name per unit. Special case: ROS has no convention for a serial
# parameter. Simplification until the profile lists its cameras as type:serial (multi-camera
# plan, step 4); then only each camera's launch file knows the parameter name
CAMERA_SERIAL_SOURCE_BY_CAMERA = {
    'brio': ('logitech_brio_node', 'serial'),
    'cu40': ('see3cam_cu40_node', 'serial'),
    'blackfly': ('blackfly', 'serial_number'),
    'kinect': ('k4a_ros_device_node', 'sensor_sn'),
    'realsense': ('realsense', 'serial_no'),
}
# Launch argument that names the unit of camera:= to open for one run, instead of the serial in
# the parameter files, e.g. to preview a unit before a profile names it
CAMERA_SERIAL_LAUNCH_ARGUMENT_NAME = 'camera_serial'
# par_launch key listing the cameras beyond par_launch.camera that the setup wizard configured and
# calibrated, as '<camera>' or '<camera>:<serial>'. Only par_launch.camera is started
ADDITIONAL_CAMERAS_KEY = 'additional_cameras'
# What a camera pose needs, in the measured camera_pose_<camera>.yaml and in the placeholder
POSE_TRANSLATION_KEYS = [f'translation.{axis}' for axis in 'xyz']
POSE_ROTATION_KEYS = [f'rotation.{axis}' for axis in 'xyzw']
CAMERA_POSE_KEYS = POSE_TRANSLATION_KEYS + POSE_ROTATION_KEYS

# PAR apps register in the ament index under this resource type: an installed marker file
# share/ament_index/resource_index/par_framework_apps/<package> whose content is the app's entry,
# a YAML mapping (blueprint and format: templates/par_app/ of ros2-par-framework)
PAR_APP_RESOURCE_TYPE = 'par_framework_apps'
PAR_APP_ENTRY_TEXT_KEYS = ('display_name', 'description')
PAR_APP_ENTRY_START_KEYS = ('executable', 'launch_file')
PAR_APP_ENTRY_LIST_KEYS = ('required_launch_switches', 'used_calibrations', 'settings_node_names')
# executable and launch_file: a name in the app's package, no path and no leading dot (not '..')
PAR_APP_START_NAME_PATTERN = re.compile(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*')
# settings_node_names: the app's nodes whose parameters the setup wizard edits, as full ROS node
# names (namespace and name), e.g. /demo_app_node
PAR_APP_FULL_NODE_NAME_PATTERN = re.compile(r'(/[A-Za-z_][A-Za-z0-9_]*)+')
# What used_calibrations may name, so a misspelt name fails instead of never being reported missing
PAR_APP_CALIBRATION_NAMES = ('camera_intrinsics', 'camera_pose', 'projection_mapping',
                             'projector_center')
# par_launch.projector_app chooses the one app on the projector: none, the rendering manager or a
# PAR app's package. The rendering manager has no entry in the index yet, since it has no launch
# file of its own; par.launch.py starts it by its own code until it has.
PROJECTOR_APP_NONE = 'none'
RENDERING_MANAGER_APP_NAME = 'rendering_manager'

# Sensor processing nodes (detectors, page_locator, projection_mask, ...) register in the ament
# index under this resource type, like PAR apps: share/ament_index/resource_index/
# par_framework_sensor_nodes/<package> holds the node's entry, a YAML mapping (blueprint:
# templates/sensor_processing_node_entry.yaml of ros2-par-framework). The package name is its
# par_launch switch; par.launch.py starts its executable of the same name as node <package>_node.
SENSOR_NODE_RESOURCE_TYPE = 'par_framework_sensor_nodes'
SENSOR_NODE_ENTRY_TEXT_KEYS = ('display_name', 'description')
SENSOR_NODE_ENTRY_LIST_KEYS = ('required_sensor_nodes',)


# Co-authored by Claude Code: names of the function, its parameter and its variables
def get_path_in_config_folder(relative_path):
    """Return the absolute path of relative_path below the folder of the real par_setup.yaml."""
    # The default par_setup.yaml, not params_file: the calibrations are shared by every parameter
    # file. realpath follows the --symlink-install links back to the source folder, so files
    # written there survive rebuilds
    installed_par_setup_path = os.path.join(get_package_share_directory('par_framework_core'),
                                            'config', 'par_setup.yaml')
    config_folder_path = os.path.dirname(os.path.realpath(installed_par_setup_path))
    absolute_path = os.path.join(config_folder_path, relative_path)
    # The writers (camera_info_manager, camera_pose_calibrator, ...) open the file without
    # creating its folder
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
    return absolute_path


# Co-authored by Claude Code
def create_profile_launch_argument():
    """Create the profile launch argument, which every launch file of a setup declares."""
    return DeclareLaunchArgument(
        'profile',
        default_value='',
        description=f'Name of a setup profile: config/{FOLDER_PATH_PROFILES}/<profile>.yaml '
                    f'overrides params_file, and the profile has its own camera pose and '
                    f'projection calibration. Empty uses params_file alone.')


# Co-authored by Claude Code
def get_profile_name(context):
    """Return the profile launch argument, or '' without a profile."""
    profile_name = LaunchConfiguration('profile').perform(context)
    if profile_name and not FILE_NAME_PART_PATTERN.fullmatch(profile_name):
        raise RuntimeError(f'[launch_helpers]: profile:={profile_name}: use only letters, digits, '
                           f'_ and -, the name of a file in config/{FOLDER_PATH_PROFILES}/ '
                           f'without .yaml')
    return profile_name


# Co-authored by Claude Code
def get_params_file_paths(context):
    """Return the parameter files in the order ROS applies them: params_file, then the profile."""
    params_file_paths = [LaunchConfiguration('params_file').perform(context)]
    profile_name = get_profile_name(context)
    if profile_name:
        profile_path = get_path_in_config_folder(f'{FOLDER_PATH_PROFILES}/{profile_name}.yaml')
        if not os.path.exists(profile_path):
            raise RuntimeError(f'[launch_helpers]: profile {profile_name} has no file '
                               f'{profile_path}: create it with only the sections and keys that '
                               f'differ from par_setup.yaml, written the same way')
        params_file_paths.append(profile_path)
    return params_file_paths


# Co-authored by Claude Code
def read_merged_parameters(context):
    """
    Return the parameter files merged as ROS merges them for a node: the later file wins per key.

    For what the launch files read themselves (par_launch, the placeholder camera poses); the
    nodes get the files from get_params_file_paths and merge them alone.
    """
    merged_parameters = {}
    for params_file_path in get_params_file_paths(context):
        with open(params_file_path) as params_file:
            file_parameters = yaml.safe_load(params_file) or {}
        # A profile is written by hand: a stray list or value would otherwise fail in the merge
        if not isinstance(file_parameters, dict):
            raise RuntimeError(f'[launch_helpers]: {params_file_path} holds no node sections: '
                               f'write it like par_setup.yaml, node name, ros__parameters, keys')
        _merge_parameters(merged_parameters, file_parameters)
    return merged_parameters


# Co-authored by Claude Code
def _merge_parameters(merged_parameters, overriding_parameters):
    """Merge overriding_parameters into merged_parameters, nested sections key by key."""
    # Simplification: keys must be spelt as in par_setup.yaml. ROS also matches a node written
    # without its leading slash or a parameter written nested instead of dotted, this merge does
    # not; upgrade: normalise both before merging
    for key, overriding_value in overriding_parameters.items():
        merged_value = merged_parameters.get(key)
        if isinstance(merged_value, dict) and isinstance(overriding_value, dict):
            _merge_parameters(merged_value, overriding_value)
        else:
            merged_parameters[key] = overriding_value


# Written by Claude Code
def get_intrinsics_folder_path(context):
    """Return the folder of the intrinsics below config/: the profile's own, or the shared one."""
    # Per profile, so recalibrating a camera for one setup (e.g. after refocusing it) leaves the
    # other setups' calibrations alone
    profile_name = get_profile_name(context)
    if profile_name:
        return f'{FOLDER_PATH_CAMERA_INTRINSICS}/{profile_name}'
    return FOLDER_PATH_CAMERA_INTRINSICS


# Written by Claude Code
def get_camera_info_url(context, camera_info_file_name):
    """Return the file:// URL of a camera's intrinsics file, the drivers' camera_info_url."""
    intrinsics_folder_path = get_intrinsics_folder_path(context)
    camera_info_path = get_path_in_config_folder(
        f'{intrinsics_folder_path}/{camera_info_file_name}')
    return f'file://{camera_info_path}'


# Co-authored by Claude Code
def get_extrinsics_folder_path(context):
    """Return the folder of the extrinsics below config/: the profile's own, or the shared one."""
    profile_name = get_profile_name(context)
    if profile_name:
        return f'{FOLDER_PATH_EXTRINSICS}/{profile_name}'
    return FOLDER_PATH_EXTRINSICS


# Co-authored by Claude Code
def create_camera_serial_launch_argument():
    """Create the camera_serial launch argument of a launch that starts a camera by serial."""
    return DeclareLaunchArgument(
        CAMERA_SERIAL_LAUNCH_ARGUMENT_NAME,
        default_value='',
        description='Serial of the unit of camera:= to open for this run, e.g. to preview a unit '
                    'no profile names yet. Empty uses the serial in the parameter files.')


# Co-authored by Claude Code
def get_camera_serial_launch_argument(context):
    """Return camera_serial:= of this launch, '' when it is empty or the launch has none."""
    # Not every launch file declares it, so it is looked up instead of performed
    return context.launch_configurations.get(CAMERA_SERIAL_LAUNCH_ARGUMENT_NAME, '')


# Co-authored by Claude Code: the camera units of a profile, told apart by serial
def get_camera_serial(context, camera):
    """
    Return the serial of the unit of this camera type the launch opens, or ''.

    camera_serial:= wins for one run, otherwise the serial the parameter files name.
    """
    if camera not in CAMERA_SERIAL_SOURCE_BY_CAMERA:
        return ''
    driver_node_name, serial_parameter_name = CAMERA_SERIAL_SOURCE_BY_CAMERA[camera]
    # Simplification: the camera's name is its type until profiles name their cameras
    node_parameters_key = f'{get_camera_namespace(camera)}/{driver_node_name}'
    serial = get_camera_serial_launch_argument(context)
    serial_source_text = f'{CAMERA_SERIAL_LAUNCH_ARGUMENT_NAME}:='
    if not serial:
        node_section = read_merged_parameters(context).get(node_parameters_key) or {}
        node_parameters = node_section.get('ros__parameters') or {}
        serial = str(node_parameters.get(serial_parameter_name, ''))
        serial_source_text = f'{serial_parameter_name} under {node_parameters_key}'
    if serial and not FILE_NAME_PART_PATTERN.fullmatch(serial):
        raise RuntimeError(f'[launch_helpers]: {camera} {serial_source_text} {serial!r} is no '
                           f'serial number: use only letters, digits, _ and -')
    return serial


# Co-authored by Claude Code
def get_additional_camera_units(context):
    """Return par_launch.additional_cameras as a list of (camera, serial); serial may be ''."""
    launch_section = read_launch_section(context)
    camera_unit_texts = launch_section.get(ADDITIONAL_CAMERAS_KEY) or []
    camera_units = []
    for camera_unit_text in camera_unit_texts:
        camera, _, serial = str(camera_unit_text).partition(':')
        camera_units.append((camera, serial))
    return camera_units


# Co-authored by Claude Code: the one identifier of a camera unit
def get_camera_id(camera, serial):
    """
    Return the identifier of a camera unit: '<camera>_<serial>', or '<camera>' without a serial.

    It ends the name of every file that belongs to one unit (intrinsics, camera pose, projection
    mapping and corners), so two units of one type never share or overwrite a file.
    """
    if not serial:
        return camera
    return f'{camera}_{serial}'


# Co-authored by Claude Code: calibration files per camera unit
def get_extrinsics_relative_path(context, file_prefix, camera, serial=None):
    """
    Return the extrinsics file <file_prefix>_<camera id>.yaml of a camera unit.

    file_prefix is camera_pose, projection_mapping or projection_corners. serial None means the
    unit the parameter files name (the one par_launch.camera starts).
    """
    if serial is None:
        serial = get_camera_serial(context, camera)
    camera_id = get_camera_id(camera, serial)
    return f'{get_extrinsics_folder_path(context)}/{file_prefix}_{camera_id}.yaml'


# Co-authored by Claude Code: reads the merged parameter files
def read_launch_section(context):
    """Return the par_launch section of the parameter files: the camera and which nodes run."""
    return read_merged_parameters(context)['par_launch']['ros__parameters']


# Co-authored by Claude Code
def create_projector_display_id_launch_argument():
    """Create the projector_display_id launch argument of every launch that draws on it."""
    return DeclareLaunchArgument(
        'projector_display_id',
        default_value='',
        description='Display of the projector, counted like SDL/pygame (0 = primary), passed to '
                    'the node that draws on it as display_id. Empty finds the projector by the '
                    'identity par_launch stores (EDID make, model, serial, connector), or else '
                    'uses par_launch.projector_display_id from params_file.')


# Co-authored by Claude Code: looks the projector up by its stored identity
def get_projector_display_id(context, launch_section):
    """
    Return the projector's display (SDL/pygame index), None when nothing sets it.

    projector_display_id:= wins for one run. Otherwise, when par_launch stores the projector's
    identity (written by the setup wizard), the display with that identity: the index changes
    when displays are plugged in or out, the identity does not. Without one,
    par_launch.projector_display_id as it is. Raises RuntimeError naming the fix when the
    projector with the stored identity is not connected or cannot be told apart.
    """
    projector_display_id_text = LaunchConfiguration('projector_display_id').perform(context)
    if projector_display_id_text:
        try:
            return int(projector_display_id_text)
        except ValueError:
            raise RuntimeError(f'[launch_helpers]: projector_display_id:='
                               f'{projector_display_id_text}: use the display number, 0 for the '
                               f'primary display')
    stored_projector_display_id = read_stored_projector_display_id(launch_section)
    projector_identity = read_projector_identity(launch_section)
    if not projector_identity:
        return stored_projector_display_id

    matching_display_ids = find_projector_display_ids(read_connected_displays(),
                                                      projector_identity)
    projector_title_text = get_projector_identity_title_text(projector_identity)
    if len(matching_display_ids) == 1:
        found_projector_display_id = matching_display_ids[0]
        if found_projector_display_id != stored_projector_display_id:
            print(f'[launch_helpers]: the projector {projector_title_text} is display '
                  f'{found_projector_display_id} now, not par_launch.projector_display_id '
                  f'{stored_projector_display_id}; using display {found_projector_display_id}')
        return found_projector_display_id
    fix_hint = ('connect it, choose the projector again in the setup wizard (Overview), or pass '
                'projector_display_id:=<n> for one run')
    if not matching_display_ids:
        raise RuntimeError(f'[launch_helpers]: the projector of the profile, '
                           f'{projector_title_text}, is not connected: {fix_hint}')
    raise RuntimeError(f'[launch_helpers]: displays {matching_display_ids} all look like the '
                       f'projector of the profile, {projector_title_text}: {fix_hint}')


# Co-authored by Claude Code
def read_stored_projector_display_id(launch_section):
    """Return par_launch.projector_display_id as written, None when the profile sets none."""
    stored_projector_display_id = launch_section.get('projector_display_id')
    # A profile is written by hand; YAML reads true as a bool, which is an int in Python
    is_display_number = isinstance(stored_projector_display_id, int) and not isinstance(
        stored_projector_display_id, bool)
    if stored_projector_display_id is not None and not is_display_number:
        raise RuntimeError(f'[launch_helpers]: par_launch.projector_display_id: '
                           f'{stored_projector_display_id!r}: use the display number, 0 for the '
                           f'primary display')
    return stored_projector_display_id


# Written by Claude Code
def read_projector_identity(launch_section):
    """
    Return the projector's stored identity, {parameter name: text}, or {} when none is stored.

    The keys are connected_displays.PROJECTOR_IDENTITY_PARAMETER_NAMES in par_launch; an empty
    value means the projector does not report it.
    """
    projector_identity = {}
    for parameter_name in PROJECTOR_IDENTITY_PARAMETER_NAMES:
        # str(): YAML reads a serial of digits written by hand as a number
        projector_identity[parameter_name] = str(launch_section.get(parameter_name, '') or '')
    if not any(projector_identity.values()):
        return {}
    return projector_identity


# Co-authored by Claude Code: the camera types come from the ament index
def get_chosen_camera(context):
    """Return the camera launch argument, or else the camera of the parameter files' par_launch."""
    camera = LaunchConfiguration('camera').perform(context)
    if not camera:
        camera = read_launch_section(context)['camera']
    # Without this, an empty or misspelt camera would end as a KeyError deep in a launch file
    camera_type_names = get_camera_type_names()
    if camera not in camera_type_names:
        camera_type_names_text = ', '.join(camera_type_names) or 'none'
        raise RuntimeError(f'[launch_helpers]: unknown camera {camera!r}: pass camera:= with one '
                           f'of the installed camera types ({camera_type_names_text}), or set '
                           f'par_launch.camera in the params_file. A camera type is installed '
                           f'with the package that registers it ({CAMERA_RESOURCE_TYPE})')
    return camera


# Written by Claude Code
def get_camera_namespace(camera_name):
    """Return the namespace a camera runs in: /cameras/<camera name>."""
    return f'{CAMERAS_NAMESPACE}/{camera_name}'


# Written by Claude Code
def create_camera_stream_remappings(camera_name):
    """Return the remappings that point a framework node's camera streams at camera_name."""
    # Simplification: the framework nodes run in the root namespace, where their relative stream
    # names would resolve to /image_raw etc. Upgrade (the multi-camera plan): start each node in
    # its camera's namespace, where they resolve without remappings
    camera_namespace = get_camera_namespace(camera_name)
    camera_stream_remappings = []
    for stream_name in CAMERA_STREAM_NAMES:
        camera_stream_remappings.append((stream_name, f'{camera_namespace}/{stream_name}'))
    return camera_stream_remappings


# Written by Claude Code
def get_camera_type_names():
    """Return the camera types registered in the ament index, sorted."""
    return sorted(get_resources(CAMERA_RESOURCE_TYPE))


# Written by Claude Code
def read_camera_entry(camera_type):
    """
    Return the checked entry of an installed camera type, a dict with every key of the format.

    Raises RuntimeError naming the fix when the type is not installed or its entry is malformed.
    """
    entry = _read_ament_index_entry(CAMERA_RESOURCE_TYPE, camera_type, 'camera type',
                                    get_camera_type_names(), 'templates/par_camera/')
    error_start_text = (f'[launch_helpers]: the camera entry of {camera_type} '
                        f'(share/ament_index/resource_index/{CAMERA_RESOURCE_TYPE}/{camera_type})')
    other_keys = (CAMERA_ENTRY_BODY_FRAME_KEY, CAMERA_ENTRY_STREAMS_KEY,
                  CAMERA_ENTRY_INTRINSICS_KEY)
    known_keys = CAMERA_ENTRY_TEXT_KEYS + CAMERA_ENTRY_NAME_KEYS + other_keys
    unknown_keys = sorted(set(entry) - set(known_keys))
    if unknown_keys:
        raise RuntimeError(f'{error_start_text} has unknown keys {unknown_keys}; known: '
                           f'{list(known_keys)}')
    for text_key in CAMERA_ENTRY_TEXT_KEYS:
        if not isinstance(entry.get(text_key), str):
            raise RuntimeError(f'{error_start_text} needs {text_key} as text')
    # A package, a file in it and a frame name part, never a path that could point elsewhere
    for name_key in CAMERA_ENTRY_NAME_KEYS + (CAMERA_ENTRY_BODY_FRAME_KEY,):
        name_value = entry.get(name_key)
        if not isinstance(name_value, str) or not PAR_APP_START_NAME_PATTERN.fullmatch(name_value):
            raise RuntimeError(f'{error_start_text}: {name_key} must be a plain name without a '
                               f'path, e.g. blackfly.launch.py or link')
    streams = entry.get(CAMERA_ENTRY_STREAMS_KEY)
    is_list_of_texts = isinstance(streams, list) and all(
        isinstance(stream_name, str) for stream_name in streams)
    if not is_list_of_texts:
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_STREAMS_KEY} must be a list of '
                           f'stream names')
    unknown_stream_names = sorted(set(streams) - set(CAMERA_STREAM_NAMES))
    if unknown_stream_names:
        raise RuntimeError(f'{error_start_text}: unknown {CAMERA_ENTRY_STREAMS_KEY} '
                           f'{unknown_stream_names}; known: {list(CAMERA_STREAM_NAMES)}')
    if entry.get(CAMERA_ENTRY_INTRINSICS_KEY) not in CAMERA_INTRINSICS_SOURCES:
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_INTRINSICS_KEY} must be one of '
                           f'{list(CAMERA_INTRINSICS_SOURCES)}')

    checked_entry = {}
    for known_key in known_keys:
        checked_entry[known_key] = entry[known_key]
    checked_entry[CAMERA_ENTRY_STREAMS_KEY] = list(streams)
    return checked_entry


# Written by Claude Code
def get_camera_body_frame_id(camera_name, camera_entry):
    """Return the camera's body frame, the child of its mount transform: <name>_<body_frame>."""
    return f'{camera_name}_{camera_entry[CAMERA_ENTRY_BODY_FRAME_KEY]}'


# Written by Claude Code
def create_camera_actions(context, camera_type):
    """
    Create a camera of camera_type from its entry: its launch file and its mount transform.

    The camera runs in /cameras/<camera name>; its name is its type for now.
    """
    # Simplification: one camera per run, named after its type, until profiles name their
    # cameras (multi-camera plan, step 4)
    camera_name = camera_type
    camera_entry = read_camera_entry(camera_type)
    launch_file_path = os.path.join(get_package_share_directory(camera_entry['package']),
                                    'launch', camera_entry['launch_file'])
    if not os.path.isfile(launch_file_path):
        raise RuntimeError(f'[launch_helpers]: the camera type {camera_type} names the launch file '
                           f'{launch_file_path}, which is not installed: install launch/ in the '
                           f'setup.py data_files of {camera_entry["package"]} '
                           f'(templates/par_camera/) and run ./scripts/local_build.sh')
    serial = get_camera_serial(context, camera_type)
    camera_info_url = ''
    if camera_entry[CAMERA_ENTRY_INTRINSICS_KEY] == 'calibratable':
        camera_info_url = get_camera_info_url(
            context, get_camera_info_file_name_of_unit(camera_type, serial))
    camera_launch_arguments = {
        'namespace': get_camera_namespace(camera_name),
        'camera_name': camera_name,
        'serial': serial,
        'camera_info_url': camera_info_url,
        'params_files': os.pathsep.join(get_params_file_paths(context)),
    }
    return [IncludeLaunchDescription(PythonLaunchDescriptionSource(launch_file_path),
                                     launch_arguments=camera_launch_arguments.items()),
            *create_mount_tf_publisher(context, f'{camera_name}_tf_publisher',
                                       get_camera_body_frame_id(camera_name, camera_entry))]


# Written by Claude Code
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
        # Optional ones, so the file can also be started alone
        if argument_name in ('serial', 'camera_info_url', 'params_files'):
            default_value = ''
        launch_arguments.append(DeclareLaunchArgument(
            argument_name, default_value=default_value,
            description=descriptions[argument_name]))
    return launch_arguments


# Written by Claude Code
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


# Co-authored by Claude Code: one function for every camera whose driver takes a serial
def get_camera_info_file_name(context, camera, node_parameters_key, serial_parameter_name):
    """Return the camera's intrinsics file name: per unit when its serial is set, else shared."""
    # The intrinsics belong to the lens, so each unit has its own; without a serial the shared
    # file is only unambiguous with one unit in use
    node_section = read_merged_parameters(context).get(node_parameters_key) or {}
    node_parameters = node_section.get('ros__parameters') or {}
    serial = str(node_parameters.get(serial_parameter_name, ''))
    if not serial:
        return f'camera_info_{camera}.yaml'
    if not FILE_NAME_PART_PATTERN.fullmatch(serial):
        raise RuntimeError(f'[launch_helpers]: {camera} {serial_parameter_name} {serial!r} under '
                           f'{node_parameters_key} is no serial number: use only letters, '
                           f'digits, _ and -')
    return get_camera_info_file_name_of_unit(camera, serial)


# Co-authored by Claude Code
def get_camera_info_file_name_of_unit(camera, serial):
    """Return the intrinsics file name of one unit: camera_info_<camera id>.yaml."""
    return f'camera_info_{get_camera_id(camera, serial)}.yaml'


# Written by Claude Code
def create_capture_camera_node(context):
    """
    Create the capture camera, a second Blackfly S in software trigger mode.

    It runs as /capture_camera/blackfly. Not remapped onto /camera/..., so it runs next to the main camera. No transforms yet: nothing
    maps its pixels onto the table so far.
    """
    node_section = read_merged_parameters(context).get(CAPTURE_CAMERA_NODE_PARAMETERS_KEY) or {}
    node_parameters = node_section.get('ros__parameters') or {}
    if not str(node_parameters.get('serial_number', '')):
        raise RuntimeError(f'[launch_helpers]: capture_camera needs serial_number under '
                           f'{CAPTURE_CAMERA_NODE_PARAMETERS_KEY} ros__parameters in the '
                           f'parameter files; without it the driver opens whichever Blackfly it finds '
                           f'first, possibly the main camera')
    # Same file name as for the main Blackfly: the intrinsics belong to the unit, whichever role
    # it has, in the profile's intrinsics folder
    camera_info_file_name = get_camera_info_file_name(
        context, 'blackfly', CAPTURE_CAMERA_NODE_PARAMETERS_KEY, 'serial_number')
    camera_info_url = get_camera_info_url(context, camera_info_file_name)
    camera_settings_mapping_path = os.path.join(
        get_package_share_directory('par_framework_core'), 'config',
        CAPTURE_CAMERA_SETTINGS_MAPPING_FILE_NAME)
    return Node(
        package='spinnaker_camera_driver',
        executable='camera_driver_node',
        name='blackfly',
        namespace='/capture_camera',
        output='screen',
        emulate_tty=True,
        parameters=[*get_params_file_paths(context),
                    {'parameter_file': camera_settings_mapping_path,
                     'camerainfo_url': camera_info_url,
                     'frame_id': 'capture_camera_optical_frame'}],
    )


# Co-authored by Claude Code: one transform for every driver that does not publish it itself,
# named after the camera
def create_optical_frame_tf_publisher(camera_name, namespace):
    """Create the publisher of <camera_name>_link -> <camera_name>_optical_frame in namespace."""
    # What the Brio node publishes itself: z forward, y down (REP 103), roll -90, yaw -90 deg
    return Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='optical_tf_publisher',
        namespace=namespace,
        arguments=['--frame-id', f'{camera_name}_link',
                   '--child-frame-id', f'{camera_name}_optical_frame',
                   '--qx', '-0.5', '--qy', '0.5', '--qz', '-0.5', '--qw', '0.5'],
    )


# Co-authored by Claude Code: checks the pose before it is used, reads the profile's files,
# variable names
def create_mount_tf_publisher(context, publisher_name, child_frame_id):
    """
    Create the publisher of world -> child_frame_id: the measured camera pose, or the placeholder.

    The placeholder is stored under /<publisher_name> in the parameter files. The measurement is
    camera_pose_<camera>.yaml in the profile's extrinsics folder, written by
    camera_pose_calibrator (<camera> is <publisher_name> without _tf_publisher), and is used while
    that file exists.
    """
    # static_transform_publisher takes its transform only as command-line flags: parameters from
    # a file are overridden by the flags' defaults, and without --frame-id it does not start. So
    # the pose is read from the file here, which is only possible once params_file is known.
    camera = publisher_name.removesuffix('_tf_publisher')
    measured_pose_relative_path = get_extrinsics_relative_path(context, 'camera_pose', camera)
    pose_source_path = get_path_in_config_folder(measured_pose_relative_path)
    if os.path.exists(pose_source_path):
        with open(pose_source_path) as measured_pose_file:
            camera_pose = yaml.safe_load(measured_pose_file)
        fix_hint = (f're-run the camera pose calibration, or delete the file to use the '
                    f'placeholder /{publisher_name} in the parameter files')
    else:
        pose_source_path = ' + '.join(get_params_file_paths(context))
        publisher_section = read_merged_parameters(context).get(f'/{publisher_name}') or {}
        camera_pose = publisher_section.get('ros__parameters')
        fix_hint = f'set them under /{publisher_name} ros__parameters in the parameter files'
    # Both files can be edited by hand or cut short, and every launch with this camera reads
    # them: a gap is reported here with its file instead of ending as a bare KeyError
    invalid_keys = get_invalid_pose_keys(camera_pose)
    if invalid_keys:
        raise RuntimeError(f'[launch_helpers]: {pose_source_path} has no finite number for '
                           f'{", ".join(invalid_keys)}: {fix_hint}')
    print(f'[launch_helpers]: {publisher_name}: camera pose from {pose_source_path}')
    transform_arguments = ['--frame-id', 'world', '--child-frame-id', child_frame_id]
    for axis in 'xyz':
        transform_arguments += [f'--{axis}', str(camera_pose[f'translation.{axis}'])]
    for axis in 'xyzw':
        transform_arguments += [f'--q{axis}', str(camera_pose[f'rotation.{axis}'])]
    return [Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name=publisher_name,
        arguments=transform_arguments,
    )]


# Co-authored by Claude Code
def get_invalid_pose_keys(pose):
    """Return the CAMERA_POSE_KEYS that pose lacks or that hold no finite number."""
    if not isinstance(pose, dict):
        return list(CAMERA_POSE_KEYS)
    invalid_keys = []
    for pose_key in CAMERA_POSE_KEYS:
        pose_value = pose.get(pose_key)
        # bool is a subclass of int in Python, but true is no coordinate
        is_number = isinstance(pose_value, (int, float)) and not isinstance(pose_value, bool)
        if not is_number or not math.isfinite(pose_value):
            invalid_keys.append(pose_key)
    return invalid_keys


# Co-authored by Claude Code: name, the paths in named steps, the profile's extrinsics folder
def create_projection_calibration_server_node(context, camera):
    """Create the owner of the projection corners and mapping, with the camera's files."""
    # One file per camera each: the corners are pixels of one camera's image, so another camera's
    # would point elsewhere. And while the camera poses in par_setup.yaml are placeholders, each
    # camera's table plane is its own, so a mapping only fits the camera it was calibrated with.
    # Per profile as well: another setup has another table and projector
    corners_relative_path = get_extrinsics_relative_path(context, 'projection_corners', camera)
    mapping_relative_path = get_extrinsics_relative_path(context, 'projection_mapping', camera)
    return [Node(
        package='projection_calibration_server',
        executable='projection_calibration_server',
        name='projection_calibration_server_node',
        output='screen',
        emulate_tty=True,
        parameters=[{
            'projection_corners_file': get_path_in_config_folder(corners_relative_path),
            'projection_mapping_file': get_path_in_config_folder(mapping_relative_path),
        }],
    )]


# Written by Claude Code
def get_par_app_package_names():
    """Return the packages that registered a PAR app in the ament index, sorted."""
    return sorted(get_resources(PAR_APP_RESOURCE_TYPE))


# Written by Claude Code
def read_par_app_entry(app_package_name):
    """
    Return the checked entry of an installed PAR app, a dict with every key of the format.

    executable or launch_file is set, the other one is None; the lists are empty when left out.
    Raises RuntimeError naming the fix when the app is not installed or its entry is malformed.
    """
    error_start_text = (f'[launch_helpers]: the PAR app entry of {app_package_name} '
                        f'(share/ament_index/resource_index/{PAR_APP_RESOURCE_TYPE}/'
                        f'{app_package_name})')
    entry = _read_ament_index_entry(PAR_APP_RESOURCE_TYPE, app_package_name, 'PAR app',
                                    get_par_app_package_names(), 'templates/par_app/')

    known_keys = PAR_APP_ENTRY_TEXT_KEYS + PAR_APP_ENTRY_START_KEYS + PAR_APP_ENTRY_LIST_KEYS
    unknown_keys = sorted(set(entry) - set(known_keys))
    if unknown_keys:
        raise RuntimeError(f'{error_start_text} has unknown keys {unknown_keys}; known: '
                           f'{list(known_keys)}')
    for text_key in PAR_APP_ENTRY_TEXT_KEYS:
        if not isinstance(entry.get(text_key), str):
            raise RuntimeError(f'{error_start_text} needs {text_key} as text')

    given_start_keys = [start_key for start_key in PAR_APP_ENTRY_START_KEYS if start_key in entry]
    if len(given_start_keys) != 1:
        raise RuntimeError(f'{error_start_text} needs exactly one of executable and launch_file')
    start_value = entry[given_start_keys[0]]
    # A file or program name in the package, never a path that could point elsewhere
    if not isinstance(start_value, str) or not PAR_APP_START_NAME_PATTERN.fullmatch(start_value):
        raise RuntimeError(f'{error_start_text}: {given_start_keys[0]} must be a plain name '
                           f'without a path, e.g. example_app or example_app.launch.py')

    for list_key in PAR_APP_ENTRY_LIST_KEYS:
        list_value = entry.get(list_key, [])
        is_list_of_texts = isinstance(list_value, list) and all(
            isinstance(list_item, str) for list_item in list_value)
        if not is_list_of_texts:
            raise RuntimeError(f'{error_start_text}: {list_key} must be a list of names')
    invalid_node_names = []
    for settings_node_name in entry.get('settings_node_names', []):
        if not PAR_APP_FULL_NODE_NAME_PATTERN.fullmatch(settings_node_name):
            invalid_node_names.append(settings_node_name)
    if invalid_node_names:
        raise RuntimeError(f'{error_start_text}: settings_node_names must be full node names '
                           f'such as /example_app_node, not {invalid_node_names}')
    unknown_calibration_names = sorted(
        set(entry.get('used_calibrations', [])) - set(PAR_APP_CALIBRATION_NAMES))
    if unknown_calibration_names:
        raise RuntimeError(f'{error_start_text}: unknown used_calibrations '
                           f'{unknown_calibration_names}; known: '
                           f'{list(PAR_APP_CALIBRATION_NAMES)}')

    checked_entry = {}
    for text_key in PAR_APP_ENTRY_TEXT_KEYS:
        checked_entry[text_key] = entry[text_key]
    for start_key in PAR_APP_ENTRY_START_KEYS:
        checked_entry[start_key] = entry.get(start_key)
    for list_key in PAR_APP_ENTRY_LIST_KEYS:
        checked_entry[list_key] = list(entry.get(list_key, []))
    return checked_entry


# Co-authored by Claude Code
def _read_ament_index_entry(resource_type, package_name, entry_kind_text, installed_names,
                            blueprint_path):
    """
    Return a package's entry under resource_type in the ament index, loaded as a YAML mapping.

    Raises RuntimeError naming the fix when the package has no entry or it is no YAML mapping;
    the caller checks the keys.
    """
    try:
        entry_text, _ = get_resource(resource_type, package_name)
    except LookupError:
        installed_names_text = ', '.join(installed_names) or 'none'
        raise RuntimeError(f'[launch_helpers]: {package_name!r} is no installed '
                           f'{entry_kind_text} (installed: {installed_names_text}): add its repo '
                           f'to config/nodes.list and run ./scripts/local_build.sh')
    error_start_text = (f'[launch_helpers]: the {entry_kind_text} entry of {package_name} '
                        f'(share/ament_index/resource_index/{resource_type}/{package_name})')
    # The entry comes from another repo: every key is checked by the caller, so a typo fails at
    # start instead of e.g. silently not starting a node
    try:
        entry = yaml.safe_load(entry_text)
    except yaml.YAMLError as error:
        raise RuntimeError(f'{error_start_text} is no valid YAML: {error}')
    if not isinstance(entry, dict):
        raise RuntimeError(f'{error_start_text} must be a YAML mapping, see {blueprint_path}')
    return entry


# Written by Claude Code
def get_sensor_node_package_names():
    """Return the packages that registered a sensor processing node in the ament index, sorted."""
    return sorted(get_resources(SENSOR_NODE_RESOURCE_TYPE))


# Written by Claude Code
def read_sensor_node_entry(sensor_node_package_name):
    """
    Return the checked entry of an installed sensor processing node, with every key of the format.

    required_sensor_nodes is empty when left out. Raises RuntimeError naming the fix when the node
    is not installed or its entry is malformed.
    """
    entry = _read_ament_index_entry(SENSOR_NODE_RESOURCE_TYPE, sensor_node_package_name,
                                    'sensor node', get_sensor_node_package_names(),
                                    'templates/sensor_processing_node_entry.yaml')
    error_start_text = (f'[launch_helpers]: the sensor node entry of {sensor_node_package_name} '
                        f'(share/ament_index/resource_index/{SENSOR_NODE_RESOURCE_TYPE}/'
                        f'{sensor_node_package_name})')
    known_keys = SENSOR_NODE_ENTRY_TEXT_KEYS + SENSOR_NODE_ENTRY_LIST_KEYS
    unknown_keys = sorted(set(entry) - set(known_keys))
    if unknown_keys:
        raise RuntimeError(f'{error_start_text} has unknown keys {unknown_keys}; known: '
                           f'{list(known_keys)}')
    checked_entry = {}
    for text_key in SENSOR_NODE_ENTRY_TEXT_KEYS:
        if not isinstance(entry.get(text_key), str):
            raise RuntimeError(f'{error_start_text} needs {text_key} as text')
        checked_entry[text_key] = entry[text_key]
    for list_key in SENSOR_NODE_ENTRY_LIST_KEYS:
        list_value = entry.get(list_key, [])
        is_list_of_texts = isinstance(list_value, list) and all(
            isinstance(list_item, str) for list_item in list_value)
        if not is_list_of_texts:
            raise RuntimeError(f'{error_start_text}: {list_key} must be a list of package names')
        checked_entry[list_key] = list(list_value)
    return checked_entry


# Written by Claude Code
def add_required_sensor_nodes(selected_sensor_node_names):
    """
    Return the selected sensor nodes plus every node they need (required_sensor_nodes), sorted.

    Follows the requirements of the requirements too, e.g. gesture_detector -> hand_landmarks.
    Raises RuntimeError when a node needs one that is not installed.
    """
    sensor_node_names = set()
    pending_names = list(selected_sensor_node_names)
    while pending_names:
        sensor_node_name = pending_names.pop()
        if sensor_node_name in sensor_node_names:
            continue
        sensor_node_names.add(sensor_node_name)
        pending_names += read_sensor_node_entry(sensor_node_name)['required_sensor_nodes']
    return sorted(sensor_node_names)
