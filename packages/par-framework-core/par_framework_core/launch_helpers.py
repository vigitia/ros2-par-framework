# Co-authored by Claude Code: written by Claude Code, since edited by hand
"""
Start functions shared by the launch files of par_framework_core.

Those that take the launch context are used inside OpaqueFunction(function=...), because they
need the resolved value of a launch argument (params_file, camera) to decide how the node is
started.
"""

import math
import os

from ament_index_python.packages import get_package_share_directory
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
}
# For error messages, so they list every camera CAMERA_DRIVER_REMAPPINGS knows
CAMERA_NAMES_TEXT = ', '.join(CAMERA_DRIVER_REMAPPINGS)

# The machine-local calibrations below config/ (gitignored), for get_path_in_config_folder: the
# camera intrinsics, and where camera and projection sit relative to the table
FOLDER_PATH_CAMERA_INTRINSICS = 'calibration/intrinsics'
FOLDER_PATH_EXTRINSICS = 'calibration/extrinsics'
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


# Co-authored by Claude Code: variable names
def read_launch_section(context):
    """Return the par_launch section of the parameter file: the camera and which nodes run."""
    params_file_path = LaunchConfiguration('params_file').perform(context)
    with open(params_file_path) as params_file:
        return yaml.safe_load(params_file)['par_launch']['ros__parameters']


# Co-authored by Claude Code: the camera list in the message comes from CAMERA_DRIVER_REMAPPINGS
def get_chosen_camera(context):
    """Return the camera launch argument, or else the camera of params_file's par_launch."""
    camera = LaunchConfiguration('camera').perform(context)
    if not camera:
        camera = read_launch_section(context)['camera']
    # Without this, an empty or misspelt camera would end as a KeyError deep in a launch file
    if camera not in CAMERA_DRIVER_REMAPPINGS:
        raise RuntimeError(f'[launch_helpers]: unknown camera {camera!r}: pass camera:= with one '
                           f'of {CAMERA_NAMES_TEXT}, or set par_launch.camera in the params_file')
    return camera


# Co-authored by Claude Code: the final error names the gap it catches
def create_camera_nodes(context, camera):
    """Create the camera's driver and its mount transform: brio, kinect, realsense, webcam."""
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
    # get_chosen_camera already rejects unknown cameras, so this is a camera in
    # CAMERA_DRIVER_REMAPPINGS without a start above
    raise ValueError(f'[launch_helpers]: create_camera_nodes cannot start camera {camera!r}: add '
                     f'it next to the others ({CAMERA_NAMES_TEXT})')


# Co-authored by Claude Code: builds the calibration path in named steps
def create_logitech_brio_node(context):
    """Create the Brio with params_file and its calibration from FOLDER_PATH_CAMERA_INTRINSICS."""
    # cameracalibrator's COMMIT writes it there
    camera_info_relative_path = f'{FOLDER_PATH_CAMERA_INTRINSICS}/camera_info_brio.yaml'
    camera_info_path = get_path_in_config_folder(camera_info_relative_path)
    camera_info_url = f'file://{camera_info_path}'
    return [Node(
        package='logitech_brio',
        executable='logitech_brio',
        name='logitech_brio_node',
        output='screen',
        emulate_tty=True,
        parameters=[LaunchConfiguration('params_file').perform(context),
                    {'camera_info_url': camera_info_url}],
        remappings=CAMERA_DRIVER_REMAPPINGS['brio'],
    )]


# Co-authored by Claude Code: name
def create_kinect_driver_node(context):
    """Create the Azure Kinect driver with params_file."""
    # No name override: the driver runs several rclcpp nodes in one process, and name= would
    # rename all of them
    return Node(
        package='azure_kinect_ros_driver',
        executable='node',
        output='screen',
        emulate_tty=True,
        parameters=[LaunchConfiguration('params_file').perform(context)],
        remappings=CAMERA_DRIVER_REMAPPINGS['kinect'],
    )


# Co-authored by Claude Code: name
def create_realsense_driver_node(context):
    """Create an Intel RealSense (e.g. D435) with params_file, as /camera/realsense."""
    return Node(
        package='realsense2_camera',
        executable='realsense2_camera_node',
        name='realsense',
        namespace='/camera',
        output='screen',
        emulate_tty=True,
        # camera_name prefixes the driver's TF frames (realsense_link, ...), which the mount
        # transform below attaches to, so it is set here and not in params_file
        parameters=[LaunchConfiguration('params_file').perform(context),
                    {'camera_name': 'realsense'}],
        remappings=CAMERA_DRIVER_REMAPPINGS['realsense'],
    )


