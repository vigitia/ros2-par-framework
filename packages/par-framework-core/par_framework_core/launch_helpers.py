# Co-authored by Claude Code: written by Claude Code, since edited by hand; Claude Code also added
# the setup profiles (profile launch argument, merged parameter files, per-profile extrinsics,
# per-unit Brio intrinsics, per-profile intrinsics and extrinsics) and the PAR app entries in the
# ament index
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
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from par_framework_core.connected_displays import (find_projector_display_ids,
                                                   get_projector_identity_title_text,
                                                   PROJECTOR_IDENTITY_PARAMETER_NAMES,
                                                   read_connected_displays)
import yaml


# The framework's default camera interface, whichever camera runs.
# The framework nodes subscribe to these names; each camera driver is remapped onto them
DEFAULT_TOPIC_NAME_CAMERA_IMAGE = '/camera/image_raw'
DEFAULT_TOPIC_NAME_CAMERA_IMAGE_COMPRESSED = DEFAULT_TOPIC_NAME_CAMERA_IMAGE + '/compressed'
DEFAULT_TOPIC_NAME_CAMERA_INFO = '/camera/camera_info'
# Depth registered to the colour image (same pixel grid), only from a depth camera
DEFAULT_TOPIC_NAME_CAMERA_DEPTH = '/camera/depth_registered/image_raw'
# Infrared on the colour image's pixel grid, only from a camera that has one. Unlike depth, the
# name does not say "registered"; /camera/ir_registered/image_raw would be the consistent
# alternative. Infrared on another grid (e.g. a depth camera's) is not mapped onto this name.
DEFAULT_TOPIC_NAME_CAMERA_IR = '/camera/ir/image_raw'
# A depth camera's infrared and depth on its own pixel grid, unregistered, with its intrinsics.
# The depth sensor measures depth with this infrared, so both are aligned pixel by pixel; its pose
# relative to the colour camera comes from TF. Co-authored by Claude Code
DEFAULT_TOPIC_NAME_DEPTH_SENSOR_IR = '/camera/depth_sensor/ir/image_raw'
DEFAULT_TOPIC_NAME_DEPTH_SENSOR_DEPTH = '/camera/depth_sensor/depth/image_raw'
DEFAULT_TOPIC_NAME_DEPTH_SENSOR_CAMERA_INFO = '/camera/depth_sensor/camera_info'
# Raw events (event_camera_msgs/EventPacket), only from an event camera
DEFAULT_TOPIC_NAME_CAMERA_EVENTS = '/camera/events'

# cameracalibrator's COMMIT stores the calibration through this service
DEFAULT_SERVICE_NAME_CAMERA_SET_INFO = '/camera/set_camera_info'


