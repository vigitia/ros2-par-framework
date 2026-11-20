# Co-authored by Claude Code: written by Claude Code, since edited by hand; Claude Code also added
# the setup profiles (profile launch argument, merged parameter files, per-profile extrinsics,
# per-unit camera intrinsics, per-profile intrinsics and extrinsics), the PAR app entries in the
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
# Each camera's projection calibration server publishes and serves these below the camera's
# namespace, because corners and mapping hold for one camera only (relative names, as the streams)
CAMERA_PROJECTION_CALIBRATION_NAMES = ('projection_corners', 'projection_mapping',
                                       'set_projection_corners', 'set_projection_mapping')

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
CAMERA_INTRINSICS_SOURCE_CALIBRATABLE = 'calibratable'
CAMERA_INTRINSICS_SOURCE_FACTORY = 'factory'
CAMERA_INTRINSICS_SOURCE_NONE = 'none'
CAMERA_INTRINSICS_SOURCES = (CAMERA_INTRINSICS_SOURCE_CALIBRATABLE,
                             CAMERA_INTRINSICS_SOURCE_FACTORY, CAMERA_INTRINSICS_SOURCE_NONE)
# Optional: how the units of a type are told apart. none: one unit per setup, no serial (the
# default); typed: the launch file passes a serial, which the user types; listed: as typed, and
# the setup wizard lists the connected units' serials with one of CAMERA_ENTRY_UNIT_LOOKUP_KEYS
CAMERA_ENTRY_SERIAL_KEY = 'serial'
# Optional: ROS packages the launch file starts besides its own package, e.g. a released driver an
# entry in core starts; a camera type counts as installed when all of them are (default: none)
CAMERA_ENTRY_REQUIRED_PACKAGES_KEY = 'required_packages'
# Written with the help of Claude Code: optional, the type's default parameter file, relative to
# share/<package>/ (e.g. config/realsense.yaml). Loaded before params_file and the profile, so both
# override it; for third-party drivers, whose defaults the framework cannot set in their code
CAMERA_ENTRY_PARAMETERS_FILE_KEY = 'parameters_file'
# A relative path of plain name parts below the package's share folder, never leaving it
RELATIVE_SHARE_PATH_PATTERN = re.compile(r'[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*')
CAMERA_SERIAL_SOURCES = ('none', 'typed', 'listed')
CAMERA_SERIAL_SOURCE_NONE = 'none'
CAMERA_SERIAL_SOURCE_LISTED = 'listed'
# The unit lookups of serial: listed, both plain Linux, no driver needed:
# v4l_by_id_prefix: /dev/v4l/by-id/<prefix>_<serial>-video-index0 (UVC cameras);
# usb_vendor_id: the USB devices of this vendor (4 hexadecimal digits), their serial text read in
# usb_serial_base (16 when the device reports in hexadecimal what its driver takes in decimal);
# usb_product_id (optional) narrows them to one product, for a vendor that makes other USB devices
# too or a camera that shows up as several USB devices with the same serial
CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY = 'v4l_by_id_prefix'
CAMERA_ENTRY_USB_VENDOR_ID_KEY = 'usb_vendor_id'
CAMERA_ENTRY_USB_PRODUCT_ID_KEY = 'usb_product_id'
CAMERA_ENTRY_USB_SERIAL_BASE_KEY = 'usb_serial_base'
CAMERA_ENTRY_UNIT_LOOKUP_KEYS = (CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY, CAMERA_ENTRY_USB_VENDOR_ID_KEY)
USB_SERIAL_BASES = (10, 16)
# Vendor and product ids alike, as lsusb shows them
USB_ID_PATTERN = re.compile(r'[0-9a-f]{4}')
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
PROFILE_FILE_EXTENSION = '.yaml'
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
# Co-authored by Claude Code: a camera's mount transform publisher is
# /<camera name><CAMERA_TF_PUBLISHER_NAME_SUFFIX>. A parameter file section of that name holds
# the camera's own placeholder pose; without one, the camera gets the generic placeholder below
CAMERA_TF_PUBLISHER_NAME_SUFFIX = '_tf_publisher'
# Parameter file section with the placeholder pose of every camera that has neither a measured
# pose nor its own placeholder section. No node has this name, so no node reads it
PLACEHOLDER_CAMERA_POSE_SECTION_NAME = 'placeholder_camera_pose'
# Co-authored by Claude Code: rotation of a camera's optical frame (z forward, y down) in its body
# frame (x forward, z up), REP 103, as quaternion x, y, z, w: roll -90 deg, yaw -90 deg
OPTICAL_FRAME_ROTATION_QUATERNION_XYZW = (-0.5, 0.5, -0.5, 0.5)

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
# Co-authored by Claude Code: inputs: the cameras an app reads, each with the topic names below a
# camera's namespace it reads from it, e.g. {camera: [pages, camera_info]}. The app runs in the
# root namespace and par.launch.py remaps its names onto the camera bound to the input in
# par_launch.app_inputs: an app with one input reads the plain names (pages), an app with several
# inputs prefixes each with its input (tracking/pages, capture/image_raw)
PAR_APP_ENTRY_INPUTS_KEY = 'inputs'
PAR_APP_INPUT_NAME_PATTERN = re.compile(r'[a-z][a-z0-9_]*')
# A topic name relative to the camera's namespace, e.g. pages or image_raw/compressed
PAR_APP_INPUT_TOPIC_NAME_PATTERN = re.compile(r'[a-z][a-z0-9_]*(/[a-z][a-z0-9_]*)*')
# par_launch.app_inputs: per app, the camera name bound to each of its inputs,
# e.g. {demo_app: {camera: overhead}}
PAR_LAUNCH_APP_INPUTS_KEY = 'app_inputs'
# par_launch.apps: the apps a profile offers, from which the setup wizard's Run menu chooses the
# projector app
PAR_LAUNCH_APPS_KEY = 'apps'
# par_launch.projector_app chooses the one app on the projector: none or a PAR app's package
PROJECTOR_APP_NONE = 'none'

