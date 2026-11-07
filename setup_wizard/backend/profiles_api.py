# Written by Claude Code
"""
Profiles API of the setup wizard backend: the hardware setups (config/profiles/<name>.yaml).

Lists them with their cameras, sensor nodes and apps and each camera's calibration state,
remembers the one selected last time, and writes node settings changed in the wizard into them.
"""

import datetime
import os
import shutil
import tempfile
import threading

from ament_index_python.packages import get_package_share_directory
from fastapi import APIRouter, HTTPException
from launch import LaunchContext
from par_framework_core.launch_helpers import (BLACKFLY_NODE_PARAMETERS_KEY,
                                               BRIO_NODE_PARAMETERS_KEY,
                                               CAMERA_DRIVER_REMAPPINGS,
                                               CAPTURE_CAMERA_NODE_PARAMETERS_KEY,
                                               CU40_NODE_PARAMETERS_KEY,
                                               FILE_NAME_PART_PATTERN,
                                               FOLDER_PATH_CAMERA_INTRINSICS,
                                               FOLDER_PATH_EXTRINSICS,
                                               FOLDER_PATH_PROFILES, get_camera_info_file_name,
                                               get_extrinsics_folder_path,
                                               get_invalid_pose_keys,
                                               get_path_in_config_folder, PROJECTOR_APP_NONE,
                                               read_launch_section, read_par_app_entry,
                                               RENDERING_MANAGER_APP_NAME)
from pydantic import BaseModel
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
import yaml

PROFILE_FILE_EXTENSION = '.yaml'
# In the profiles folder, which is gitignored as a whole: the selection belongs to this machine.
# Hidden and without .yaml, so it is never listed as a profile.
LAST_SELECTED_PROFILE_FILE_NAME = '.setup_wizard_last_selected_profile'
# Deleted profiles are moved here (config/profiles/.deleted/<name>_<time>/), with their extrinsics
# in a subfolder; profile listings skip it, since it is a folder, not a .yaml file.
DELETED_PROFILES_FOLDER_NAME = '.deleted'
DELETED_EXTRINSICS_FOLDER_NAME = 'extrinsics'

# How the par_launch switches are sorted on a profile's card: every switch that is on counts as a
# sensor node, so a new detector shows up without a change here, except these. The capture camera
# is listed with the cameras instead; the app is par_launch.projector_app, no switch.
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

# The key under each node section of a ROS 2 parameter file
ROS_PARAMETERS_KEY = 'ros__parameters'
# Written above a node section the wizard adds to a profile; the leading empty line separates it
# from the section before, as in the hand-written profiles
ADDED_NODE_SECTION_COMMENT = '\nSaved by the setup wizard'
# In ruamel.yaml's comment record of a key, the position of what follows its value
RUAMEL_COMMENT_AFTER_VALUE_INDEX = 2
# Long lines (e.g. a page app's command) stay on one line instead of being wrapped on rewrite
PROFILE_YAML_LINE_WIDTH_CHARACTERS = 4096

# One rewrite of a profile file at a time; requests run in a thread pool.
_profile_write_lock = threading.Lock()

profiles_router = APIRouter()


class CameraCalibrationSummary(BaseModel):
    camera_display_name: str
    # The camera type for a preview (camera:= of par.launch.py); None when the camera cannot be
    # started on its own for a preview.
    preview_camera_name: str | None
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


class DeletedProfileResponse(BaseModel):
    # Where the profile file and its extrinsics were moved to, to restore them by hand
    deleted_profile_folder_path: str


class NewProfileRequest(BaseModel):
    # The file name without .yaml and the value of profile:=
    profile_name: str
    # As the user typed it, kept as a comment at the top of the file
    profile_display_name: str
    # Simplification: one camera, since the framework launches one at a time. Upgrade: a list of
    # camera instances, once launch_helpers starts several (card "Setup Wizard").
    camera_name: str
    # SDL/pygame display index of the projector; None when the profile has no projector yet
    projector_display_id: int | None


class NewProfileResponse(BaseModel):
    profile_name: str
    # The setting changes of the wizard written into the new profile, by node section
    written_setting_names_by_node_name: dict[str, list[str]]


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
    check_profile_exists(request.profile_name)
    with open(_get_last_selected_profile_path(), 'w') as last_selected_profile_file:
        last_selected_profile_file.write(request.profile_name)


