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

import collections
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
# Co-authored by Claude Code: par_launch.cameras maps each camera's name to its unit,
# '<camera type>' or '<camera type>:<serial>', e.g. {overhead: 'blackfly:22260470'}. The name
# makes the camera's namespace (/cameras/<name>), its frames (<name>_link, ...) and its extrinsics
# files; the unit makes its intrinsics file (camera_info_<type>_<serial>.yaml), since they belong
# to the lens. A replaced unit keeps its name, topics, pose and projection mapping
PAR_LAUNCH_CAMERAS_KEY = 'cameras'
# A camera name is part of ROS names and file names: lower case, digits and _, starting with a
# letter (ROS names may not contain - or start with a digit)
CAMERA_NAME_PATTERN = re.compile(r'[a-z][a-z0-9_]*')
# The par_launch keys of the one-camera format, refused with a message naming the fix
OLD_PAR_LAUNCH_CAMERA_KEYS = ('camera', 'additional_cameras', 'capture_camera')
# A camera to start: its name, its type (an entry in CAMERA_RESOURCE_TYPE) and its unit's serial
# ('' opens the first unit found)
ProfileCamera = collections.namedtuple('ProfileCamera', ['camera_name', 'camera_type', 'serial'])
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


# Written by Claude Code
def read_profile_cameras(context):
    """
    Return the cameras par_launch.cameras names, in its order, as ProfileCamera tuples.

    Raises RuntimeError naming the fix when the list is missing or malformed, or when the
    parameter files still use the one-camera keys.
    """
    launch_section = read_launch_section(context)
    old_keys = [key for key in OLD_PAR_LAUNCH_CAMERA_KEYS if key in launch_section]
    if old_keys:
        raise RuntimeError(f'[launch_helpers]: par_launch.{", par_launch.".join(old_keys)}: no '
                           f'longer read; name every camera in par_launch.{PAR_LAUNCH_CAMERAS_KEY} '
                           f'instead, e.g. {PAR_LAUNCH_CAMERAS_KEY}: {{overhead: '
                           f"'blackfly:22260470'}}, and remove {', '.join(old_keys)}")
    # The last parameter file that names cameras sets all of them: a profile's cameras replace
    # par_setup.yaml's default instead of being merged with it key by key
    camera_unit_text_by_name = None
    cameras_source_path = None
    for params_file_path in get_params_file_paths(context):
        with open(params_file_path) as params_file:
            file_parameters = yaml.safe_load(params_file) or {}
        launch_parameters = (file_parameters.get('par_launch') or {}).get('ros__parameters') or {}
        if PAR_LAUNCH_CAMERAS_KEY in launch_parameters:
            camera_unit_text_by_name = launch_parameters[PAR_LAUNCH_CAMERAS_KEY]
            cameras_source_path = params_file_path
    if not isinstance(camera_unit_text_by_name, dict) or not camera_unit_text_by_name:
        raise RuntimeError(f'[launch_helpers]: no cameras: map each camera\'s name to its unit in '
                           f'par_launch.{PAR_LAUNCH_CAMERAS_KEY} of the profile, e.g. '
                           f"{PAR_LAUNCH_CAMERAS_KEY}: {{overhead: 'blackfly:22260470'}}, or pass "
                           f'camera:=<type>[:<serial>]')

    profile_cameras = []
    for camera_name, camera_unit_text in camera_unit_text_by_name.items():
        source_text = f'par_launch.{PAR_LAUNCH_CAMERAS_KEY}.{camera_name} in {cameras_source_path}'
        if not isinstance(camera_name, str) or not CAMERA_NAME_PATTERN.fullmatch(camera_name):
            raise RuntimeError(f'[launch_helpers]: {source_text}: a camera name may only hold '
                               f'lower case letters, digits and _, starting with a letter')
        camera_type, serial = parse_camera_unit_text(camera_unit_text, source_text)
        profile_cameras.append(ProfileCamera(camera_name, camera_type, serial))
    return profile_cameras