# Sensor processing nodes (detectors, page_locator, projection_mask, ...) register in the ament
# index under this resource type, like PAR apps: share/ament_index/resource_index/
# par_framework_sensor_nodes/<package> holds the node's entry, a YAML mapping (blueprint:
# templates/sensor_processing_node_entry.yaml of ros2-par-framework). The package name is its
# par_launch switch; par.launch.py starts its executable of the same name as node <package>_node.
SENSOR_NODE_RESOURCE_TYPE = 'par_framework_sensor_nodes'
SENSOR_NODE_ENTRY_TEXT_KEYS = ('display_name', 'description')
SENSOR_NODE_ENTRY_LIST_KEYS = ('required_sensor_nodes',)


# Written by Claude Code
def get_installed_par_setup_path():
    """Return the path of the installed default par_setup.yaml, the params_file of every launch."""
    return os.path.join(get_package_share_directory('par_framework_core'), 'config',
                        'par_setup.yaml')


# Co-authored by Claude Code: names of the function, its parameter and its variables
def get_path_in_config_folder(relative_path):
    """Return the absolute path of relative_path below the folder of the real par_setup.yaml."""
    # The default par_setup.yaml, not params_file: the calibrations are shared by every parameter
    # file. realpath follows the --symlink-install links back to the source folder, so files
    # written there survive rebuilds
    config_folder_path = os.path.dirname(os.path.realpath(get_installed_par_setup_path()))
    return os.path.join(config_folder_path, relative_path)


# Written by Claude Code
def create_folder_of_file(file_path):
    """Create the folder file_path lies in, for a file that is written there."""
    # Only for writers: the nodes that write calibrations (camera_info_manager,
    # camera_pose_calibrator, ...) open the file without creating its folder. Code that only
    # checks or reads a file must not call this, or it leaves empty folders behind, e.g. for a
    # profile that was deleted meanwhile
    os.makedirs(os.path.dirname(file_path), exist_ok=True)


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


# Written by Claude Code
def get_profile_file_path(profile_name):
    """Return the path of a profile's file: config/profiles/<profile_name>.yaml."""
    return get_path_in_config_folder(
        f'{FOLDER_PATH_PROFILES}/{profile_name}{PROFILE_FILE_EXTENSION}')