# Co-authored by Claude Code: builds the calibration path in named steps, resolves params_file
def create_webcam_nodes(context):
    """Create a generic UVC webcam with v4l2_camera, and its body -> optical frame transform."""
    # In FOLDER_PATH_CAMERA_INTRINSICS like the Brio's; cameracalibrator's COMMIT writes it there
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
            parameters=[LaunchConfiguration('params_file').perform(context),
                        {'camera_info_url': camera_info_url}],
            remappings=CAMERA_DRIVER_REMAPPINGS['webcam'],
        ),
        # What the Brio node publishes itself: z forward, y down (REP 103), roll -90, yaw -90 deg
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='webcam_optical_tf_publisher',
            arguments=['--frame-id', 'webcam_link', '--child-frame-id', 'webcam_optical_frame',
                       '--qx', '-0.5', '--qy', '0.5', '--qz', '-0.5', '--qw', '0.5'],
        ),
    ]


# Co-authored by Claude Code: checks the pose before it is used
def create_mount_tf_publisher(context, publisher_name, child_frame_id):
    """
    Create the publisher of world -> child_frame_id: the measured camera pose, or the placeholder.

    The placeholder is stored under /<publisher_name> in the parameter file. The measurement is
    camera_pose_<camera>.yaml in FOLDER_PATH_EXTRINSICS, written by camera_pose_calibrator
    (<camera> is <publisher_name> without _tf_publisher), and is used while that file exists.
    """
    # static_transform_publisher takes its transform only as command-line flags: parameters from
    # a file are overridden by the flags' defaults, and without --frame-id it does not start. So
    # the pose is read from the file here, which is only possible once params_file is known.
    camera = publisher_name.removesuffix('_tf_publisher')
    measured_pose_relative_path = f'{FOLDER_PATH_EXTRINSICS}/camera_pose_{camera}.yaml'
    pose_source_path = get_path_in_config_folder(measured_pose_relative_path)
    if os.path.exists(pose_source_path):
        with open(pose_source_path) as measured_pose_file:
            pose = yaml.safe_load(measured_pose_file)
        fix_hint = (f're-run the camera pose calibration, or delete the file to use the '
                    f'placeholder /{publisher_name} in the params_file')
    else:
        pose_source_path = LaunchConfiguration('params_file').perform(context)
        with open(pose_source_path) as params_file:
            all_parameters = yaml.safe_load(params_file) or {}
        publisher_section = all_parameters.get(f'/{publisher_name}') or {}
        pose = publisher_section.get('ros__parameters')
        fix_hint = f'set them under /{publisher_name} ros__parameters in the params_file'
    # Both files can be edited by hand or cut short, and every launch with this camera reads
    # them: a gap is reported here with its file instead of ending as a bare KeyError
    invalid_keys = get_invalid_pose_keys(pose)
    if invalid_keys:
        raise RuntimeError(f'[launch_helpers]: {pose_source_path} has no finite number for '
                           f'{", ".join(invalid_keys)}: {fix_hint}')
    print(f'[launch_helpers]: {publisher_name}: camera pose from {pose_source_path}')
    transform_arguments = ['--frame-id', 'world', '--child-frame-id', child_frame_id]
    for axis in 'xyz':
        transform_arguments += [f'--{axis}', str(pose[f'translation.{axis}'])]
    for axis in 'xyzw':
        transform_arguments += [f'--q{axis}', str(pose[f'rotation.{axis}'])]
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


# Co-authored by Claude Code: name, and the paths in named steps
def create_projection_calibration_server_node(camera):
    """Create the owner of the projection corners and mapping, with the camera's files."""
    # One file per camera each: the corners are pixels of one camera's image, so another camera's
    # would point elsewhere. And while the camera poses in par_setup.yaml are placeholders, each
    # camera's table plane is its own, so a mapping only fits the camera it was calibrated with
    corners_relative_path = f'{FOLDER_PATH_EXTRINSICS}/projection_corners_{camera}.yaml'
    mapping_relative_path = f'{FOLDER_PATH_EXTRINSICS}/projection_mapping_{camera}.yaml'
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