@profiles_router.post('/api/profiles')
def create_profile(request: NewProfileRequest) -> NewProfileResponse:
    """Create config/profiles/<name>.yaml: camera, projector and the wizard's setting changes."""
    # The name becomes a file name and profile:=, so only what profile:= accepts
    if not FILE_NAME_PART_PATTERN.fullmatch(request.profile_name):
        raise HTTPException(status_code=422,
                            detail=f'{request.profile_name!r} is no valid profile name: use only '
                                   f'letters, digits, _ and -')
    if request.camera_name not in CAMERA_DRIVER_REMAPPINGS:
        # Without a camera the launch would silently take par_setup.yaml's camera
        raise HTTPException(status_code=422,
                            detail='Add a camera to the profile first (Hardware step)')
    if request.projector_display_id is not None and request.projector_display_id < 0:
        raise HTTPException(status_code=422, detail='The display number cannot be negative')

    profile_path = get_path_in_config_folder(
        f'{FOLDER_PATH_PROFILES}/{request.profile_name}{PROFILE_FILE_EXTENSION}')
    # One line, so a typed line break cannot end the comment and add YAML of its own
    one_line_display_name = ' '.join(request.profile_display_name.split())
    creation_date_text = datetime.date.today().isoformat()
    profile_lines = [
        f'# Setup profile {one_line_display_name}: only what differs from par_setup.yaml '
        f'(profile:={request.profile_name}).',
        f'# Created by the setup wizard on {creation_date_text}.',
        'par_launch:',
        f'  {ROS_PARAMETERS_KEY}:',
        f'    camera: {request.camera_name}',
    ]
    if request.projector_display_id is not None:
        profile_lines.append(f'    projector_display_id: {request.projector_display_id}')
    try:
        # 'x' creates the file only if it does not exist, so an existing profile is never
        # overwritten, even by two requests at once
        with open(profile_path, 'x') as profile_file:
            profile_file.write('\n'.join(profile_lines) + '\n')
    except FileExistsError:
        raise HTTPException(status_code=409,
                            detail=f'A profile named {request.profile_name!r} exists already')

    # Imported here: camera_preview_api imports this module, so a module-level import would be
    # circular
    import camera_preview_api
    written_setting_names_by_node_name = {}
    new_profile_setting_values = camera_preview_api.take_new_profile_setting_values(
        request.camera_name)
    for node_name, setting_value_by_name in new_profile_setting_values.items():
        write_result = write_node_settings_into_profile(request.profile_name, node_name,
                                                        setting_value_by_name)
        written_setting_names_by_node_name[write_result.node_section_name] = (
            write_result.written_setting_names)
    return NewProfileResponse(
        profile_name=request.profile_name,
        written_setting_names_by_node_name=written_setting_names_by_node_name)


@profiles_router.delete('/api/profiles/{profile_name}')
def delete_profile(profile_name: str) -> DeletedProfileResponse:
    """Move the profile and its extrinsics into config/profiles/.deleted/, to restore by hand."""
    # Only the name of a listed profile reaches a path, so no other file can be moved.
    check_profile_exists(profile_name)
    # Not deleted for good: the folders are gitignored, and measured camera poses and projector
    # calibrations take real work to redo.
    deletion_time_text = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    deleted_profile_folder_name = f'{profile_name}_{deletion_time_text}'
    deleted_profile_folder_path = get_path_in_config_folder(
        f'{FOLDER_PATH_PROFILES}/{DELETED_PROFILES_FOLDER_NAME}/{deleted_profile_folder_name}')
    os.makedirs(deleted_profile_folder_path)
    profile_path = get_path_in_config_folder(
        f'{FOLDER_PATH_PROFILES}/{profile_name}{PROFILE_FILE_EXTENSION}')
    # The profile file first: once it is moved, the profile is gone from every list and launch.
    shutil.move(profile_path, deleted_profile_folder_path)
    extrinsics_folder_path = get_path_in_config_folder(f'{FOLDER_PATH_EXTRINSICS}/{profile_name}')
    if os.path.isdir(extrinsics_folder_path):
        shutil.move(extrinsics_folder_path,
                    os.path.join(deleted_profile_folder_path, DELETED_EXTRINSICS_FOLDER_NAME))
    return DeletedProfileResponse(deleted_profile_folder_path=deleted_profile_folder_path)


