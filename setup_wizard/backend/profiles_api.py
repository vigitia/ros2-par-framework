# Written by Claude Code
"""
Profiles API of the setup wizard backend: the hardware setups (config/profiles/<name>.yaml).

Lists them with their cameras, sensor nodes and apps and each camera's calibration state,
remembers the one selected last time, and writes node settings changed in the wizard, the cameras
(par_launch.cameras: name -> '<type>[:<serial>]') and the app on the projector into them.
"""

import datetime
import os
import shutil
import tempfile
import threading

from ament_index_python.packages import get_package_share_directory
from fastapi import APIRouter, HTTPException
from launch import LaunchContext
from par_framework_core.connected_displays import (
    ConnectedDisplay, find_projector_display_ids, get_display_mode_text, get_display_title_text,
    get_projector_display_mode, get_projector_identity, get_projector_identity_title_text,
    PROJECTOR_DISPLAY_MODE_PARAMETER_NAME_BY_ATTRIBUTE, read_connected_displays)
from par_framework_core.launch_helpers import (CAMERA_ENTRY_INTRINSICS_KEY,
                                               CAMERA_ENTRY_SERIAL_KEY, CAMERA_NAME_PATTERN,
                                               CAMERA_SERIAL_SOURCE_NONE, CAMERAS_NAMESPACE,
                                               FILE_NAME_PART_PATTERN,
                                               FOLDER_PATH_CAMERA_INTRINSICS,
                                               FOLDER_PATH_EXTRINSICS,
                                               FOLDER_PATH_PROFILES,
                                               get_camera_info_file_name_of_unit,
                                               get_extrinsics_relative_path,
                                               get_intrinsics_folder_path,
                                               get_invalid_pose_keys,
                                               get_path_in_config_folder,
                                               get_sensor_node_package_names,
                                               PAR_LAUNCH_CAMERAS_KEY, ProfileCamera,
                                               PROJECTOR_APP_NONE, read_camera_entry,
                                               read_launch_section, read_par_app_entry,
                                               read_profile_cameras, read_projector_identity,
                                               read_stored_projector_display_id,
                                               RENDERING_MANAGER_APP_NAME)
from pydantic import BaseModel
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import CommentMark
from ruamel.yaml.tokens import CommentToken
import yaml

PROFILE_FILE_EXTENSION = '.yaml'
# In the profiles folder, which is gitignored as a whole: the selection belongs to this machine.
# Hidden and without .yaml, so it is never listed as a profile.
LAST_SELECTED_PROFILE_FILE_NAME = '.setup_wizard_last_selected_profile'
# Deleted profiles are moved here (config/profiles/.deleted/<name>_<time>/), with their intrinsics
# and extrinsics in subfolders; profile listings skip it, since it is a folder, not a .yaml file.
DELETED_PROFILES_FOLDER_NAME = '.deleted'
DELETED_INTRINSICS_FOLDER_NAME = 'intrinsics'
DELETED_EXTRINSICS_FOLDER_NAME = 'extrinsics'

# par.launch.py's switch for RViz with rviz_bridge. The Apps area lists RViz as an app under this
# name (apps_api.py), stored as this switch instead of in par_launch.apps.
RVIZ_LAUNCH_SWITCH_NAME = 'rviz'

# Calibration states as the app receives them.
INTRINSICS_STATE_CALIBRATED = 'calibrated'
INTRINSICS_STATE_FACTORY = 'factory'
INTRINSICS_STATE_MISSING = 'missing'
# The camera publishes no camera_info (intrinsics: none in its entry), so it cannot be calibrated.
INTRINSICS_STATE_UNSUPPORTED = 'unsupported'
# Whether the profile's projector is where par_launch.projector_display_id says, as the app
# receives it. Launches look the projector up by its stored identity
# (launch_helpers.get_projector_display_id), so a moved projector still works there.
PROJECTOR_DISPLAY_STATE_NOT_SET = 'not_set'
# A display id without a stored identity (written by hand): nothing to check it against
PROJECTOR_DISPLAY_STATE_UNIDENTIFIED = 'unidentified'
PROJECTOR_DISPLAY_STATE_CONNECTED = 'connected'
# The projector is connected, but under another display id than the stored one
PROJECTOR_DISPLAY_STATE_MOVED = 'moved'
PROJECTOR_DISPLAY_STATE_NOT_CONNECTED = 'not_connected'
# Several displays match the stored identity (identical projectors without a serial)
PROJECTOR_DISPLAY_STATE_AMBIGUOUS = 'ambiguous'
PROJECTOR_DISPLAY_STATE_DISPLAYS_UNREADABLE = 'displays_unreadable'
POSE_STATE_MEASURED = 'measured'
POSE_STATE_PLACEHOLDER = 'placeholder'
# The measured pose file exists but lacks keys or numbers; a launch would stop on it.
POSE_STATE_INVALID = 'invalid'

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
    # The camera's name in par_launch.cameras, as in camera:= and /cameras/<name>
    camera_name: str
    # Its type (a camera entry's name) and its unit's serial, '' when the profile names none
    camera_type: str
    serial: str = ''
    # The first camera of par_launch.cameras: the framework nodes use it
    is_main_camera: bool = False
    # One of the INTRINSICS_STATE_* values.
    intrinsics_state: str
    # One of the POSE_STATE_* values.
    pose_state: str


