# Written by Claude Code
"""
Start functions shared by the launch files of par_framework_core.

Each is used as OpaqueFunction(function=...), because it needs the resolved value of a launch
argument (params_file, camera_info_url) to decide how the node is started.
"""

import os

from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import yaml


def logitech_brio_node(context):
    """Start the Brio with params_file, and camera_info_url on top if it is given."""
    parameters = [LaunchConfiguration('params_file').perform(context)]
    # Only added when set: an empty value would replace the URL from params_file with '', which
    # the node reads as the default ~/.ros/camera_info/ instead
    camera_info_url = LaunchConfiguration('camera_info_url').perform(context)
    if camera_info_url:
        parameters.append({'camera_info_url': camera_info_url})
    return [Node(
        package='logitech_brio',
        executable='logitech_brio',
        name='logitech_brio_node',
        output='screen',
        emulate_tty=True,
        parameters=parameters,
    )]


def mount_tf_publisher(context, name, child_frame_id):
    """
    Publish world -> child_frame_id: the measured camera pose, or else the placeholder.

    The placeholder is stored under /<name> in the parameter file. The measurement is
    camera_pose_<camera>.yaml next to it, written by camera_pose_calibrator (<camera> is <name>
    without _tf_publisher), and is used while that file exists.
    """
    # static_transform_publisher takes its transform only as command-line flags: parameters from
    # a file are overridden by the flags' defaults, and without --frame-id it does not start. So
    # the pose is read from the file here, which is only possible once params_file is known.
    source = next_to_params_file(context, f'camera_pose_{name.removesuffix("_tf_publisher")}.yaml')
    if os.path.exists(source):
        with open(source) as f:
            pose = yaml.safe_load(f)
    else:
        source = LaunchConfiguration('params_file').perform(context)
        with open(source) as f:
            pose = yaml.safe_load(f)[f'/{name}']['ros__parameters']
    print(f'[launch_helpers]: {name}: camera pose from {source}')
    arguments = ['--frame-id', 'world', '--child-frame-id', child_frame_id]
    for axis in 'xyz':
        arguments += [f'--{axis}', str(pose[f'translation.{axis}'])]
    for axis in 'xyzw':
        arguments += [f'--q{axis}', str(pose[f'rotation.{axis}'])]
    return [Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name=name,
        arguments=arguments,
    )]


# Points the framework nodes, which default to the Brio's topics (some hard-coded), at the Azure
# Kinect driver's topics. The driver publishes without a namespace, like in the old VIGITIA
# framework, whose depth topic /depth_to_rgb/image_raw the detectors still use.
KINECT_REMAPPINGS = [
    ('/camera/brio/image_raw', '/rgb/image_raw'),
    ('/camera/brio/camera_info', '/rgb/camera_info'),
]


def next_to_params_file(context, file_name):
    """Return the path of file_name in the folder of the real par_setup.yaml."""
    # realpath follows the --symlink-install links back to the source folder, so files written
    # there survive rebuilds, on the host and in the container alike
    params_file = os.path.realpath(LaunchConfiguration('params_file').perform(context))
    return os.path.join(os.path.dirname(params_file), file_name)


def projection_corners_node(context):
    """Start the projection corners owner with its file next to the real par_setup.yaml."""
    return [Node(
        package='projection_corners',
        executable='projection_corners',
        name='projection_corners_node',
        output='screen',
        emulate_tty=True,
        parameters=[{'projection_corners_file':
                     next_to_params_file(context, 'projection_corners.yaml')}],
    )]


def projection_mapping_node(context, camera):
    """Start the table-to-projector mapping owner with camera's file next to par_setup.yaml."""
    # One file per camera: while the camera poses in par_setup.yaml are placeholders, each
    # camera's table plane is its own, so a mapping only fits the camera it was calibrated with
    return [Node(
        package='projection_mapping',
        executable='projection_mapping',
        name='projection_mapping_node',
        output='screen',
        emulate_tty=True,
        parameters=[{'projection_mapping_file':
                     next_to_params_file(context, f'projection_mapping_{camera}.yaml')}],
    )]