def check_profile_exists(profile_name: str) -> None:
    """Raise 404 unless profile_name names a saved profile, e.g. before it reaches profile:=."""
    if profile_name not in _read_profile_names():
        raise HTTPException(status_code=404, detail=f'No profile named {profile_name!r}')


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
    """Return the cameras, sensor nodes and app the profile starts through par_launch."""
    profile_launch_context = _create_profile_launch_context(profile_name)
    try:
        launch_section = read_launch_section(profile_launch_context)
        main_camera_name = launch_section['camera']
        cameras = [CameraCalibrationSummary(
            camera_display_name=main_camera_name,
            preview_camera_name=main_camera_name,
            intrinsics_state=_read_main_camera_intrinsics_state(profile_launch_context,
                                                                main_camera_name),
            pose_state=_read_camera_pose_state(profile_launch_context, main_camera_name))]
        if launch_section.get('capture_camera') is True:
            # Simplification: the capture camera only starts together with the main camera
            # (capture_camera:=true), so it has no preview of its own. Upgrade: start cameras as
            # instances (card "Setup Wizard", "Multiple cameras").
            cameras.append(CameraCalibrationSummary(
                camera_display_name=CAPTURE_CAMERA_DISPLAY_NAME,
                preview_camera_name=None,
                intrinsics_state=_read_capture_camera_intrinsics_state(profile_launch_context),
                pose_state=POSE_STATE_UNSUPPORTED))
    except (RuntimeError, KeyError, OSError, yaml.YAMLError) as error:
        # A profile is written by hand: one broken file must not hide the other profiles.
        return ProfileSummary(profile_name=profile_name, cameras=[], sensor_node_names=[],
                              app_names=[], profile_error_text=str(error))

    app_names = []
    switched_on_names = []
    projector_app_name = str(launch_section.get('projector_app', PROJECTOR_APP_NONE))
    if projector_app_name != PROJECTOR_APP_NONE:
        app_names.append(projector_app_name)
    if projector_app_name not in (PROJECTOR_APP_NONE, RENDERING_MANAGER_APP_NAME):
        # par.launch.py switches on what the app requires, so the card lists those nodes too
        try:
            switched_on_names += read_par_app_entry(projector_app_name)['required_launch_switches']
        except RuntimeError:
            # Not installed or a broken entry: GET /api/apps reports it; the card shows the rest
            pass
    for switch_name, switch_value in launch_section.items():
        if switch_value is True:
            switched_on_names.append(switch_name)

    sensor_node_names = []
    for switch_name in switched_on_names:
        if switch_name in HIDDEN_LAUNCH_SWITCH_NAMES:
            continue
        if switch_name not in sensor_node_names:
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


class NodeSettingsWriteResult(BaseModel):
    # The node's section in the profile the settings were written to
    node_section_name: str
    # Written into the profile, because they differ from par_setup.yaml
    written_setting_names: list[str]
    # Removed from the profile (or never written), because par_setup.yaml has the same value
    removed_setting_names: list[str]


def write_node_settings_into_profile(profile_name: str, full_node_name: str,
                                     setting_value_by_name: dict) -> NodeSettingsWriteResult:
    """
    Write settings of a node into the profile, as ROS reads them at the node's next start.

    Only what differs from par_setup.yaml is kept, as in a hand-written profile: a value equal
    to par_setup.yaml's removes its key. The file is rewritten with ruamel.yaml's round trip,
    which keeps comments, quotes and layout of everything else.
    """
    check_profile_exists(profile_name)
    profile_path = get_path_in_config_folder(
        f'{FOLDER_PATH_PROFILES}/{profile_name}{PROFILE_FILE_EXTENSION}')
    default_setting_value_by_name = _read_par_setup_node_settings(full_node_name)
    round_trip_yaml = _create_round_trip_yaml()
    with _profile_write_lock:
        with open(profile_path) as profile_file:
            profile_document = round_trip_yaml.load(profile_file)
        if profile_document is None:
            profile_document = CommentedMap()
        if not isinstance(profile_document, CommentedMap):
            raise HTTPException(status_code=409,
                                detail=f'{profile_path} holds no node sections; fix it by hand '
                                       f'before saving settings into it')

        node_section_name = _find_node_section_name(profile_document, full_node_name)
        if node_section_name is None:
            # A namespaced node needs its full name; ROS silently ignores a bare one
            node_section_name = full_node_name
        node_section = profile_document.get(node_section_name)
        if not isinstance(node_section, dict):
            node_section = CommentedMap()
        node_parameters = node_section.get(ROS_PARAMETERS_KEY)
        if not isinstance(node_parameters, dict):
            node_parameters = CommentedMap()

        written_setting_names = []
        removed_setting_names = []
        for setting_name, setting_value in setting_value_by_name.items():
            # Simplification: settings are written flat (image_raw.jpeg_quality), so one written
            # nested in the profile by hand is not found and stays as well; ROS then takes the
            # later one. Upgrade: look up dotted names in nested sections too.
            is_par_setup_value = setting_name in default_setting_value_by_name and _is_same_value(
                default_setting_value_by_name[setting_name], setting_value)
            if is_par_setup_value:
                if setting_name in node_parameters:
                    _delete_key_keeping_empty_lines_after(node_parameters, setting_name)
                removed_setting_names.append(setting_name)
            else:
                node_parameters[setting_name] = setting_value
                written_setting_names.append(setting_name)

        if node_parameters:
            node_section[ROS_PARAMETERS_KEY] = node_parameters
            is_new_node_section = node_section_name not in profile_document
            profile_document[node_section_name] = node_section
            if is_new_node_section:
                profile_document.yaml_set_comment_before_after_key(
                    node_section_name, before=ADDED_NODE_SECTION_COMMENT)
        elif node_section_name in profile_document:
            # Nothing left that differs; a section with other keys besides the parameters stays
            if ROS_PARAMETERS_KEY in node_section:
                del node_section[ROS_PARAMETERS_KEY]
            if not node_section:
                del profile_document[node_section_name]
        _replace_file_contents(profile_path, round_trip_yaml, profile_document)

    return NodeSettingsWriteResult(node_section_name=node_section_name,
                                   written_setting_names=written_setting_names,
                                   removed_setting_names=removed_setting_names)