class ProfileSummary(BaseModel):
    profile_name: str
    cameras: list[CameraCalibrationSummary]
    sensor_node_names: list[str]
    app_names: list[str]
    # The apps the profile offers (par_launch.apps), in its order; the projector app is one of them
    enabled_app_names: list[str] = []
    # The display to use for the projector now: found by its stored identity, else the stored
    # id; None when the profile sets none or the projector is not found
    projector_display_id: int | None = None
    # par_launch.projector_display_id as written in the profile
    stored_projector_display_id: int | None = None
    # One of the PROJECTOR_DISPLAY_STATE_* values
    projector_display_state: str = PROJECTOR_DISPLAY_STATE_NOT_SET
    # The stored projector's name, e.g. 'EPS EB-680'; '' without a stored identity
    projector_title_text: str = ''
    # The display at the stored id now, e.g. 'eDP-1 15"'; '' when none is or it cannot be read
    stored_display_title_text: str = ''
    # The display mode the projector was chosen with, e.g. '3840 × 2160 at 60 Hz'; '' when the
    # profile stores none
    stored_display_mode_text: str = ''
    # The projector's display mode now; '' while it is not found
    current_display_mode_text: str = ''
    # True when both are known and differ: the projector calibration may no longer fit
    is_display_mode_changed: bool = False
    # Set when the profile's files cannot be read; the lists are empty then.
    profile_error_text: str | None = None


class ProfileListResponse(BaseModel):
    profiles: list[ProfileSummary]
    # None when nothing was selected yet, or the profile selected last time no longer exists.
    last_selected_profile_name: str | None


class LastSelectedProfileRequest(BaseModel):
    profile_name: str


class DeletedProfileResponse(BaseModel):
    # Where the profile file and its extrinsics were moved to, to restore them by hand; '' when a
    # removed camera had no files to move
    deleted_profile_folder_path: str


class NewProfileRequest(BaseModel):
    # The file name without .yaml and the value of profile:=
    profile_name: str
    # As the user typed it, kept as a comment at the top of the file
    profile_display_name: str
    # The profile's first camera, set up in the Hardware step; more are added in the Cameras area.
    # Its name in par_launch.cameras (a camera name: lower case letters, digits and _)
    camera_name: str
    # A camera type from GET /api/cameras
    camera_type: str
    # The camera unit chosen in the Hardware step; '' for a camera type without serials
    camera_serial: str = ''
    # SDL/pygame display index of the projector; None when the profile has no projector yet
    projector_display_id: int | None


class NewCameraRequest(BaseModel):
    # Its name in par_launch.cameras (lower case letters, digits and _), e.g. overhead
    camera_name: str
    # A camera type from GET /api/cameras
    camera_type: str
    # The unit's serial; '' for a camera type that has none
    serial: str = ''


class ProjectorDisplayChoiceRequest(BaseModel):
    # A display_id from GET /api/displays
    display_id: int


class ProjectorAppChoiceRequest(BaseModel):
    # par_launch.projector_app: none, or one of the profile's apps (par_launch.apps)
    app_name: str


class EnabledAppsRequest(BaseModel):
    # par_launch.apps: app_names of installed apps from GET /api/apps
    app_names: list[str]


class NewProfileResponse(BaseModel):
    profile_name: str
    # The setting changes of the wizard written into the new profile, by node section
    written_setting_names_by_node_name: dict[str, list[str]]


@profiles_router.get('/api/profiles')
def get_profile_list() -> ProfileListResponse:
    """List the profiles (config/profiles/<name>.yaml) with what they run, and the last choice."""
    profile_names = _read_profile_names()
    # Read once for all profiles: SDL opens the displays per call
    displays_error_text = None
    try:
        connected_displays = read_connected_displays()
    except RuntimeError as error:
        connected_displays = []
        displays_error_text = str(error)
    profile_summaries = []
    for profile_name in profile_names:
        profile_summaries.append(_read_profile_summary(profile_name, connected_displays,
                                                       displays_error_text))
    last_selected_profile_name = _read_last_selected_profile_name()
    if last_selected_profile_name not in profile_names:
        last_selected_profile_name = None
    return ProfileListResponse(profiles=profile_summaries,
                               last_selected_profile_name=last_selected_profile_name)


@profiles_router.put('/api/profiles/last-selected')
def set_last_selected_profile(request: LastSelectedProfileRequest) -> None:
    """Remember the selected profile, so the wizard opens it next time."""
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
    if not request.camera_type:
        # Without a camera the launch would silently take par_setup.yaml's camera
        raise HTTPException(status_code=422,
                            detail='Add a camera to the profile first (Hardware step)')
    new_camera = _check_new_camera([], request.camera_name, request.camera_type,
                                   request.camera_serial)
    # Checked before the file exists, so a display that went away leaves no half-made profile
    projector_display = None
    if request.projector_display_id is not None:
        projector_display = _find_connected_display(request.projector_display_id)

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
        f'    {PAR_LAUNCH_CAMERAS_KEY}:',
        f"      {new_camera.camera_name}: '{_create_camera_unit_text(new_camera)}'",
    ]
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
    # The preview ran without a profile, so its camera was named after its type
    new_profile_setting_values = camera_preview_api.take_new_profile_setting_values(
        new_camera.camera_type)
    preview_namespace = f'{CAMERAS_NAMESPACE}/{new_camera.camera_type}/'
    camera_namespace = f'{CAMERAS_NAMESPACE}/{new_camera.camera_name}/'
    write_results = []
    for node_name, setting_value_by_name in new_profile_setting_values.items():
        # Saved for this camera alone, under its name
        if node_name.startswith(preview_namespace):
            node_name = camera_namespace + node_name.removeprefix(preview_namespace)
        write_results.append(write_node_settings_into_profile(request.profile_name, node_name,
                                                              setting_value_by_name))
    if projector_display is not None:
        _write_projector_display_into_profile(request.profile_name, projector_display)
    for write_result in write_results:
        node_setting_names = written_setting_names_by_node_name.setdefault(
            write_result.node_section_name, [])
        node_setting_names += write_result.written_setting_names
    return NewProfileResponse(
        profile_name=request.profile_name,
        written_setting_names_by_node_name=written_setting_names_by_node_name)


