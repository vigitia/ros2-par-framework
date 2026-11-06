# Written by Claude Code
"""
Profiles API of the setup wizard backend: the hardware setups (config/profiles/<name>.yaml).

Lists them with their cameras, sensor nodes and apps and each camera's calibration state, and
remembers the one selected last time.
"""

import os

from ament_index_python.packages import get_package_share_directory
from fastapi import APIRouter, HTTPException
from launch import LaunchContext
from par_framework_core.launch_helpers import (BLACKFLY_NODE_PARAMETERS_KEY,
                                               BRIO_NODE_PARAMETERS_KEY,
                                               CAPTURE_CAMERA_NODE_PARAMETERS_KEY,
                                               CU40_NODE_PARAMETERS_KEY,
                                               FILE_NAME_PART_PATTERN,
                                               FOLDER_PATH_CAMERA_INTRINSICS,
                                               FOLDER_PATH_PROFILES, get_camera_info_file_name,
                                               get_extrinsics_folder_path,
                                               get_invalid_pose_keys,
                                               get_path_in_config_folder, read_launch_section)
from pydantic import BaseModel
import yaml

PROFILE_FILE_EXTENSION = '.yaml'
# In the profiles folder, which is gitignored as a whole: the selection belongs to this machine.
# Hidden and without .yaml, so it is never listed as a profile.
LAST_SELECTED_PROFILE_FILE_NAME = '.setup_wizard_last_selected_profile'

# How the par_launch switches are sorted on a profile's card. Every other switch that is on
# counts as a sensor node, so a new detector shows up without a change here.
APP_LAUNCH_SWITCH_NAMES = ('demo_app', 'rendering_manager')
# Neither sensor nodes nor apps; the capture camera is listed with the cameras instead.
HIDDEN_LAUNCH_SWITCH_NAMES = ('projection_mask', 'rviz', 'capture_camera')
# The capture camera is always a second Blackfly (launch_helpers.create_capture_camera_node).
CAPTURE_CAMERA_DISPLAY_NAME = 'blackfly (capture)'

# Where each camera's intrinsics file name comes from, as in its create_*_node function in
# launch_helpers: the node section and the serial parameter that make the name per unit.
# Simplification: this copies knowledge of those functions. Upgrade: a launch_helpers function
# that returns a camera's intrinsics path, used by them and by this backend.
INTRINSICS_SERIAL_SOURCE_BY_CAMERA = {
    'brio': (BRIO_NODE_PARAMETERS_KEY, 'serial'),
    'cu40': (CU40_NODE_PARAMETERS_KEY, 'serial'),
    'blackfly': (BLACKFLY_NODE_PARAMETERS_KEY, 'serial_number'),
}
# v4l2_camera exposes no serial, so every webcam shares one file.
WEBCAM_INTRINSICS_FILE_NAME = 'camera_info_webcam.yaml'
# Their drivers publish the calibration stored in the device.
FACTORY_INTRINSICS_CAMERA_NAMES = ('kinect', 'realsense')

# Calibration states as the app receives them.
INTRINSICS_STATE_CALIBRATED = 'calibrated'
INTRINSICS_STATE_FACTORY = 'factory'
INTRINSICS_STATE_MISSING = 'missing'
# The event camera publishes no camera_info, so it cannot be calibrated yet.
INTRINSICS_STATE_UNSUPPORTED = 'unsupported'
POSE_STATE_MEASURED = 'measured'
POSE_STATE_PLACEHOLDER = 'placeholder'
# The measured pose file exists but lacks keys or numbers; a launch would stop on it.
POSE_STATE_INVALID = 'invalid'
# The capture camera publishes no transforms yet, so it has no pose.
POSE_STATE_UNSUPPORTED = 'unsupported'

profiles_router = APIRouter()


class CameraCalibrationSummary(BaseModel):
    camera_display_name: str
    # One of the INTRINSICS_STATE_* values.
    intrinsics_state: str
    # One of the POSE_STATE_* values.
    pose_state: str