def _delete_key_keeping_empty_lines_after(yaml_mapping: CommentedMap, key: str) -> None:
    """Delete key; empty lines ruamel.yaml stores after the last key move to the new last key."""
    # Without this, deleting a section's last setting also deletes the empty line that separates
    # the section from the next one
    keys = list(yaml_mapping.keys())
    comment_record = yaml_mapping.ca.items.get(key)
    del yaml_mapping[key]
    is_last_key = keys[-1] == key
    if comment_record is None or not is_last_key or len(keys) < 2:
        return
    comment_after_value = comment_record[RUAMEL_COMMENT_AFTER_VALUE_INDEX]
    # Only empty lines move; a comment written after the deleted value belonged to it
    if comment_after_value is None or comment_after_value.value.strip() != '':
        return
    new_last_key = keys[-2]
    if new_last_key in yaml_mapping.ca.items:
        return
    yaml_mapping.ca.items[new_last_key] = [None, None, comment_after_value, None]


def _create_round_trip_yaml() -> YAML:
    """Return a ruamel.yaml reader and writer that keeps a profile as it was written by hand."""
    round_trip_yaml = YAML()
    round_trip_yaml.preserve_quotes = True
    round_trip_yaml.width = PROFILE_YAML_LINE_WIDTH_CHARACTERS
    round_trip_yaml.indent(mapping=2, sequence=4, offset=2)
    return round_trip_yaml


def _find_node_section_name(parameter_document: dict, full_node_name: str) -> str | None:
    """Return the section of the node as the file spells it (with or without leading /)."""
    for section_name in parameter_document:
        if not isinstance(section_name, str):
            continue
        if '/' + section_name.lstrip('/') == full_node_name:
            return section_name
    return None


def _read_par_setup_node_settings(full_node_name: str) -> dict:
    """Return the node's parameters in par_setup.yaml, the defaults a profile overrides."""
    par_setup_path = os.path.join(get_package_share_directory('par_framework_core'), 'config',
                                  'par_setup.yaml')
    with open(par_setup_path) as par_setup_file:
        par_setup_document = yaml.safe_load(par_setup_file) or {}
    node_section_name = _find_node_section_name(par_setup_document, full_node_name)
    if node_section_name is None:
        return {}
    node_section = par_setup_document[node_section_name] or {}
    return node_section.get(ROS_PARAMETERS_KEY) or {}


def _is_same_value(par_setup_value, setting_value) -> bool:
    """Compare like ROS: 5 and 5.0 are different parameter types, so not the same value."""
    if type(par_setup_value) is not type(setting_value):
        return False
    return par_setup_value == setting_value


def _replace_file_contents(file_path: str, round_trip_yaml: YAML, yaml_document) -> None:
    """Write the document to a hidden file next to file_path, then put it in place in one step."""
    # A crash or a full disk while writing leaves the old profile intact instead of half a file
    folder_path = os.path.dirname(file_path)
    with tempfile.NamedTemporaryFile('w', dir=folder_path, prefix='.', suffix='.saving',
                                     delete=False) as temporary_file:
        round_trip_yaml.dump(yaml_document, temporary_file)
        temporary_file_path = temporary_file.name
    shutil.copymode(file_path, temporary_file_path)
    os.replace(temporary_file_path, file_path)