@profiles_router.put('/api/profiles/{profile_name}/projector-app')
def set_projector_app(profile_name: str, request: ProjectorAppChoiceRequest) -> None:
    """Store which of the profile's apps it puts on the projector (par_launch.projector_app)."""
    launch_section = read_profile_launch_section(profile_name)
    if request.app_name == RVIZ_LAUNCH_SWITCH_NAME:
        raise HTTPException(status_code=422,
                            detail='RViz does not draw on the projector; it runs next to the '
                                   'app on the projector')
    if request.app_name != PROJECTOR_APP_NONE:
        if request.app_name not in _read_enabled_app_names(launch_section):
            raise HTTPException(status_code=422,
                                detail=f'{request.app_name} is not one of the profile\'s apps; '
                                       f'add it under Apps first')
        _check_startable_app(request.app_name)
    # As the sensor node switches: none is par_setup.yaml's value, so choosing it removes the key
    write_node_settings_into_profile(profile_name, '/par_launch',
                                     {'projector_app': request.app_name})


# Written by Claude Code
@profiles_router.put('/api/profiles/{profile_name}/apps')
def set_enabled_apps(profile_name: str, request: EnabledAppsRequest) -> None:
    """
    Store which installed apps the profile offers (par_launch.apps), keeping their order.

    RViz is stored as the switch par_launch.rviz instead, which par.launch.py starts it by.
    """
    launch_section = read_profile_launch_section(profile_name)
    enabled_app_names = []
    is_rviz_enabled = False
    for app_name in request.app_names:
        if app_name in enabled_app_names:
            continue
        _check_startable_app(app_name)
        if app_name == RVIZ_LAUNCH_SWITCH_NAME:
            is_rviz_enabled = True
            continue
        enabled_app_names.append(app_name)
    setting_value_by_name = {'apps': enabled_app_names, RVIZ_LAUNCH_SWITCH_NAME: is_rviz_enabled}
    # The projector app is always one of the profile's apps
    if str(launch_section.get('projector_app', PROJECTOR_APP_NONE)) not in enabled_app_names:
        setting_value_by_name['projector_app'] = PROJECTOR_APP_NONE
    write_node_settings_into_profile(profile_name, '/par_launch', setting_value_by_name)


# Written by Claude Code
def _check_startable_app(app_name: str) -> None:
    """Raise 422 for no installed app, 409 for one whose entry par.launch.py would refuse."""
    # Imported here like camera_preview_api, so this module's imports stay free of the API modules
    import apps_api
    for installed_app in apps_api.get_installed_app_list().installed_apps:
        if installed_app.app_name != app_name:
            continue
        if installed_app.entry_error_text is not None:
            raise HTTPException(status_code=409, detail=installed_app.entry_error_text)
        return
    raise HTTPException(status_code=422,
                        detail=f'{app_name!r} is no installed app; choose one from GET /api/apps')


# Written by Claude Code
def _read_enabled_app_names(launch_section: dict) -> list[str]:
    """Return par_launch.apps as names, then RViz when par_launch.rviz is on; [] without any."""
    listed_app_names = launch_section.get('apps') or []
    if not isinstance(listed_app_names, list):
        raise RuntimeError(f'par_launch.apps must be a list of app names, not '
                           f'{listed_app_names!r}')
    enabled_app_names = [str(app_name) for app_name in listed_app_names]
    if launch_section.get(RVIZ_LAUNCH_SWITCH_NAME) is True:
        enabled_app_names.append(RVIZ_LAUNCH_SWITCH_NAME)
    return enabled_app_names


# Written by Claude Code
@profiles_router.put('/api/profiles/{profile_name}/projector-display')
def set_projector_display(profile_name: str, request: ProjectorDisplayChoiceRequest) -> None:
    """Store which connected display is the profile's projector: its id and its identity."""
    check_profile_exists(profile_name)
    _write_projector_display_into_profile(profile_name,
                                          _find_connected_display(request.display_id))


@profiles_router.post('/api/profiles/{profile_name}/cameras')
def add_camera(profile_name: str, request: NewCameraRequest) -> None:
    """Add a named camera to the profile's par_launch.cameras; every run starts it."""
    check_profile_exists(profile_name)
    profile_cameras = read_profile_cameras(create_profile_launch_context(profile_name))
    new_camera = _check_new_camera(profile_cameras, request.camera_name, request.camera_type,
                                   request.serial)
    _write_profile_cameras(profile_name, [*profile_cameras, new_camera])