class ProfileSummary(BaseModel):
    profile_name: str
    cameras: list[CameraCalibrationSummary]
    sensor_node_names: list[str]
    app_names: list[str]
    # Set when the profile's files cannot be read; the lists are empty then.
    profile_error_text: str | None = None


class ProfileListResponse(BaseModel):
    profiles: list[ProfileSummary]
    # None when nothing was selected yet, or the profile selected last time no longer exists.
    last_selected_profile_name: str | None


class LastSelectedProfileRequest(BaseModel):
    profile_name: str


@profiles_router.get('/api/profiles')
def get_profile_list() -> ProfileListResponse:
    """List the profiles (config/profiles/<name>.yaml) with what they run, and the last choice."""
    profile_names = _read_profile_names()
    profile_summaries = []
    for profile_name in profile_names:
        profile_summaries.append(_read_profile_summary(profile_name))
    last_selected_profile_name = _read_last_selected_profile_name()
    if last_selected_profile_name not in profile_names:
        last_selected_profile_name = None
    return ProfileListResponse(profiles=profile_summaries,
                               last_selected_profile_name=last_selected_profile_name)


@profiles_router.put('/api/profiles/last-selected')
def set_last_selected_profile(request: LastSelectedProfileRequest) -> None:
    """Remember the selected profile, so the start screen preselects it next time."""
    # The name ends up in a file path and in profile:=, so it must be an existing profile name.
    if request.profile_name not in _read_profile_names():
        raise HTTPException(status_code=404, detail=f'No profile named {request.profile_name!r}')
    with open(_get_last_selected_profile_path(), 'w') as last_selected_profile_file:
        last_selected_profile_file.write(request.profile_name)


def _read_profile_names() -> list[str]:
    """Return the profile file names, sorted, without those that profile:= would reject."""
    profiles_folder_path = get_path_in_config_folder(FOLDER_PATH_PROFILES)
    if not os.path.isdir(profiles_folder_path):
        return []
    profile_names = []
    for file_name in os.listdir(profiles_folder_path):
        profile_name, file_extension = os.path.splitext(file_name)
        if file_extension != PROFILE_FILE_EXTENSION:
            continue
        if not FILE_NAME_PART_PATTERN.fullmatch(profile_name):
            continue
        profile_names.append(profile_name)
    return sorted(profile_names)


def _read_profile_summary(profile_name: str) -> ProfileSummary:
    """Return the cameras, sensor nodes and apps the profile switches on in par_launch."""
    profile_launch_context = _create_profile_launch_context(profile_name)
    try:
        launch_section = read_launch_section(profile_launch_context)
        main_camera_name = launch_section['camera']
        cameras = [CameraCalibrationSummary(
            camera_display_name=main_camera_name,
            intrinsics_state=_read_main_camera_intrinsics_state(profile_launch_context,
                                                                main_camera_name),
            pose_state=_read_camera_pose_state(profile_launch_context, main_camera_name))]
        if launch_section.get('capture_camera') is True:
            cameras.append(CameraCalibrationSummary(
                camera_display_name=CAPTURE_CAMERA_DISPLAY_NAME,
                intrinsics_state=_read_capture_camera_intrinsics_state(profile_launch_context),
                pose_state=POSE_STATE_UNSUPPORTED))
    except (RuntimeError, KeyError, OSError, yaml.YAMLError) as error:
        # A profile is written by hand: one broken file must not hide the other profiles.
        return ProfileSummary(profile_name=profile_name, cameras=[], sensor_node_names=[],
                              app_names=[], profile_error_text=str(error))

    sensor_node_names = []
    app_names = []
    for switch_name, switch_value in launch_section.items():
        if switch_value is not True:
            continue
        if switch_name in HIDDEN_LAUNCH_SWITCH_NAMES:
            continue
        if switch_name in APP_LAUNCH_SWITCH_NAMES:
            app_names.append(switch_name)
        else:
            sensor_node_names.append(switch_name)
    return ProfileSummary(profile_name=profile_name, cameras=cameras,
                          sensor_node_names=sensor_node_names, app_names=app_names)