# Co-authored by Claude Code
def get_params_file_paths(context):
    """Return the parameter files in the order ROS applies them: params_file, then the profile."""
    params_file_paths = [LaunchConfiguration('params_file').perform(context)]
    profile_name = get_profile_name(context)
    if profile_name:
        profile_path = get_profile_file_path(profile_name)
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
def get_unit_intrinsics_file_path(context, camera_type, serial):
    """Return the absolute path of a camera unit's intrinsics file in the intrinsics folder."""
    intrinsics_folder_path = get_intrinsics_folder_path(context)
    camera_info_file_name = get_camera_info_file_name_of_unit(camera_type, serial)
    return get_path_in_config_folder(f'{intrinsics_folder_path}/{camera_info_file_name}')


# Written by Claude Code
def get_camera_info_url(context, camera_type, serial):
    """Return the file:// URL of a camera unit's intrinsics file, the drivers' camera_info_url."""
    intrinsics_file_path = get_unit_intrinsics_file_path(context, camera_type, serial)
    # The driver writes the file there when a calibration is committed through set_camera_info
    create_folder_of_file(intrinsics_file_path)
    return f'file://{intrinsics_file_path}'


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
        # Written with the help of Claude Code: par_setup.yaml names no camera, so this is
        # where a launch without profile:= ends up
        raise RuntimeError(f'[launch_helpers]: no cameras: pass profile:=<name> (the setup '
                           f'wizard, ./scripts/start_setup_wizard.sh, creates one), map each '
                           f'camera name to its unit in par_launch.{PAR_LAUNCH_CAMERAS_KEY} of '
                           f'the profile, e.g. {PAR_LAUNCH_CAMERAS_KEY}: {{overhead: '
                           f'"blackfly:22260470"}}, or pass camera:=<type>[:<serial>]')

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
    # The launch file would ignore it, while the intrinsics file is named after it
    is_serial_unsupported = (
        read_camera_entry(camera_type)[CAMERA_ENTRY_SERIAL_KEY] == CAMERA_SERIAL_SOURCE_NONE)
    if serial and is_serial_unsupported:
        raise RuntimeError(f'[launch_helpers]: {source_text}: camera type {camera_type} has no '
                           f'serial numbers ({CAMERA_ENTRY_SERIAL_KEY}: none in its entry); '
                           f'write {camera_type!r} alone')
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
    return check_camera_entry(entry, error_start_text)


# Co-authored by Claude Code: split from read_camera_entry, so the setup wizard checks entries of
# repositories that are not installed yet the same way
def check_camera_entry(entry, error_start_text):
    """
    Return a camera type's entry (a mapping) checked, a dict with every key of the format.

    Raises RuntimeError starting with error_start_text when a key is unknown, missing or of the
    wrong type.
    """
    other_keys = (CAMERA_ENTRY_BODY_FRAME_KEY, CAMERA_ENTRY_STREAMS_KEY,
                  CAMERA_ENTRY_INTRINSICS_KEY)
    required_keys = CAMERA_ENTRY_TEXT_KEYS + CAMERA_ENTRY_NAME_KEYS + other_keys
    optional_keys = (CAMERA_ENTRY_REQUIRED_PACKAGES_KEY, CAMERA_ENTRY_SERIAL_KEY,
                     CAMERA_ENTRY_USB_SERIAL_BASE_KEY, CAMERA_ENTRY_USB_PRODUCT_ID_KEY,
                     CAMERA_ENTRY_PARAMETERS_FILE_KEY, *CAMERA_ENTRY_UNIT_LOOKUP_KEYS)
    known_keys = required_keys + optional_keys
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
    for required_key in required_keys:
        checked_entry[required_key] = entry[required_key]
    checked_entry[CAMERA_ENTRY_STREAMS_KEY] = list(streams)
    required_package_names = entry.get(CAMERA_ENTRY_REQUIRED_PACKAGES_KEY, [])
    is_list_of_package_names = isinstance(required_package_names, list) and all(
        isinstance(package_name, str) and PAR_APP_START_NAME_PATTERN.fullmatch(package_name)
        for package_name in required_package_names)
    if not is_list_of_package_names:
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_REQUIRED_PACKAGES_KEY} must be a '
                           f'list of ROS package names, e.g. [v4l2_camera]')
    checked_entry[CAMERA_ENTRY_REQUIRED_PACKAGES_KEY] = list(required_package_names)
    parameters_file_relative_path = entry.get(CAMERA_ENTRY_PARAMETERS_FILE_KEY)
    if parameters_file_relative_path is not None:
        is_relative_share_path = (
            isinstance(parameters_file_relative_path, str)
            and RELATIVE_SHARE_PATH_PATTERN.fullmatch(parameters_file_relative_path)
            and '..' not in parameters_file_relative_path.split('/'))
        if not is_relative_share_path:
            raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_PARAMETERS_FILE_KEY} must be '
                               f'a path below the package\'s share folder, e.g. '
                               f'config/realsense.yaml')
    checked_entry[CAMERA_ENTRY_PARAMETERS_FILE_KEY] = parameters_file_relative_path
    checked_entry.update(_check_camera_entry_serial_keys(entry, error_start_text))
    return checked_entry