# Per camera: (the driver's own name, the framework's name) pairs
CAMERA_DRIVER_REMAPPINGS = {
    # The Brio node from this framework. It can send the raw camera images or compressed ones, depending on the use case
    'brio': [
        ('/camera/brio/image_raw', DEFAULT_TOPIC_NAME_CAMERA_IMAGE),
        ('/camera/brio/image_raw/compressed', DEFAULT_TOPIC_NAME_CAMERA_IMAGE_COMPRESSED),
        ('/camera/brio/image_rect_color', '/camera/image_rect_color'),   # TODO: ADD Constant
        ('/camera/brio/camera_info', DEFAULT_TOPIC_NAME_CAMERA_INFO),
        ('/camera/brio/set_camera_info', DEFAULT_SERVICE_NAME_CAMERA_SET_INFO),
    ],
    # The Kinect driver we use from GitHub unfortunately publishes without a namespace
    'kinect': [
        ('/rgb/image_raw', DEFAULT_TOPIC_NAME_CAMERA_IMAGE),
        ('/rgb/camera_info', DEFAULT_TOPIC_NAME_CAMERA_INFO),
        ('/depth_to_rgb/image_raw', DEFAULT_TOPIC_NAME_CAMERA_DEPTH),
        # Infrared transformed onto the colour image's grid by the driver (its ir/image_raw is on
        # the depth grid)
        ('/ir_to_rgb/image_raw', DEFAULT_TOPIC_NAME_CAMERA_IR),
        # The depth sensor's own infrared and depth, e.g. for hand_landmarks with use_ir
        ('/ir/image_raw', DEFAULT_TOPIC_NAME_DEPTH_SENSOR_IR),
        ('/depth/image_raw', DEFAULT_TOPIC_NAME_DEPTH_SENSOR_DEPTH),
        ('/depth/camera_info', DEFAULT_TOPIC_NAME_DEPTH_SENSOR_CAMERA_INFO),
    ],
    # Realsense driver from GitHub. aligned_depth_to_color is its
    # depth on the colour image's pixel grid, published with align_depth.enable in params_file
    'realsense': [
        ('/camera/realsense/color/image_raw', DEFAULT_TOPIC_NAME_CAMERA_IMAGE),
        ('/camera/realsense/color/camera_info', DEFAULT_TOPIC_NAME_CAMERA_INFO),
        ('/camera/realsense/aligned_depth_to_color/image_raw', DEFAULT_TOPIC_NAME_CAMERA_DEPTH),
    ],
    # Generic v4l2_camera driver from GitHub. Like the Blackfly's, its calibration service ignores
    # the node's namespace and is created at the root. Co-authored by Claude Code
    'webcam': [
        ('/camera/webcam/image_raw', DEFAULT_TOPIC_NAME_CAMERA_IMAGE),
        ('/camera/webcam/camera_info', DEFAULT_TOPIC_NAME_CAMERA_INFO),
        ('/set_camera_info', DEFAULT_SERVICE_NAME_CAMERA_SET_INFO),
    ],
    # FLIR Blackfly S through the released spinnaker_camera_driver. Its calibration service
    # ignores the node's namespace and is created at the root
    'blackfly': [
        ('/camera/blackfly/image_raw', DEFAULT_TOPIC_NAME_CAMERA_IMAGE),
        ('/camera/blackfly/camera_info', DEFAULT_TOPIC_NAME_CAMERA_INFO),
        ('/set_camera_info', DEFAULT_SERVICE_NAME_CAMERA_SET_INFO),
    ],
    # e-con See3CAM_CU40 RGB-IR camera through its node from this framework. Its infrared pixels
    # are part of the colour sensor, so the infrared image is on the colour image's grid
    'cu40': [
        ('/camera/cu40/image_raw', DEFAULT_TOPIC_NAME_CAMERA_IMAGE),
        ('/camera/cu40/camera_info', DEFAULT_TOPIC_NAME_CAMERA_INFO),
        ('/camera/cu40/ir/image_raw', DEFAULT_TOPIC_NAME_CAMERA_IR),
        ('/camera/cu40/set_camera_info', DEFAULT_SERVICE_NAME_CAMERA_SET_INFO),
    ],
    # Event camera through the released metavision_driver: its renderer's images become the
    # camera image, and the renderer reads the events from the neutral name as well. The
    # driver publishes no camera_info
    'event': [
        ('/camera/event/events', DEFAULT_TOPIC_NAME_CAMERA_EVENTS),
        ('/camera/event_renderer/events', DEFAULT_TOPIC_NAME_CAMERA_EVENTS),
        ('/camera/event_renderer/image_raw', DEFAULT_TOPIC_NAME_CAMERA_IMAGE),
    ],
}
# For error messages, so they list every camera CAMERA_DRIVER_REMAPPINGS knows
CAMERA_NAMES_TEXT = ', '.join(CAMERA_DRIVER_REMAPPINGS)

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
# The cameras' sections in the parameter files, which hold their serials
BRIO_NODE_PARAMETERS_KEY = '/camera/brio/logitech_brio_node'
BLACKFLY_NODE_PARAMETERS_KEY = '/camera/blackfly'
CAPTURE_CAMERA_NODE_PARAMETERS_KEY = '/capture_camera/blackfly'
# Driver mapping of the capture camera's ROS parameters onto its settings, next to par_setup.yaml
CAPTURE_CAMERA_SETTINGS_MAPPING_FILE_NAME = 'blackfly_s_software_trigger.yaml'
CU40_NODE_PARAMETERS_KEY = '/camera/cu40/see3cam_cu40_node'
# Spelled as par_setup.yaml spells them: the Kinect driver sets its node name in code, without a leading /
KINECT_NODE_PARAMETERS_KEY = 'k4a_ros_device_node'
REALSENSE_NODE_PARAMETERS_KEY = '/camera/realsense'
# The cameras whose driver opens one unit by its serial: the node section and the serial parameter
# in it, which also make the intrinsics file name per unit (get_camera_info_file_name). Special
# case: ROS has no convention for a serial parameter, so each driver's name is listed here
CAMERA_SERIAL_SOURCE_BY_CAMERA = {
    'brio': (BRIO_NODE_PARAMETERS_KEY, 'serial'),
    'cu40': (CU40_NODE_PARAMETERS_KEY, 'serial'),
    'blackfly': (BLACKFLY_NODE_PARAMETERS_KEY, 'serial_number'),
    'kinect': (KINECT_NODE_PARAMETERS_KEY, 'sensor_sn'),
    'realsense': (REALSENSE_NODE_PARAMETERS_KEY, 'serial_no'),
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
    node_parameters_key, serial_parameter_name = CAMERA_SERIAL_SOURCE_BY_CAMERA[camera]
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
def create_camera_serial_override_parameters(context, camera):
    """Return the driver parameters that open the unit camera_serial:= names, [] without it."""
    if not get_camera_serial_launch_argument(context):
        return []
    if camera not in CAMERA_SERIAL_SOURCE_BY_CAMERA:
        return []
    _, serial_parameter_name = CAMERA_SERIAL_SOURCE_BY_CAMERA[camera]
    serial = get_camera_serial(context, camera)
    # As text: launch would read a serial of digits as a number, which the drivers refuse
    return [{serial_parameter_name: ParameterValue(serial, value_type=str)}]


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


# Co-authored by Claude Code: the camera list in the message comes from CAMERA_DRIVER_REMAPPINGS
def get_chosen_camera(context):
    """Return the camera launch argument, or else the camera of the parameter files' par_launch."""
    camera = LaunchConfiguration('camera').perform(context)
    if not camera:
        camera = read_launch_section(context)['camera']
    # Without this, an empty or misspelt camera would end as a KeyError deep in a launch file
    if camera not in CAMERA_DRIVER_REMAPPINGS:
        raise RuntimeError(f'[launch_helpers]: unknown camera {camera!r}: pass camera:= with one '
                           f'of {CAMERA_NAMES_TEXT}, or set par_launch.camera in the params_file')
    return camera


# Co-authored by Claude Code: the final error names the gap it catches, the Blackfly
def create_camera_nodes(context, camera):
    """Create the camera's driver and its mount transform, for each of CAMERA_DRIVER_REMAPPINGS."""
    if camera == 'brio':
        # The Brio node itself publishes brio_link -> brio_optical_frame
        return [*create_logitech_brio_node(context),
                *create_mount_tf_publisher(context, 'brio_tf_publisher', 'brio_link')]
    if camera == 'kinect':
        # The driver itself publishes camera_base -> depth_camera_link -> rgb_camera_link
        return [create_kinect_driver_node(context),
                *create_mount_tf_publisher(context, 'kinect_tf_publisher', 'camera_base')]
    if camera == 'realsense':
        # The driver itself publishes realsense_link -> realsense_color_frame ->
        # realsense_color_optical_frame
        return [create_realsense_driver_node(context),
                *create_mount_tf_publisher(context, 'realsense_tf_publisher', 'realsense_link')]
    if camera == 'webcam':
        return [*create_webcam_nodes(context),
                *create_mount_tf_publisher(context, 'webcam_tf_publisher', 'webcam_link')]
    if camera == 'blackfly':
        return [*create_blackfly_nodes(context),
                *create_mount_tf_publisher(context, 'blackfly_tf_publisher', 'blackfly_link')]
    if camera == 'cu40':
        # The CU40 node itself publishes cu40_link -> cu40_optical_frame
        return [*create_see3cam_cu40_node(context),
                *create_mount_tf_publisher(context, 'cu40_tf_publisher', 'cu40_link')]
    if camera == 'event':
        return [*create_event_camera_nodes(context),
                *create_mount_tf_publisher(context, 'event_tf_publisher', 'event_link')]
    # get_chosen_camera already rejects unknown cameras, so this is a camera in
    # CAMERA_DRIVER_REMAPPINGS without a start above
    raise ValueError(f'[launch_helpers]: create_camera_nodes cannot start camera {camera!r}: add '
                     f'it next to the others ({CAMERA_NAMES_TEXT})')


# Co-authored by Claude Code: builds the calibration path in named steps, one file per Brio unit
# in the profile's intrinsics folder
def create_logitech_brio_node(context):
    """Create the Brio with the parameter files and its unit's calibration."""
    # cameracalibrator's COMMIT writes it there
    camera_info_file_name = get_camera_info_file_name_of_unit(
        'brio', get_camera_serial(context, 'brio'))
    camera_info_url = get_camera_info_url(context, camera_info_file_name)
    return [Node(
        package='logitech_brio',
        executable='logitech_brio',
        name='logitech_brio_node',
        output='screen',
        emulate_tty=True,
        parameters=[*get_params_file_paths(context),
                    {'camera_info_url': camera_info_url},
                    *create_camera_serial_override_parameters(context, 'brio')],
        remappings=CAMERA_DRIVER_REMAPPINGS['brio'],
    )]


# Written by Claude Code
def create_see3cam_cu40_node(context):
    """Create the See3CAM_CU40 with the parameter files and its unit's calibration."""
    # In the profile's intrinsics folder like the Brio's, per unit through serial
    camera_info_file_name = get_camera_info_file_name_of_unit(
        'cu40', get_camera_serial(context, 'cu40'))
    camera_info_url = get_camera_info_url(context, camera_info_file_name)
    return [Node(
        package='see3cam_cu40',
        executable='see3cam_cu40',
        name='see3cam_cu40_node',
        output='screen',
        emulate_tty=True,
        parameters=[*get_params_file_paths(context),
                    {'camera_info_url': camera_info_url},
                    *create_camera_serial_override_parameters(context, 'cu40')],
        remappings=CAMERA_DRIVER_REMAPPINGS['cu40'],
    )]


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


# Co-authored by Claude Code: name, and the parameter files with the profile
def create_kinect_driver_node(context):
    """Create the Azure Kinect driver with the parameter files."""
    # No name override: the driver runs several rclcpp nodes in one process, and name= would
    # rename all of them
    return Node(
        package='azure_kinect_ros_driver',
        executable='node',
        output='screen',
        emulate_tty=True,
        parameters=[*get_params_file_paths(context),
                    *create_camera_serial_override_parameters(context, 'kinect')],
        remappings=CAMERA_DRIVER_REMAPPINGS['kinect'],
    )


# Co-authored by Claude Code: name, and the parameter files with the profile
def create_realsense_driver_node(context):
    """Create an Intel RealSense (e.g. D435) with the parameter files, as /camera/realsense."""
    return Node(
        package='realsense2_camera',
        executable='realsense2_camera_node',
        name='realsense',
        namespace='/camera',
        output='screen',
        emulate_tty=True,
        # camera_name prefixes the driver's TF frames (realsense_link, ...), which the mount
        # transform below attaches to, so it is set here and not in params_file
        parameters=[*get_params_file_paths(context),
                    {'camera_name': 'realsense'},
                    *create_camera_serial_override_parameters(context, 'realsense')],
        remappings=CAMERA_DRIVER_REMAPPINGS['realsense'],
    )


# Co-authored by Claude Code: builds the calibration path in the profile's intrinsics folder,
# resolves the parameter files, the optical frame transform from create_optical_frame_tf_publisher
def create_webcam_nodes(context):
    """Create a generic UVC webcam with v4l2_camera, and its body -> optical frame transform."""
    # In the profile's intrinsics folder like the Brio's; cameracalibrator's COMMIT writes it
    # there. Simplification: v4l2_camera exposes no serial, so the ID is just 'webcam' and every
    # webcam shares one file. Upgrade: key it by the /dev/v4l/by-id/ name of video_device
    camera_info_url = get_camera_info_url(context,
                                          get_camera_info_file_name_of_unit('webcam', ''))
    return [
        # Settings (device, size, encoding, frame) under /camera/webcam/webcam_node in params_file
        Node(
            package='v4l2_camera',
            executable='v4l2_camera_node',
            name='webcam_node',
            namespace='/camera/webcam',
            output='screen',
            emulate_tty=True,
            parameters=[*get_params_file_paths(context),
                        {'camera_info_url': camera_info_url}],
            remappings=CAMERA_DRIVER_REMAPPINGS['webcam'],
        ),
        create_optical_frame_tf_publisher('webcam'),
    ]


# Written by Claude Code
def create_blackfly_nodes(context):
    """Create a FLIR Blackfly S with spinnaker_camera_driver, and its optical frame transform."""
    # In the profile's intrinsics folder like the Brio's, per unit through serial_number
    camera_info_file_name = get_camera_info_file_name_of_unit(
        'blackfly', get_camera_serial(context, 'blackfly'))
    camera_info_url = get_camera_info_url(context, camera_info_file_name)
    # The driver maps its ROS parameters onto the camera's settings with this file, which ships
    # with the driver for the whole Blackfly S series
    camera_settings_mapping_path = os.path.join(
        get_package_share_directory('spinnaker_camera_driver'), 'config', 'blackfly_s.yaml')
    return [
        Node(
            package='spinnaker_camera_driver',
            executable='camera_driver_node',
            name='blackfly',
            namespace='/camera',
            output='screen',
            emulate_tty=True,
            # frame_id must match the optical frame transform below, so it is set here and not in
            # params_file. The driver spells its calibration parameter camerainfo_url
            parameters=[*get_params_file_paths(context),
                        {'parameter_file': camera_settings_mapping_path,
                         'camerainfo_url': camera_info_url,
                         'frame_id': 'blackfly_optical_frame'},
                        *create_camera_serial_override_parameters(context, 'blackfly')],
            remappings=CAMERA_DRIVER_REMAPPINGS['blackfly'],
        ),
        create_optical_frame_tf_publisher('blackfly'),
    ]


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


# Written by Claude Code
def create_event_camera_nodes(context):
    """Create an event camera, a renderer of its events as images, and its optical frame."""
    # TODO: intrinsic calibration. The driver publishes no camera_info and offers no
    # set_camera_info, so scripts/run_cameracalibrator.sh cannot store a calibration yet:
    # 1. A node that loads camera_info_event.yaml from FOLDER_PATH_CAMERA_INTRINSICS (as
    #    camera_info_url, like the other cameras), publishes /camera/camera_info with each image's
    #    header and serves /camera/set_camera_info. First check whether ROS 2 already ships one;
    #    otherwise a small node built on camera_info_manager.
    # 2. A blink source: utils/checkerboard.png full screen on a movable display (not the
    #    projector, the board needs many poses), alternating with black at a few Hz, slower than
    #    the renderer's fps. Only the white squares fire, so each rendered image shows the board.
    #    Not board and inverse: then every square fires, and a slice with two switches is uniform
    event_camera_actions = []
    # OpenEB finds plugins that a camera maker ships separately only through this variable.
    # Without it such a camera fails with "cannot open default camera", which names no cause
    if not os.environ.get('MV_HAL_PLUGIN_PATH'):
        event_camera_actions.append(LogInfo(
            msg='[launch_helpers]: MV_HAL_PLUGIN_PATH is not set: an event camera whose maker '
                'ships its own OpenEB plugin is not found. Set it in this shell, e.g. for a '
                'SilkyEvCam: export MV_HAL_PLUGIN_PATH=/usr/lib/CenturyArks/hal/plugins'))
    # Settings (serial, biases, trigger) under /camera/event in params_file. Publishes the
    # events only while something subscribes. frame_id must match the optical frame transform
    # below, so it is set here and not in params_file
    event_camera_actions.append(Node(
        package='metavision_driver',
        executable='driver_node',
        name='event',
        namespace='/camera',
        output='screen',
        emulate_tty=True,
        parameters=[*get_params_file_paths(context),
                    {'frame_id': 'event_optical_frame'}],
        remappings=CAMERA_DRIVER_REMAPPINGS['event'],
    ))
    # Collects the events into the camera images (rate and style under /camera/event_renderer in
    # params_file). It reads events only while something subscribes to the images, and its
    # images carry the events' frame_id
    event_camera_actions.append(Node(
        package='event_camera_renderer',
        executable='renderer_node',
        name='event_renderer',
        namespace='/camera',
        output='screen',
        emulate_tty=True,
        parameters=get_params_file_paths(context),
        remappings=CAMERA_DRIVER_REMAPPINGS['event'],
    ))
    event_camera_actions.append(create_optical_frame_tf_publisher('event'))
    return event_camera_actions


# Co-authored by Claude Code: one transform for every driver that does not publish it itself
def create_optical_frame_tf_publisher(camera):
    """Create the publisher of <camera>_link -> <camera>_optical_frame."""
    # What the Brio node publishes itself: z forward, y down (REP 103), roll -90, yaw -90 deg
    return Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name=f'{camera}_optical_tf_publisher',
        arguments=['--frame-id', f'{camera}_link', '--child-frame-id', f'{camera}_optical_frame',
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