def _read_main_camera_intrinsics_state(profile_launch_context: LaunchContext,
                                       camera_name: str) -> str:
    """Return whether the profile's main camera has its lens calibration (INTRINSICS_STATE_*)."""
    if camera_name in FACTORY_INTRINSICS_CAMERA_NAMES:
        return INTRINSICS_STATE_FACTORY
    if camera_name == 'webcam':
        return _get_intrinsics_file_state(WEBCAM_INTRINSICS_FILE_NAME)
    if camera_name not in INTRINSICS_SERIAL_SOURCE_BY_CAMERA:
        return INTRINSICS_STATE_UNSUPPORTED
    node_parameters_key, serial_parameter_name = INTRINSICS_SERIAL_SOURCE_BY_CAMERA[camera_name]
    intrinsics_file_name = get_camera_info_file_name(profile_launch_context, camera_name,
                                                     node_parameters_key, serial_parameter_name)
    return _get_intrinsics_file_state(intrinsics_file_name)


def _read_capture_camera_intrinsics_state(profile_launch_context: LaunchContext) -> str:
    """Return whether the capture camera, a second Blackfly, has its lens calibration."""
    intrinsics_file_name = get_camera_info_file_name(
        profile_launch_context, 'blackfly', CAPTURE_CAMERA_NODE_PARAMETERS_KEY, 'serial_number')
    return _get_intrinsics_file_state(intrinsics_file_name)


def _get_intrinsics_file_state(intrinsics_file_name: str) -> str:
    # Simplification: only checks that the file exists, not that it holds a valid calibration.
    intrinsics_path = get_path_in_config_folder(
        f'{FOLDER_PATH_CAMERA_INTRINSICS}/{intrinsics_file_name}')
    if os.path.exists(intrinsics_path):
        return INTRINSICS_STATE_CALIBRATED
    return INTRINSICS_STATE_MISSING


def _read_camera_pose_state(profile_launch_context: LaunchContext, camera_name: str) -> str:
    """Return whether the profile has a measured pose for the camera (POSE_STATE_*)."""
    # The same file launch_helpers.create_mount_tf_publisher reads instead of the placeholder.
    extrinsics_folder_path = get_extrinsics_folder_path(profile_launch_context)
    pose_path = get_path_in_config_folder(
        f'{extrinsics_folder_path}/camera_pose_{camera_name}.yaml')
    if not os.path.exists(pose_path):
        return POSE_STATE_PLACEHOLDER
    with open(pose_path) as pose_file:
        camera_pose = yaml.safe_load(pose_file)
    if get_invalid_pose_keys(camera_pose):
        return POSE_STATE_INVALID
    return POSE_STATE_MEASURED


def _create_profile_launch_context(profile_name: str) -> LaunchContext:
    """Return a launch context like `ros2 launch ... par.launch.py profile:=<profile_name>`."""
    # So launch_helpers merges par_setup.yaml and the profile exactly as a launch does.
    profile_launch_context = LaunchContext()
    default_params_file_path = os.path.join(get_package_share_directory('par_framework_core'),
                                            'config', 'par_setup.yaml')
    profile_launch_context.launch_configurations['params_file'] = default_params_file_path
    profile_launch_context.launch_configurations['profile'] = profile_name
    return profile_launch_context


def _get_last_selected_profile_path() -> str:
    return get_path_in_config_folder(f'{FOLDER_PATH_PROFILES}/{LAST_SELECTED_PROFILE_FILE_NAME}')


def _read_last_selected_profile_name() -> str | None:
    last_selected_profile_path = _get_last_selected_profile_path()
    if not os.path.exists(last_selected_profile_path):
        return None
    with open(last_selected_profile_path) as last_selected_profile_file:
        return last_selected_profile_file.read().strip()
