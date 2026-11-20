# Written by Claude Code
"""
Where a PAR setup keeps its files, and how its parameter files are read.

The setup's parameter files (par_setup.yaml, then the profile's file), its profiles and its
machine-local calibrations below config/. Imports nothing from launch: the launch files read the
launch arguments in launch_helpers and pass their values here.
"""

import os
import re

from ament_index_python.packages import get_package_share_directory
import yaml


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
# The parameter file section the launch files read themselves; no node has this name
PAR_LAUNCH_SECTION_NAME = 'par_launch'


def get_installed_par_setup_path():
    """Return the path of the installed default par_setup.yaml, the params_file of every launch."""
    return os.path.join(get_package_share_directory('par_framework_core'), 'config',
                        'par_setup.yaml')


def get_path_in_config_folder(relative_path):
    """Return the absolute path of relative_path below the folder of the real par_setup.yaml."""
    # The default par_setup.yaml, not params_file: the calibrations are shared by every parameter
    # file. realpath follows the --symlink-install links back to the source folder, so files
    # written there survive rebuilds
    config_folder_path = os.path.dirname(os.path.realpath(get_installed_par_setup_path()))
    return os.path.join(config_folder_path, relative_path)


def create_folder_of_file(file_path):
    """Create the folder file_path lies in, for a file that is written there."""
    # Only for writers: the nodes that write calibrations (camera_info_manager,
    # camera_pose_calibrator, ...) open the file without creating its folder. Code that only
    # checks or reads a file must not call this, or it leaves empty folders behind, e.g. for a
    # profile that was deleted meanwhile
    os.makedirs(os.path.dirname(file_path), exist_ok=True)


def check_profile_name(profile_name):
    """Raise RuntimeError naming the fix unless profile_name is '' or a valid profile file name."""
    if profile_name and not FILE_NAME_PART_PATTERN.fullmatch(profile_name):
        raise RuntimeError(f'[setup_files]: profile:={profile_name}: use only letters, digits, '
                           f'_ and -, the name of a file in config/{FOLDER_PATH_PROFILES}/ '
                           f'without .yaml')


def get_profile_file_path(profile_name):
    """Return the path of a profile's file: config/profiles/<profile_name>.yaml."""
    return get_path_in_config_folder(
        f'{FOLDER_PATH_PROFILES}/{profile_name}{PROFILE_FILE_EXTENSION}')


def get_params_file_paths_of_profile(params_file_path, profile_name):
    """
    Return the parameter files in the order ROS applies them: params_file, then the profile.

    profile_name '' means no profile. Raises RuntimeError naming the fix when the profile's name
    is invalid or its file does not exist.
    """
    check_profile_name(profile_name)
    params_file_paths = [params_file_path]
    if profile_name:
        profile_path = get_profile_file_path(profile_name)
        if not os.path.exists(profile_path):
            raise RuntimeError(f'[setup_files]: profile {profile_name} has no file '
                               f'{profile_path}: create it with only the sections and keys that '
                               f'differ from par_setup.yaml, written the same way')
        params_file_paths.append(profile_path)
    return params_file_paths


def read_params_file(params_file_path):
    """
    Return a parameter file's node sections as a dict, {} for an empty file.

    Raises RuntimeError naming the fix when the file holds no mapping, e.g. a hand-written profile
    with a stray list or value.
    """
    with open(params_file_path) as params_file:
        file_parameters = yaml.safe_load(params_file) or {}
    if not isinstance(file_parameters, dict):
        raise RuntimeError(f'[setup_files]: {params_file_path} holds no node sections: write it '
                           f'like par_setup.yaml, node name, ros__parameters, keys')
    return file_parameters


def read_merged_parameters(params_file_paths):
    """
    Return the parameter files merged as ROS merges them for a node: the later file wins per key.

    For what the launch files read themselves (par_launch, the placeholder camera poses); the
    nodes get the files themselves and merge them alone.
    """
    merged_parameters = {}
    for params_file_path in params_file_paths:
        _merge_parameters(merged_parameters, read_params_file(params_file_path))
    return merged_parameters


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


def read_launch_section(params_file_paths):
    """Return the merged par_launch section of the parameter files: cameras and which nodes run."""
    return read_merged_parameters(params_file_paths)[PAR_LAUNCH_SECTION_NAME]['ros__parameters']


def get_intrinsics_folder_path(profile_name):
    """Return the folder of the intrinsics below config/: the profile's own, or the shared one."""
    # Per profile, so recalibrating a camera for one setup (e.g. after refocusing it) leaves the
    # other setups' calibrations alone
    if profile_name:
        return f'{FOLDER_PATH_CAMERA_INTRINSICS}/{profile_name}'
    return FOLDER_PATH_CAMERA_INTRINSICS


def get_camera_unit_id(camera_type, serial):
    """
    Return the identifier of a camera unit: '<type>_<serial>', or '<type>' without a serial.

    It ends the name of the unit's intrinsics file, so two units of one type never share or
    overwrite one.
    """
    if not serial:
        return camera_type
    return f'{camera_type}_{serial}'


def get_camera_info_file_name_of_unit(camera_type, serial):
    """Return the intrinsics file name of one unit: camera_info_<camera unit id>.yaml."""
    return f'camera_info_{get_camera_unit_id(camera_type, serial)}.yaml'


def get_unit_intrinsics_file_path(profile_name, camera_type, serial):
    """Return the absolute path of a camera unit's intrinsics file in the intrinsics folder."""
    intrinsics_folder_path = get_intrinsics_folder_path(profile_name)
    camera_info_file_name = get_camera_info_file_name_of_unit(camera_type, serial)
    return get_path_in_config_folder(f'{intrinsics_folder_path}/{camera_info_file_name}')


def get_extrinsics_folder_path(profile_name):
    """Return the folder of the extrinsics below config/: the profile's own, or the shared one."""
    if profile_name:
        return f'{FOLDER_PATH_EXTRINSICS}/{profile_name}'
    return FOLDER_PATH_EXTRINSICS


def get_extrinsics_relative_path(profile_name, file_prefix, camera_name):
    """
    Return the extrinsics file <file_prefix>_<camera name>.yaml of a camera, below config/.

    file_prefix is camera_pose, projection_mapping or projection_corners. Named after the camera,
    not its unit: the pose belongs to the mount, so a replaced unit keeps it.
    """
    return f'{get_extrinsics_folder_path(profile_name)}/{file_prefix}_{camera_name}.yaml'