# Written by Claude Code
def get_camera_type_params_file_paths(camera_entry):
    """
    Return the camera type's default parameter file as a list: one path, or none without one.

    Raises RuntimeError naming the fix when the entry names a file that is not installed.
    """
    parameters_file_relative_path = camera_entry[CAMERA_ENTRY_PARAMETERS_FILE_KEY]
    if parameters_file_relative_path is None:
        return []
    package_share_path = get_package_share_directory(camera_entry['package'])
    parameters_file_path = os.path.join(package_share_path, parameters_file_relative_path)
    if not os.path.isfile(parameters_file_path):
        raise RuntimeError(f'[launch_helpers]: the camera entry names {parameters_file_path} as '
                           f'{CAMERA_ENTRY_PARAMETERS_FILE_KEY}, which is not installed: install '
                           f'it in the setup.py data_files of {camera_entry["package"]} and run '
                           f'./scripts/local_build.sh')
    return [parameters_file_path]


# Written by Claude Code
def _check_camera_entry_serial_keys(entry, error_start_text):
    """
    Return the entry's serial keys checked, every one set (None for an unused lookup).

    Raises RuntimeError naming the fix for a value or combination the format does not allow.
    """
    serial_source = entry.get(CAMERA_ENTRY_SERIAL_KEY, CAMERA_SERIAL_SOURCE_NONE)
    if serial_source not in CAMERA_SERIAL_SOURCES:
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_SERIAL_KEY} must be one of '
                           f'{list(CAMERA_SERIAL_SOURCES)}')
    v4l_by_id_prefix = entry.get(CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY)
    usb_vendor_id = entry.get(CAMERA_ENTRY_USB_VENDOR_ID_KEY)
    usb_product_id = entry.get(CAMERA_ENTRY_USB_PRODUCT_ID_KEY)
    usb_serial_base = entry.get(CAMERA_ENTRY_USB_SERIAL_BASE_KEY, 10)
    unit_lookup_count = 0
    if v4l_by_id_prefix is not None:
        unit_lookup_count += 1
    if usb_vendor_id is not None:
        unit_lookup_count += 1
    is_listed = serial_source == CAMERA_SERIAL_SOURCE_LISTED
    if is_listed and unit_lookup_count != 1:
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_SERIAL_KEY}: listed needs exactly '
                           f'one of {list(CAMERA_ENTRY_UNIT_LOOKUP_KEYS)}')
    if not is_listed and unit_lookup_count > 0:
        raise RuntimeError(f'{error_start_text}: {list(CAMERA_ENTRY_UNIT_LOOKUP_KEYS)} only go '
                           f'with {CAMERA_ENTRY_SERIAL_KEY}: listed')
    # Part of a glob pattern over /dev/v4l/by-id: a plain name, no wildcards or path
    if v4l_by_id_prefix is not None:
        is_plain_name = isinstance(v4l_by_id_prefix, str) and FILE_NAME_PART_PATTERN.fullmatch(
            v4l_by_id_prefix)
        if not is_plain_name:
            raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY} must be '
                               f'the start of the camera\'s /dev/v4l/by-id names before the '
                               f'serial, e.g. usb-046d_Logitech_BRIO')
    if usb_vendor_id is not None:
        _check_usb_id(usb_vendor_id, CAMERA_ENTRY_USB_VENDOR_ID_KEY, "'1e10'", error_start_text)
        if usb_product_id is not None:
            _check_usb_id(usb_product_id, CAMERA_ENTRY_USB_PRODUCT_ID_KEY, "'097c'",
                          error_start_text)
    else:
        for usb_only_key in (CAMERA_ENTRY_USB_SERIAL_BASE_KEY, CAMERA_ENTRY_USB_PRODUCT_ID_KEY):
            if usb_only_key in entry:
                raise RuntimeError(f'{error_start_text}: {usb_only_key} only goes with '
                                   f'{CAMERA_ENTRY_USB_VENDOR_ID_KEY}')
    if usb_serial_base not in USB_SERIAL_BASES:
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_USB_SERIAL_BASE_KEY} must be one '
                           f'of {list(USB_SERIAL_BASES)}')
    return {CAMERA_ENTRY_SERIAL_KEY: serial_source,
            CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY: v4l_by_id_prefix,
            CAMERA_ENTRY_USB_VENDOR_ID_KEY: usb_vendor_id,
            CAMERA_ENTRY_USB_PRODUCT_ID_KEY: usb_product_id,
            CAMERA_ENTRY_USB_SERIAL_BASE_KEY: usb_serial_base}


