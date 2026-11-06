# Co-authored by Claude Code: written by Claude Code, since edited by hand; Claude Code also added
# the setup profiles (profile launch argument, merged parameter files, per-profile extrinsics,
# per-unit Brio intrinsics)
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
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
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
    ],
    # Realsense driver from GitHub. aligned_depth_to_color is its
    # depth on the colour image's pixel grid, published with align_depth.enable in params_file
    'realsense': [
        ('/camera/realsense/color/image_raw', DEFAULT_TOPIC_NAME_CAMERA_IMAGE),
        ('/camera/realsense/color/camera_info', DEFAULT_TOPIC_NAME_CAMERA_INFO),
        ('/camera/realsense/aligned_depth_to_color/image_raw', DEFAULT_TOPIC_NAME_CAMERA_DEPTH),
    ],
    # Generic v4l2_camera driver from GitHub
    'webcam': [
        ('/camera/webcam/image_raw', DEFAULT_TOPIC_NAME_CAMERA_IMAGE),
        ('/camera/webcam/camera_info', DEFAULT_TOPIC_NAME_CAMERA_INFO),
        ('/camera/webcam/set_camera_info', DEFAULT_SERVICE_NAME_CAMERA_SET_INFO),
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
# params_file, and each profile keeps its extrinsics in FOLDER_PATH_EXTRINSICS/<name>
FOLDER_PATH_PROFILES = 'profiles'
# Profile names and camera serials become parts of file names: nothing that could leave the folder
FILE_NAME_PART_PATTERN = re.compile(r'[A-Za-z0-9_-]+')
# The cameras' sections in the parameter files, which hold their serials
BRIO_NODE_PARAMETERS_KEY = '/camera/brio/logitech_brio_node'
BLACKFLY_NODE_PARAMETERS_KEY = '/camera/blackfly'
CU40_NODE_PARAMETERS_KEY = '/camera/cu40/see3cam_cu40_node'
# What a camera pose needs, in the measured camera_pose_<camera>.yaml and in the placeholder
POSE_TRANSLATION_KEYS = [f'translation.{axis}' for axis in 'xyz']
POSE_ROTATION_KEYS = [f'rotation.{axis}' for axis in 'xyzw']
CAMERA_POSE_KEYS = POSE_TRANSLATION_KEYS + POSE_ROTATION_KEYS


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


# Co-authored by Claude Code
def get_extrinsics_folder_path(context):
    """Return the folder of the extrinsics below config/: the profile's own, or the shared one."""
    profile_name = get_profile_name(context)
    if profile_name:
        return f'{FOLDER_PATH_EXTRINSICS}/{profile_name}'
    return FOLDER_PATH_EXTRINSICS


# Co-authored by Claude Code: reads the merged parameter files
def read_launch_section(context):
    """Return the par_launch section of the parameter files: the camera and which nodes run."""
    return read_merged_parameters(context)['par_launch']['ros__parameters']


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
def create_logitech_brio_node(context):
    """Create the Brio with the parameter files and its unit's calibration."""
    # cameracalibrator's COMMIT writes it there
    camera_info_file_name = get_camera_info_file_name(context, 'brio', BRIO_NODE_PARAMETERS_KEY,
                                                      'serial')
    camera_info_relative_path = f'{FOLDER_PATH_CAMERA_INTRINSICS}/{camera_info_file_name}'
    camera_info_path = get_path_in_config_folder(camera_info_relative_path)
    camera_info_url = f'file://{camera_info_path}'
    return [Node(
        package='logitech_brio',
        executable='logitech_brio',
        name='logitech_brio_node',
        output='screen',
        emulate_tty=True,
        parameters=[*get_params_file_paths(context),
                    {'camera_info_url': camera_info_url}],
        remappings=CAMERA_DRIVER_REMAPPINGS['brio'],
    )]


# Written by Claude Code
def create_see3cam_cu40_node(context):
    """Create the See3CAM_CU40 with the parameter files and its unit's calibration."""
    # In FOLDER_PATH_CAMERA_INTRINSICS like the Brio's, per unit through serial
    camera_info_file_name = get_camera_info_file_name(context, 'cu40', CU40_NODE_PARAMETERS_KEY,
                                                      'serial')
    camera_info_relative_path = f'{FOLDER_PATH_CAMERA_INTRINSICS}/{camera_info_file_name}'
    camera_info_path = get_path_in_config_folder(camera_info_relative_path)
    camera_info_url = f'file://{camera_info_path}'
    return [Node(
        package='see3cam_cu40',
        executable='see3cam_cu40',
        name='see3cam_cu40_node',
        output='screen',
        emulate_tty=True,
        parameters=[*get_params_file_paths(context),
                    {'camera_info_url': camera_info_url}],
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
    return f'camera_info_{camera}_{serial}.yaml'


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
        parameters=get_params_file_paths(context),
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
                    {'camera_name': 'realsense'}],
        remappings=CAMERA_DRIVER_REMAPPINGS['realsense'],
    )


# Co-authored by Claude Code: builds the calibration path in named steps, resolves the parameter
# files, the optical frame transform from create_optical_frame_tf_publisher
def create_webcam_nodes(context):
    """Create a generic UVC webcam with v4l2_camera, and its body -> optical frame transform."""
    # In FOLDER_PATH_CAMERA_INTRINSICS like the Brio's; cameracalibrator's COMMIT writes it there.
    # Simplification: one file for every webcam, since v4l2_camera exposes no serial. Upgrade: key
    # it by the /dev/v4l/by-id/ name of video_device
    camera_info_relative_path = f'{FOLDER_PATH_CAMERA_INTRINSICS}/camera_info_webcam.yaml'
    camera_info_path = get_path_in_config_folder(camera_info_relative_path)
    camera_info_url = f'file://{camera_info_path}'
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
    # In FOLDER_PATH_CAMERA_INTRINSICS like the Brio's, per unit through serial_number
    camera_info_file_name = get_camera_info_file_name(
        context, 'blackfly', BLACKFLY_NODE_PARAMETERS_KEY, 'serial_number')
    camera_info_relative_path = f'{FOLDER_PATH_CAMERA_INTRINSICS}/{camera_info_file_name}'
    camera_info_path = get_path_in_config_folder(camera_info_relative_path)
    camera_info_url = f'file://{camera_info_path}'
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
                         'frame_id': 'blackfly_optical_frame'}],
            remappings=CAMERA_DRIVER_REMAPPINGS['blackfly'],
        ),
        create_optical_frame_tf_publisher('blackfly'),
    ]


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
    extrinsics_folder_path = get_extrinsics_folder_path(context)
    measured_pose_relative_path = f'{extrinsics_folder_path}/camera_pose_{camera}.yaml'
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
    extrinsics_folder_path = get_extrinsics_folder_path(context)
    corners_relative_path = f'{extrinsics_folder_path}/projection_corners_{camera}.yaml'
    mapping_relative_path = f'{extrinsics_folder_path}/projection_mapping_{camera}.yaml'
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