# Written by Claude Code
@profiles_router.delete('/api/profiles/{profile_name}/cameras/{camera_name}')
def remove_camera(profile_name: str, camera_name: str) -> DeletedProfileResponse:
    """Remove a camera from the profile; its calibrations move to config/profiles/.deleted/."""
    check_profile_exists(profile_name)
    profile_launch_context = create_profile_launch_context(profile_name)
    profile_cameras = read_profile_cameras(profile_launch_context)
    removed_camera = find_profile_camera(profile_cameras, camera_name)
    if len(profile_cameras) == 1:
        raise HTTPException(status_code=409,
                            detail='A profile needs at least one camera: add another one first')
    intrinsics_folder_path = get_intrinsics_folder_path(profile_launch_context)
    intrinsics_file_name = get_camera_info_file_name_of_unit(removed_camera.camera_type,
                                                             removed_camera.serial)
    file_relative_paths = [f'{intrinsics_folder_path}/{intrinsics_file_name}']
    for file_prefix in ('camera_pose', 'projection_mapping', 'projection_corners'):
        file_relative_paths.append(
            get_extrinsics_relative_path(profile_launch_context, file_prefix, camera_name))
    existing_file_paths = []
    for file_relative_path in file_relative_paths:
        file_path = get_path_in_config_folder(file_relative_path)
        if os.path.exists(file_path):
            existing_file_paths.append(file_path)
    # A camera never calibrated leaves nothing to keep, so no empty folder is created for it
    deleted_folder_path = ''
    if existing_file_paths:
        deleted_folder_path = _create_deleted_folder(f'{profile_name}_{camera_name}')
    for existing_file_path in existing_file_paths:
        shutil.move(existing_file_path, deleted_folder_path)
    remaining_cameras = [camera for camera in profile_cameras if camera.camera_name != camera_name]
    _write_profile_cameras(profile_name, remaining_cameras)
    return DeletedProfileResponse(deleted_profile_folder_path=deleted_folder_path)


# Written by Claude Code
def _check_new_camera(profile_cameras: list[ProfileCamera], camera_name: str, camera_type: str,
                      serial: str) -> ProfileCamera:
    """
    Return the camera to add to a profile with profile_cameras, checked; HTTP 4xx when it cannot.

    The name must be new; a type without serials (serial: none in its entry) once per profile,
    and a type with serials only once without one, since units that cannot be told apart would
    share their files.
    """
    if not CAMERA_NAME_PATTERN.fullmatch(camera_name):
        raise HTTPException(status_code=422,
                            detail=f'{camera_name!r} is no camera name: use lower case letters, '
                                   f'digits and _, starting with a letter, e.g. overhead')
    for profile_camera in profile_cameras:
        if profile_camera.camera_name == camera_name:
            raise HTTPException(status_code=409,
                                detail=f'The profile has a camera named {camera_name!r} '
                                       f'already; choose another name')
    # Imported here like camera_preview_api, so this module's imports stay free of the API modules
    import cameras_api
    camera_entry = cameras_api.read_installed_camera_entry(camera_type)
    # It becomes part of the calibration file names
    if serial and not FILE_NAME_PART_PATTERN.fullmatch(serial):
        raise HTTPException(status_code=422,
                            detail='A serial number has only letters, digits, _ and -')
    has_serials = camera_entry[CAMERA_ENTRY_SERIAL_KEY] != CAMERA_SERIAL_SOURCE_NONE
    if serial and not has_serials:
        raise HTTPException(status_code=422,
                            detail=f'Cameras of type {camera_type} have no serial numbers')
    cameras_of_type = [camera for camera in profile_cameras if camera.camera_type == camera_type]
    if not cameras_of_type:
        return ProfileCamera(camera_name, camera_type, serial)
    if not has_serials:
        raise HTTPException(status_code=409,
                            detail=f'The profile has a {camera_type} camera already, and two of '
                                   f'this type cannot be told apart')
    for camera_of_type in cameras_of_type:
        if not camera_of_type.serial:
            raise HTTPException(status_code=409,
                                detail=f"The profile's {camera_type} camera "
                                       f'{camera_of_type.camera_name} is not tied to one unit, so '
                                       f'a second one cannot be told apart')
        if camera_of_type.serial == serial:
            raise HTTPException(status_code=409,
                                detail=f'This {camera_type} is in the profile already, as '
                                       f'{camera_of_type.camera_name}')
    if not serial:
        raise HTTPException(status_code=422,
                            detail=f'The profile has a {camera_type} camera already: choose '
                                   f'which unit to add')
    return ProfileCamera(camera_name, camera_type, serial)


# Written by Claude Code
def find_profile_camera(profile_cameras: list[ProfileCamera], camera_name: str) -> ProfileCamera:
    """Return the profile's camera of this name; HTTP 404 when it has none."""
    for profile_camera in profile_cameras:
        if profile_camera.camera_name == camera_name:
            return profile_camera
    raise HTTPException(status_code=404, detail=f'The profile has no camera {camera_name!r}')