# Written by Claude Code
def _check_usb_id(usb_id, entry_key, example_text, error_start_text):
    """Raise RuntimeError naming the fix unless usb_id is 4 lower case hexadecimal digits."""
    is_usb_id = isinstance(usb_id, str) and USB_ID_PATTERN.fullmatch(usb_id)
    if not is_usb_id:
        raise RuntimeError(f'{error_start_text}: {entry_key} must be 4 lower case hexadecimal '
                           f'digits as text, as lsusb shows it, e.g. {example_text}')


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
    if camera_entry[CAMERA_ENTRY_INTRINSICS_KEY] == CAMERA_INTRINSICS_SOURCE_CALIBRATABLE:
        camera_info_url = get_camera_info_url(context, camera_type, serial)
    camera_launch_arguments = {
        'namespace': get_camera_namespace(camera_name),
        'camera_name': camera_name,
        'serial': serial,
        'camera_info_url': camera_info_url,
        # Written with the help of Claude Code: the type's defaults first, so the parameter files
        # override them
        'params_files': os.pathsep.join(get_camera_type_params_file_paths(camera_entry)
                                        + get_params_file_paths(context)),
    }
    return [IncludeLaunchDescription(PythonLaunchDescriptionSource(launch_file_path),
                                     launch_arguments=camera_launch_arguments.items()),
            *create_mount_tf_publisher(context,
                                       f'{camera_name}{CAMERA_TF_PUBLISHER_NAME_SUFFIX}',
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


# Written by Claude Code
def read_published_camera_pose(context, camera_name):
    """
    Return the pose a launch publishes for the camera, as (pose, source text, is measured).

    The measurement while it exists: camera_pose_<camera name>.yaml in the profile's extrinsics
    folder, written by camera_pose_calibrator. Else the placeholder (read_placeholder_camera_pose).
    pose is the file's or section's content unchecked; get_invalid_pose_keys checks it. Raises
    OSError or yaml.YAMLError when the measured file cannot be read.
    """
    measured_pose_relative_path = get_extrinsics_relative_path(context, 'camera_pose',
                                                               camera_name)
    measured_pose_path = get_path_in_config_folder(measured_pose_relative_path)
    if os.path.exists(measured_pose_path):
        with open(measured_pose_path) as measured_pose_file:
            camera_pose = yaml.safe_load(measured_pose_file)
        return camera_pose, measured_pose_path, True
    placeholder_pose, pose_source_text = read_placeholder_camera_pose(context, camera_name)
    return placeholder_pose, pose_source_text, False


# Written by Claude Code
def read_placeholder_camera_pose(context, camera_name):
    """
    Return the camera's placeholder pose from the parameter files, as (pose, source text).

    The camera's own section /<camera name>_tf_publisher when a parameter file has one (e.g. a
    profile placing one camera of several elsewhere), else the generic
    PLACEHOLDER_CAMERA_POSE_SECTION_NAME section. pose is the section's content unchecked (None
    when neither section exists); get_invalid_pose_keys checks it.
    """
    merged_parameters = read_merged_parameters(context)
    camera_section_name = f'/{camera_name}{CAMERA_TF_PUBLISHER_NAME_SUFFIX}'
    placeholder_section_name = PLACEHOLDER_CAMERA_POSE_SECTION_NAME
    if camera_section_name in merged_parameters:
        placeholder_section_name = camera_section_name
    placeholder_section = merged_parameters.get(placeholder_section_name) or {}
    placeholder_pose = placeholder_section.get('ros__parameters')
    params_file_paths_text = ' + '.join(get_params_file_paths(context))
    pose_source_text = f'the placeholder {placeholder_section_name} in {params_file_paths_text}'
    return placeholder_pose, pose_source_text


# Co-authored by Claude Code: checks the pose before it is used, reads the profile's files,
# variable names, the pose source shared with the setup wizard
def create_mount_tf_publisher(context, publisher_name, child_frame_id):
    """
    Create the publisher of world -> child_frame_id: the measured camera pose, or the placeholder.

    The pose is the one read_published_camera_pose returns for <camera>, which is
    <publisher_name> without _tf_publisher.
    """
    # static_transform_publisher takes its transform only as command-line flags: parameters from
    # a file are overridden by the flags' defaults, and without --frame-id it does not start. So
    # the pose is read from the file here, which is only possible once params_file is known.
    camera = publisher_name.removesuffix(CAMERA_TF_PUBLISHER_NAME_SUFFIX)
    camera_pose, pose_source_text, is_pose_measured = read_published_camera_pose(context, camera)
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


# Co-authored by Claude Code: name, the paths in named steps, the profile's extrinsics folder,
# the camera's namespace
def create_projection_calibration_server_node(context, camera):
    """Create the owner of the projection corners and mapping, with the camera's files."""
    # One file per camera each: the corners are pixels of one camera's image, so another camera's
    # would point elsewhere. And while the camera poses in par_setup.yaml are placeholders, each
    # camera's table plane is its own, so a mapping only fits the camera it was calibrated with.
    # Per profile as well: another setup has another table and projector
    corners_file_path = get_path_in_config_folder(
        get_extrinsics_relative_path(context, 'projection_corners', camera))
    mapping_file_path = get_path_in_config_folder(
        get_extrinsics_relative_path(context, 'projection_mapping', camera))
    # The server writes both files when a calibration sets them; they share one folder
    create_folder_of_file(mapping_file_path)
    # In the camera's namespace, so each camera has its own server, topics and services, e.g.
    # /cameras/overhead/projection_mapping
    return [Node(
        package='projection_calibration_server',
        executable='projection_calibration_server',
        name='projection_calibration_server_node',
        namespace=get_camera_namespace(camera),
        output='screen',
        emulate_tty=True,
        parameters=[{
            'projection_corners_file': corners_file_path,
            'projection_mapping_file': mapping_file_path,
        }],
    )]


# Written by Claude Code
def get_par_app_package_names():
    """Return the packages that registered a PAR app in the ament index, sorted."""
    return sorted(get_resources(PAR_APP_RESOURCE_TYPE))


# Written by Claude Code
def read_offered_par_app_names(launch_section):
    """
    Return the installed PAR apps par_launch.apps offers, in its order.

    Other names (rviz, an app not installed) are left out. Raises
    RuntimeError naming the fix when par_launch.apps is no list.
    """
    listed_app_names = launch_section.get(PAR_LAUNCH_APPS_KEY) or []
    if not isinstance(listed_app_names, list):
        raise RuntimeError(f'[launch_helpers]: par_launch.{PAR_LAUNCH_APPS_KEY} must be a list of '
                           f'app names, e.g. {PAR_LAUNCH_APPS_KEY}: [demo_app], not '
                           f'{listed_app_names!r}')
    installed_app_names = get_par_app_package_names()
    offered_app_names = []
    for app_name in listed_app_names:
        if str(app_name) in installed_app_names:
            offered_app_names.append(str(app_name))
    return offered_app_names


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
    return check_par_app_entry(entry, error_start_text)


# Co-authored by Claude Code: split from read_par_app_entry, so the setup wizard checks entries of
# repositories that are not installed yet the same way
def check_par_app_entry(entry, error_start_text):
    """
    Return a PAR app's entry (a mapping) checked, a dict with every key of the format.

    executable or launch_file is set, the other one is None; the lists are empty when left out.
    Raises RuntimeError starting with error_start_text when a key is unknown, missing or of the
    wrong type.
    """
    known_keys = (PAR_APP_ENTRY_TEXT_KEYS + PAR_APP_ENTRY_START_KEYS + PAR_APP_ENTRY_LIST_KEYS
                  + (PAR_APP_ENTRY_INPUTS_KEY,))
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
    checked_entry[PAR_APP_ENTRY_INPUTS_KEY] = _check_par_app_inputs(
        entry.get(PAR_APP_ENTRY_INPUTS_KEY, {}), error_start_text)
    return checked_entry


# Written by Claude Code
def _check_par_app_inputs(inputs, error_start_text):
    """Return an app entry's inputs as {input name: [topic name, ...]}, checked."""
    example_text = 'e.g. inputs: {camera: [pages, camera_info]}'
    if not isinstance(inputs, dict):
        raise RuntimeError(f'{error_start_text}: {PAR_APP_ENTRY_INPUTS_KEY} must map each input '
                           f'to the topic names it reads, {example_text}')
    checked_inputs = {}
    for input_name, topic_names in inputs.items():
        if not isinstance(input_name, str) or not PAR_APP_INPUT_NAME_PATTERN.fullmatch(input_name):
            raise RuntimeError(f'{error_start_text}: input {input_name!r}: an input name may only '
                               f'hold lower case letters, digits and _, starting with a letter')
        is_list_of_topic_names = isinstance(topic_names, list) and bool(topic_names) and all(
            isinstance(topic_name, str)
            and PAR_APP_INPUT_TOPIC_NAME_PATTERN.fullmatch(topic_name)
            for topic_name in topic_names)
        if not is_list_of_topic_names:
            raise RuntimeError(f'{error_start_text}: input {input_name} must list the topic names '
                               f'it reads below the namespace of the camera, without a leading /, '
                               f'{example_text}')
        checked_inputs[input_name] = list(topic_names)
    return checked_inputs


# Written by Claude Code
def get_app_input_camera_names(launch_section, app_name, app_inputs, profile_camera_names,
                               started_camera_names):
    """
    Return {input name: camera name} for every input of the app's entry.

    par_launch.app_inputs.<app>.<input> binds an input to a camera of par_launch.cameras; an
    input left unbound reads the only camera of the run. Raises RuntimeError naming the fix when
    a binding is malformed, names an unknown input or camera, or a camera this run does not
    start, and when an unbound input has several cameras to choose from.
    """
    example_text = f'e.g. {PAR_LAUNCH_APP_INPUTS_KEY}: {{{app_name}: {{<input>: <camera>}}}}'
    input_camera_name_by_app = launch_section.get(PAR_LAUNCH_APP_INPUTS_KEY, {})
    if not isinstance(input_camera_name_by_app, dict):
        raise RuntimeError(f'[par.launch]: par_launch.{PAR_LAUNCH_APP_INPUTS_KEY} must map each '
                           f'app to the cameras of its inputs, {example_text}')
    bound_camera_name_by_input = input_camera_name_by_app.get(app_name, {})
    error_start_text = f'[par.launch]: par_launch.{PAR_LAUNCH_APP_INPUTS_KEY}.{app_name}'
    if not isinstance(bound_camera_name_by_input, dict):
        raise RuntimeError(f'{error_start_text} must map each input to a camera, {example_text}')
    unknown_input_names = sorted(set(bound_camera_name_by_input) - set(app_inputs))
    if unknown_input_names:
        raise RuntimeError(f'{error_start_text} names the inputs {unknown_input_names}, which '
                           f'{app_name} does not have; its inputs: {list(app_inputs)}')

    camera_name_by_input = {}
    for input_name in app_inputs:
        bound_camera_name = bound_camera_name_by_input.get(input_name)
        if bound_camera_name is None:
            if len(started_camera_names) != 1:
                raise RuntimeError(f'{error_start_text}.{input_name} is not set, and this run '
                                   f'starts the cameras {started_camera_names}: bind the input '
                                   f'to one of them, {example_text}')
            camera_name_by_input[input_name] = started_camera_names[0]
            continue
        if bound_camera_name not in profile_camera_names:
            raise RuntimeError(f'{error_start_text}.{input_name}: {bound_camera_name!r} is no '
                               f'camera of par_launch.cameras; known: {profile_camera_names}')
        if bound_camera_name not in started_camera_names:
            raise RuntimeError(f'{error_start_text}.{input_name} reads {bound_camera_name}, '
                               f'which this run does not start (camera:='
                               f'{started_camera_names[0]}): start it too, or pass '
                               f'projector_app:={PROJECTOR_APP_NONE}')
        camera_name_by_input[input_name] = bound_camera_name
    return camera_name_by_input


# Written by Claude Code
def get_par_app_sensor_node_camera_names(par_app_entry, camera_name_by_input, main_camera_name,
                                         sensor_node_names):
    """
    Return {sensor node: [camera name]}: where the app's required sensor nodes run for it.

    They run on every camera the app reads (camera_name_by_input, from
    get_app_input_camera_names); an app without inputs reads no camera of its own, so they run on
    the main camera. Required launch switches that are no sensor node (rviz) are left out.
    par.launch.py starts them this way and the setup wizard shows them, so both follow this one
    rule.
    """
    # Simplification: the required sensor nodes run on every camera the app reads, also on a
    # camera whose input does not use them (e.g. markers on a capture camera). Upgrade: the entry
    # names the required sensor nodes per input
    app_camera_names = []
    for camera_name in camera_name_by_input.values():
        if camera_name not in app_camera_names:
            app_camera_names.append(camera_name)
    if not app_camera_names:
        app_camera_names = [main_camera_name]
    camera_names_by_sensor_node = {}
    for switch_name in par_app_entry['required_launch_switches']:
        if switch_name in sensor_node_names:
            camera_names_by_sensor_node[switch_name] = list(app_camera_names)
    return camera_names_by_sensor_node


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
                           f'from config/catalog_repos.list to config/installed_repos.list and '
                           f'run ./scripts/local_build.sh')
    error_start_text = (f'[launch_helpers]: the {entry_kind_text} entry of {package_name} '
                        f'(share/ament_index/resource_index/{resource_type}/{package_name})')
    return parse_ament_index_entry_text(entry_text, error_start_text, blueprint_path)


# Co-authored by Claude Code: split from _read_ament_index_entry, so the setup wizard checks
# entries read from a repository that is not installed yet the same way
def parse_ament_index_entry_text(entry_text, error_start_text, blueprint_path):
    """
    Return an ament index entry's text loaded as a YAML mapping.

    error_start_text names the entry in the error, e.g. "the camera entry of brio (...)". Raises
    RuntimeError naming the fix when the text is no YAML mapping; the caller checks the keys.
    """
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
def get_sensor_node_name(sensor_node_package_name):
    """Return the node name par.launch.py gives a sensor node in its camera's namespace."""
    return f'{sensor_node_package_name}_node'


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
    return check_sensor_node_entry(entry, error_start_text)


# Co-authored by Claude Code: split from read_sensor_node_entry, so the setup wizard checks
# entries of repositories that are not installed yet the same way
def check_sensor_node_entry(entry, error_start_text):
    """
    Return a sensor processing node's entry (a mapping) checked, with every key of the format.

    required_sensor_nodes is empty when left out. Raises RuntimeError starting with
    error_start_text when a key is unknown, missing or of the wrong type.
    """
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


# Written by Claude Code
def get_sensor_node_names_by_camera(camera_names_by_sensor_node, camera_names):
    """
    Return, per camera of camera_names, the sensor nodes that run on it, sorted.

    camera_names_by_sensor_node is par_launch's lists, {sensor node: [camera name]}. A camera
    runs the nodes listed for it plus every node they need (add_required_sensor_nodes): a node
    reads the outputs of its required ones in its own camera's namespace. Raises RuntimeError
    when a node needs one that is not installed.
    """
    sensor_node_names_by_camera = {}
    for camera_name in camera_names:
        listed_sensor_node_names = []
        for sensor_node_name, listed_camera_names in camera_names_by_sensor_node.items():
            if camera_name in listed_camera_names:
                listed_sensor_node_names.append(sensor_node_name)
        sensor_node_names_by_camera[camera_name] = add_required_sensor_nodes(
            listed_sensor_node_names)
    return sensor_node_names_by_camera