# Written by Claude Code
def parse_camera_unit_text(camera_unit_text, source_text):
    """Return (camera type, serial) of '<type>' or '<type>:<serial>'; the serial may be ''."""
    # str(): YAML reads a unit written as a bare number, e.g. a serial alone, as an int
    camera_type, _, serial = str(camera_unit_text).partition(':')
    camera_type_names = get_camera_type_names()
    if camera_type not in camera_type_names:
        camera_type_names_text = ', '.join(camera_type_names) or 'none'
        raise RuntimeError(f'[launch_helpers]: {source_text}: unknown camera type '
                           f'{camera_type!r} in {camera_unit_text!r}; write <type> or '
                           f'<type>:<serial> with one of the installed camera types '
                           f'({camera_type_names_text}). A camera type is installed with the '
                           f'package that registers it ({CAMERA_RESOURCE_TYPE})')
    if serial and not FILE_NAME_PART_PATTERN.fullmatch(serial):
        raise RuntimeError(f'[launch_helpers]: {source_text}: {serial!r} is no serial number: '
                           f'use only letters, digits, _ and -')
    return camera_type, serial


# Written by Claude Code
def get_cameras_to_start(context):
    """
    Return the cameras a launch starts, as ProfileCamera tuples; the first one is the main camera.

    Without camera:=, every camera of par_launch.cameras. camera:=<name> starts that camera of
    the profile; camera:=<type>[:<serial>] starts a unit the profile does not name, named after
    its type, e.g. to preview or calibrate it.
    """
    camera_argument = context.launch_configurations.get('camera', '')
    if not camera_argument:
        return read_profile_cameras(context)
    # A camera:= without a profile list must not fail on the missing list
    launch_section = read_launch_section(context)
    if PAR_LAUNCH_CAMERAS_KEY in launch_section:
        for profile_camera in read_profile_cameras(context):
            if profile_camera.camera_name == camera_argument:
                return [profile_camera]
    camera_type, serial = parse_camera_unit_text(camera_argument, f'camera:={camera_argument}')
    return [ProfileCamera(camera_type, camera_type, serial)]


# Written by Claude Code
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


# Written by Claude Code
def get_camera_to_calibrate(context):
    """Return the one camera a calibration launch measures; camera:= chooses it among several."""
    cameras_to_start = get_cameras_to_start(context)
    if len(cameras_to_start) > 1:
        camera_names_text = ', '.join(camera.camera_name for camera in cameras_to_start)
        raise RuntimeError(f'[launch_helpers]: the profile has several cameras '
                           f'({camera_names_text}): choose the one to calibrate with '
                           f'camera:=<name>')
    return cameras_to_start[0]


# Co-authored by Claude Code: the one identifier of a camera unit
def get_camera_id(camera, serial):
    """
    Return the identifier of a camera unit: '<camera>_<serial>', or '<camera>' without a serial.

    It ends the name of the unit's intrinsics file, so two units of one type never share or
    overwrite one.
    """
    if not serial:
        return camera
    return f'{camera}_{serial}'


# Co-authored by Claude Code: calibration files per camera name
def get_extrinsics_relative_path(context, file_prefix, camera_name):
    """
    Return the extrinsics file <file_prefix>_<camera name>.yaml of a camera.

    file_prefix is camera_pose, projection_mapping or projection_corners. Named after the camera,
    not its unit: the pose belongs to the mount, so a replaced unit keeps it.
    """
    return f'{get_extrinsics_folder_path(context)}/{file_prefix}_{camera_name}.yaml'


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
def create_camera_actions(context, profile_camera):
    """
    Create a camera (a ProfileCamera) from its type's entry: its launch file and mount transform.

    The camera runs in /cameras/<camera name>, its frames are named after it, and its unit opens
    with the unit's intrinsics.
    """
    camera_name, camera_type, serial = profile_camera
    camera_entry = read_camera_entry(camera_type)
    launch_file_path = os.path.join(get_package_share_directory(camera_entry['package']),
                                    'launch', camera_entry['launch_file'])
    if not os.path.isfile(launch_file_path):
        raise RuntimeError(f'[launch_helpers]: the camera type {camera_type} names the launch file '
                           f'{launch_file_path}, which is not installed: install launch/ in the '
                           f'setup.py data_files of {camera_entry["package"]} '
                           f'(templates/par_camera/) and run ./scripts/local_build.sh')
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


# Co-authored by Claude Code
def get_camera_info_file_name_of_unit(camera, serial):
    """Return the intrinsics file name of one unit: camera_info_<camera id>.yaml."""
    return f'camera_info_{get_camera_id(camera, serial)}.yaml'


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