# Written by Claude Code
def _write_profile_cameras(profile_name: str, profile_cameras: list[ProfileCamera]) -> None:
    """Write par_launch.cameras, keeping the cameras' order: the first is the main camera."""
    camera_unit_text_by_name = {}
    for profile_camera in profile_cameras:
        camera_unit_text_by_name[profile_camera.camera_name] = _create_camera_unit_text(
            profile_camera)
    # Pinned even when it equals par_setup.yaml's: the profile names its own cameras
    write_node_settings_into_profile(profile_name, '/par_launch',
                                     {PAR_LAUNCH_CAMERAS_KEY: camera_unit_text_by_name},
                                     always_written_setting_names=(PAR_LAUNCH_CAMERAS_KEY,))


@profiles_router.delete('/api/profiles/{profile_name}')
def delete_profile(profile_name: str) -> DeletedProfileResponse:
    """Move the profile and its calibrations into config/profiles/.deleted/, to restore by hand."""
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
    # Moved along, so a new profile of the same name does not take over this one's calibrations
    intrinsics_folder_path = get_path_in_config_folder(
        f'{FOLDER_PATH_CAMERA_INTRINSICS}/{profile_name}')
    if os.path.isdir(intrinsics_folder_path):
        shutil.move(intrinsics_folder_path,
                    os.path.join(deleted_profile_folder_path, DELETED_INTRINSICS_FOLDER_NAME))
    extrinsics_folder_path = get_path_in_config_folder(f'{FOLDER_PATH_EXTRINSICS}/{profile_name}')
    if os.path.isdir(extrinsics_folder_path):
        shutil.move(extrinsics_folder_path,
                    os.path.join(deleted_profile_folder_path, DELETED_EXTRINSICS_FOLDER_NAME))
    return DeletedProfileResponse(deleted_profile_folder_path=deleted_profile_folder_path)


def check_profile_exists(profile_name: str) -> None:
    """Raise 404 unless profile_name names a saved profile, e.g. before it reaches profile:=."""
    if profile_name not in _read_profile_names():
        raise HTTPException(status_code=404, detail=f'No profile named {profile_name!r}')


def read_profile_launch_section(profile_name: str) -> dict:
    """Return the profile's par_launch section as a launch reads it; 404 or 409 when it cannot."""
    check_profile_exists(profile_name)
    profile_launch_context = create_profile_launch_context(profile_name)
    try:
        return read_launch_section(profile_launch_context)
    except (RuntimeError, KeyError, OSError) as error:
        raise HTTPException(status_code=409,
                            detail=f'Cannot read the profile {profile_name}: {error}') from error


def read_profile_node_settings(profile_name: str, full_node_name: str) -> dict:
    """Return the node's parameters as the profile sets them; {} when it sets none."""
    check_profile_exists(profile_name)
    profile_path = get_path_in_config_folder(
        f'{FOLDER_PATH_PROFILES}/{profile_name}{PROFILE_FILE_EXTENSION}')
    with open(profile_path) as profile_file:
        profile_document = yaml.safe_load(profile_file) or {}
    if not isinstance(profile_document, dict):
        raise HTTPException(status_code=409, detail=f'{profile_path} holds no node sections')
    node_section_name = _find_node_section_name(profile_document, full_node_name)
    if node_section_name is None:
        return {}
    node_section = profile_document[node_section_name] or {}
    return node_section.get(ROS_PARAMETERS_KEY) or {}


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


# Co-authored by Claude Code: the projector is checked against the connected displays
def _read_profile_summary(profile_name: str, connected_displays: list[ConnectedDisplay],
                          displays_error_text: str | None) -> ProfileSummary:
    """
    Return the cameras, sensor nodes and app the profile starts through par_launch.

    connected_displays is empty and displays_error_text says why when they cannot be read.
    """
    profile_launch_context = create_profile_launch_context(profile_name)
    try:
        launch_section = read_launch_section(profile_launch_context)
        enabled_app_names = _read_enabled_app_names(launch_section)
        projector_display_summary = _create_projector_display_summary(
            launch_section, connected_displays, displays_error_text)
        cameras = []
        profile_cameras = read_profile_cameras(profile_launch_context)
        for camera_index, profile_camera in enumerate(profile_cameras):
            cameras.append(_create_camera_summary(profile_launch_context, profile_camera,
                                                  camera_index == 0))
    except (RuntimeError, KeyError, OSError, yaml.YAMLError) as error:
        # A profile is written by hand: one broken file must not hide the other profiles.
        return ProfileSummary(profile_name=profile_name, cameras=[], sensor_node_names=[],
                              app_names=[], profile_error_text=str(error))

    app_names = []
    switched_on_launch_switch_names = []
    projector_app_name = str(launch_section.get('projector_app', PROJECTOR_APP_NONE))
    if projector_app_name != PROJECTOR_APP_NONE:
        app_names.append(projector_app_name)
    if projector_app_name not in (PROJECTOR_APP_NONE, RENDERING_MANAGER_APP_NAME):
        # par.launch.py switches on what the app requires, so the card lists those nodes too
        try:
            projector_app_entry = read_par_app_entry(projector_app_name)
            switched_on_launch_switch_names += projector_app_entry['required_launch_switches']
        except RuntimeError:
            # Not installed or a broken entry: GET /api/apps reports it; the card shows the rest
            pass
    for switch_name, switch_value in launch_section.items():
        if switch_value is True:
            switched_on_launch_switch_names.append(switch_name)

    # The same nodes as the Sensor nodes area: those registered in the ament index
    installed_sensor_node_names = get_sensor_node_package_names()
    sensor_node_names = []
    for switch_name in switched_on_launch_switch_names:
        if switch_name not in installed_sensor_node_names:
            continue
        if switch_name not in sensor_node_names:
            sensor_node_names.append(switch_name)
    return ProfileSummary(profile_name=profile_name, cameras=cameras,
                          sensor_node_names=sensor_node_names, app_names=app_names,
                          enabled_app_names=enabled_app_names,
                          **projector_display_summary)


# Written by Claude Code
def _create_projector_display_summary(launch_section: dict,
                                      connected_displays: list[ConnectedDisplay],
                                      displays_error_text: str | None) -> dict:
    """Return the ProfileSummary fields about the projector, checked like a launch finds it."""
    stored_projector_display_id = read_stored_projector_display_id(launch_section)
    projector_identity = read_projector_identity(launch_section)
    stored_display_title_text = ''
    for connected_display in connected_displays:
        if connected_display.display_id == stored_projector_display_id:
            stored_display_title_text = get_display_title_text(connected_display)
    projector_display_summary = {
        'projector_display_id': stored_projector_display_id,
        'stored_projector_display_id': stored_projector_display_id,
        'projector_title_text': get_projector_identity_title_text(projector_identity),
        'stored_display_title_text': stored_display_title_text,
    }

    if not projector_identity:
        if stored_projector_display_id is None:
            projector_display_summary['projector_display_state'] = PROJECTOR_DISPLAY_STATE_NOT_SET
        else:
            projector_display_summary['projector_display_state'] = (
                PROJECTOR_DISPLAY_STATE_UNIDENTIFIED)
        return projector_display_summary
    if displays_error_text is not None:
        print(f'[profiles_api]: cannot check the projector: {displays_error_text}')
        projector_display_summary['projector_display_state'] = (
            PROJECTOR_DISPLAY_STATE_DISPLAYS_UNREADABLE)
        return projector_display_summary

    matching_display_ids = find_projector_display_ids(connected_displays, projector_identity)
    if len(matching_display_ids) != 1:
        # Nothing to project on: steps that black out or calibrate the projector need the right one
        projector_display_summary['projector_display_id'] = None
        if matching_display_ids:
            projector_display_summary['projector_display_state'] = (
                PROJECTOR_DISPLAY_STATE_AMBIGUOUS)
        else:
            projector_display_summary['projector_display_state'] = (
                PROJECTOR_DISPLAY_STATE_NOT_CONNECTED)
        return projector_display_summary

    found_projector_display_id = matching_display_ids[0]
    projector_display_summary['projector_display_id'] = found_projector_display_id
    for connected_display in connected_displays:
        if connected_display.display_id == found_projector_display_id:
            projector_display_summary.update(
                _compare_projector_display_mode(launch_section, connected_display))
    is_at_stored_id = stored_projector_display_id in (None, found_projector_display_id)
    if is_at_stored_id:
        projector_display_summary['projector_display_state'] = PROJECTOR_DISPLAY_STATE_CONNECTED
    else:
        projector_display_summary['projector_display_state'] = PROJECTOR_DISPLAY_STATE_MOVED
    return projector_display_summary


# Written by Claude Code
def _compare_projector_display_mode(launch_section: dict,
                                    connected_display: ConnectedDisplay) -> dict:
    """Return the ProfileSummary fields comparing the stored display mode with the current one."""
    current_display_mode = get_projector_display_mode(connected_display)
    stored_display_mode = {}
    for parameter_name in PROJECTOR_DISPLAY_MODE_PARAMETER_NAME_BY_ATTRIBUTE.values():
        stored_display_mode[parameter_name] = launch_section.get(parameter_name)
    display_mode_comparison = {'current_display_mode_text': get_display_mode_text(
        connected_display.width_px, connected_display.height_px,
        connected_display.refresh_rate_hz)}
    stored_width_px = stored_display_mode['projector_width_px']
    stored_height_px = stored_display_mode['projector_height_px']
    if stored_width_px is None or stored_height_px is None:
        return display_mode_comparison
    display_mode_comparison['stored_display_mode_text'] = get_display_mode_text(
        stored_width_px, stored_height_px, stored_display_mode['projector_refresh_rate_hz'])
    is_display_mode_changed = False
    for parameter_name, stored_value in stored_display_mode.items():
        # A refresh rate the display did not report when it was chosen cannot be compared
        if stored_value is None:
            continue
        if stored_value != current_display_mode[parameter_name]:
            is_display_mode_changed = True
    display_mode_comparison['is_display_mode_changed'] = is_display_mode_changed
    return display_mode_comparison


def _create_camera_summary(profile_launch_context: LaunchContext, profile_camera: ProfileCamera,
                           is_main_camera: bool) -> CameraCalibrationSummary:
    """Return the calibration state of a profile's camera."""
    return CameraCalibrationSummary(
        camera_name=profile_camera.camera_name,
        camera_type=profile_camera.camera_type,
        serial=profile_camera.serial,
        is_main_camera=is_main_camera,
        intrinsics_state=_read_camera_intrinsics_state(profile_launch_context, profile_camera),
        pose_state=_read_camera_pose_state(profile_launch_context, profile_camera.camera_name))


def _create_camera_unit_text(profile_camera: ProfileCamera) -> str:
    """Return the camera's value in par_launch.cameras: '<type>' or '<type>:<serial>'."""
    if profile_camera.serial:
        return f'{profile_camera.camera_type}:{profile_camera.serial}'
    return profile_camera.camera_type


def _create_deleted_folder(folder_name_stem: str) -> str:
    """Create and return a new folder in config/profiles/.deleted/ for files moved out of use."""
    deletion_time_text = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    deleted_folder_path = get_path_in_config_folder(
        f'{FOLDER_PATH_PROFILES}/{DELETED_PROFILES_FOLDER_NAME}/'
        f'{folder_name_stem}_{deletion_time_text}')
    os.makedirs(deleted_folder_path)
    return deleted_folder_path


def _read_camera_intrinsics_state(profile_launch_context: LaunchContext,
                                  profile_camera: ProfileCamera) -> str:
    """Return whether the camera's unit has its lens calibration (INTRINSICS_STATE_*)."""
    intrinsics_source = read_camera_entry(profile_camera.camera_type)[CAMERA_ENTRY_INTRINSICS_KEY]
    if intrinsics_source == 'factory':
        return INTRINSICS_STATE_FACTORY
    if intrinsics_source == 'none':
        return INTRINSICS_STATE_UNSUPPORTED
    intrinsics_file_name = get_camera_info_file_name_of_unit(profile_camera.camera_type,
                                                             profile_camera.serial)
    return _get_intrinsics_file_state(profile_launch_context, intrinsics_file_name)


# Written by Claude Code
def get_camera_intrinsics_file_path(profile_name: str, camera_name: str) -> str | None:
    """
    Return the path of the intrinsics file the framework gives the profile's camera at launch.

    The same file launch_helpers.get_camera_info_url names, whatever the driver calls its
    parameter for it. None when the framework gives the camera none: its type is not
    calibratable (intrinsics: factory or none in its entry).
    """
    profile_launch_context = create_profile_launch_context(profile_name)
    profile_camera = find_profile_camera(read_profile_cameras(profile_launch_context),
                                         camera_name)
    intrinsics_source = read_camera_entry(profile_camera.camera_type)[CAMERA_ENTRY_INTRINSICS_KEY]
    if intrinsics_source != 'calibratable':
        return None
    intrinsics_file_name = get_camera_info_file_name_of_unit(profile_camera.camera_type,
                                                             profile_camera.serial)
    intrinsics_folder_path = get_intrinsics_folder_path(profile_launch_context)
    return get_path_in_config_folder(f'{intrinsics_folder_path}/{intrinsics_file_name}')


def _get_intrinsics_file_state(profile_launch_context: LaunchContext,
                               intrinsics_file_name: str) -> str:
    """Return whether the profile's intrinsics folder holds the file (INTRINSICS_STATE_*)."""
    # Simplification: only checks that the file exists, not that it holds a valid calibration.
    # The same folder launch_helpers.get_camera_info_url gives the drivers
    intrinsics_folder_path = get_intrinsics_folder_path(profile_launch_context)
    intrinsics_path = get_path_in_config_folder(
        f'{intrinsics_folder_path}/{intrinsics_file_name}')
    if os.path.exists(intrinsics_path):
        return INTRINSICS_STATE_CALIBRATED
    return INTRINSICS_STATE_MISSING


def _read_camera_pose_state(profile_launch_context: LaunchContext, camera_name: str) -> str:
    """Return whether the profile has a measured pose for the named camera (POSE_STATE_*)."""
    # The same file launch_helpers.create_mount_tf_publisher reads instead of the placeholder.
    pose_path = get_path_in_config_folder(
        get_extrinsics_relative_path(profile_launch_context, 'camera_pose', camera_name))
    if not os.path.exists(pose_path):
        return POSE_STATE_PLACEHOLDER
    with open(pose_path) as pose_file:
        camera_pose = yaml.safe_load(pose_file)
    if get_invalid_pose_keys(camera_pose):
        return POSE_STATE_INVALID
    return POSE_STATE_MEASURED


def create_profile_launch_context(profile_name: str) -> LaunchContext:
    """Return a launch context like `ros2 launch ... par.launch.py profile:=<profile_name>`."""
    # So launch_helpers merges par_setup.yaml and the profile exactly as a launch does.
    profile_launch_context = LaunchContext()
    default_params_file_path = os.path.join(get_package_share_directory('par_framework_core'),
                                            'config', 'par_setup.yaml')
    profile_launch_context.launch_configurations['params_file'] = default_params_file_path
    profile_launch_context.launch_configurations['profile'] = profile_name
    # No per-run override, as in a launch without projector_display_id:=
    profile_launch_context.launch_configurations['projector_display_id'] = ''
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


# Written by Claude Code
def _find_connected_display(display_id: int) -> ConnectedDisplay:
    """Return the connected display with this display_id; HTTP 422 when there is none."""
    try:
        connected_displays = read_connected_displays()
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    for connected_display in connected_displays:
        if connected_display.display_id == display_id:
            return connected_display
    raise HTTPException(status_code=422,
                        detail=f'Display {display_id} is not connected: search the displays '
                               f'again and choose a connected one')


# Written by Claude Code
def _write_projector_display_into_profile(profile_name: str,
                                          projector_display: ConnectedDisplay) -> None:
    """Write the projector's display id, identity and display mode into the profile's par_launch."""
    # The id is pinned even when par_setup.yaml has the same, like the identity it belongs to
    setting_value_by_name = {'projector_display_id': projector_display.display_id}
    for parameter_name, identity_text in get_projector_identity(projector_display).items():
        # None removes a value the display does not report, so none of an earlier projector stays
        if identity_text:
            setting_value_by_name[parameter_name] = identity_text
        else:
            setting_value_by_name[parameter_name] = None
    # A refresh rate the display does not report is None and removes an earlier one the same way
    setting_value_by_name.update(get_projector_display_mode(projector_display))
    write_node_settings_into_profile(profile_name, '/par_launch', setting_value_by_name,
                                     always_written_setting_names=('projector_display_id',))


# Co-authored by Claude Code: settings that are kept even when equal to par_setup.yaml's
def write_node_settings_into_profile(profile_name: str, full_node_name: str,
                                     setting_value_by_name: dict,
                                     always_written_setting_names: tuple = ()
                                     ) -> NodeSettingsWriteResult:
    """
    Write settings of a node into the profile, as ROS reads them at the node's next start.

    Only what differs from par_setup.yaml is kept, as in a hand-written profile: a value equal
    to par_setup.yaml's removes its key, except for always_written_setting_names. The file is
    rewritten with ruamel.yaml's round trip, which keeps comments, quotes and layout of
    everything else.
    """
    check_profile_exists(profile_name)
    profile_path = get_path_in_config_folder(
        f'{FOLDER_PATH_PROFILES}/{profile_name}{PROFILE_FILE_EXTENSION}')
    default_setting_value_by_name = read_par_setup_node_settings(full_node_name)
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
            # None asks for the key to be removed, e.g. a list with no entry left
            is_par_setup_value = setting_value is None or (
                setting_name in default_setting_value_by_name and _is_same_value(
                    default_setting_value_by_name[setting_name], setting_value))
            is_always_written = setting_name in always_written_setting_names
            if is_par_setup_value and not is_always_written:
                if setting_name in node_parameters:
                    _delete_key_keeping_comment_after_section(node_parameters, setting_name)
                removed_setting_names.append(setting_name)
            elif setting_name in node_parameters:
                node_parameters[setting_name] = setting_value
                written_setting_names.append(setting_name)
            else:
                _add_key_keeping_comment_after_section(node_parameters, setting_name,
                                                       setting_value)
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


# Written by Claude Code
def _add_key_keeping_comment_after_section(yaml_mapping: CommentedMap, key: str,
                                           value) -> None:
    """Add key at the end; what follows the old last key's line moves after the new key."""
    # ruamel.yaml stores the empty lines and comments before the next section with the last key
    # of this one, so a key appended after it would land below them, inside the next section's
    # comment. A comment on the old last key's own line stays with it
    keys = list(yaml_mapping.keys())
    yaml_mapping[key] = value
    if not keys:
        return
    following_text = _take_text_after_value_line(yaml_mapping, keys[-1])
    _append_text_after_value_line(yaml_mapping, key, following_text)


def _delete_key_keeping_comment_after_section(yaml_mapping: CommentedMap, key: str) -> None:
    """Delete key; what follows the last key's line moves to the new last key."""
    # Without this, deleting a section's last setting also deletes the empty lines and comments
    # that separate the section from the next one. A comment on the deleted key's own line
    # belonged to it and goes with it
    keys = list(yaml_mapping.keys())
    is_last_key = keys[-1] == key
    following_text = ''
    if is_last_key:
        following_text = _take_text_after_value_line(yaml_mapping, key)
    del yaml_mapping[key]
    if is_last_key and len(keys) >= 2:
        _append_text_after_value_line(yaml_mapping, keys[-2], following_text)


def _take_text_after_value_line(yaml_mapping: CommentedMap, key: str) -> str:
    """Remove and return what ruamel.yaml stores after the line of key's value ('' if nothing)."""
    comment_record = yaml_mapping.ca.items.get(key)
    if comment_record is None:
        return ''
    comment_after_value = comment_record[RUAMEL_COMMENT_AFTER_VALUE_INDEX]
    if comment_after_value is None:
        return ''
    # The text starts with what is left of the value's own line: a comment there, or only its
    # line break
    comment_text = comment_after_value.value
    line_end_index = comment_text.find('\n')
    if line_end_index < 0:
        return ''
    same_line_text = comment_text[:line_end_index + 1]
    following_text = comment_text[line_end_index + 1:]
    if same_line_text.strip():
        comment_record[RUAMEL_COMMENT_AFTER_VALUE_INDEX] = CommentToken(
            same_line_text, comment_after_value.start_mark, None)
    else:
        comment_record[RUAMEL_COMMENT_AFTER_VALUE_INDEX] = None
    return following_text


def _append_text_after_value_line(yaml_mapping: CommentedMap, key: str,
                                  following_text: str) -> None:
    """Put following_text (empty lines, comments) after the line of key's value."""
    if not following_text:
        return
    comment_record = yaml_mapping.ca.items.setdefault(key, [None, None, None, None])
    comment_after_value = comment_record[RUAMEL_COMMENT_AFTER_VALUE_INDEX]
    if comment_after_value is None:
        # The leading line break ends the value's own line
        comment_record[RUAMEL_COMMENT_AFTER_VALUE_INDEX] = CommentToken(
            '\n' + following_text, CommentMark(0), None)
        return
    comment_after_value.value = comment_after_value.value + following_text


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


def read_par_setup_node_settings(full_node_name: str) -> dict:
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
