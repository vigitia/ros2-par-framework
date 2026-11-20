# Written by Claude Code
"""
Profiles API of the setup wizard backend: the hardware setups (config/profiles/<name>.yaml).

Lists them with their cameras and apps and each camera's calibration state (profile_summary.py),
remembers the one selected last time, creates a new profile without cameras and projector,
copies a profile with its calibrations, stores the profile's projector and moves a deleted
profile out of use. A profile's cameras are added and removed through cameras_api.py, its apps
through apps_api.py; all of them read and write the profile files through profile_files.py.
"""

import datetime
import os
import shutil

from fastapi import APIRouter, HTTPException
from par_framework_core.connected_displays import (ConnectedDisplay, get_projector_display_mode,
                                                   get_projector_identity)
from par_framework_core.par_launch_cameras import PAR_LAUNCH_CAMERAS_KEY
from par_framework_core.setup_files import (create_folder_of_file, FILE_NAME_PART_PATTERN,
                                            FOLDER_PATH_CAMERA_INTRINSICS, FOLDER_PATH_EXTRINSICS,
                                            FOLDER_PATH_PROFILES, get_path_in_config_folder,
                                            get_profile_file_path)
from profiles.profile_files import (check_profile_exists, DELETED_PROFILES_FOLDER_NAME,
                                    DeletedProfileResponse, PAR_LAUNCH_NODE_NAME,
                                    read_profile_names, ROS_PARAMETERS_KEY,
                                    write_node_settings_into_profile)
from profiles.profile_summary import (ProfileSummary, read_connected_displays_for_summary,
                                      read_profile_summary)
from pydantic import BaseModel
from shared.backend_helpers import read_connected_displays_or_raise

# In the profiles folder, which is gitignored as a whole: the selection belongs to this machine.
# Hidden and without .yaml, so it is never listed as a profile.
LAST_SELECTED_PROFILE_FILE_NAME = '.setup_wizard_last_selected_profile'
# A deleted profile's intrinsics and extrinsics go into these subfolders of its deleted folder
DELETED_INTRINSICS_FOLDER_NAME = 'intrinsics'
DELETED_EXTRINSICS_FOLDER_NAME = 'extrinsics'
# How the first line of a profile the wizard writes starts; a copy replaces that line
PROFILE_HEADER_LINE_START = '# Setup profile '

profiles_router = APIRouter()


class ProfileListResponse(BaseModel):
    profiles: list[ProfileSummary]
    # None when nothing was selected yet, or the profile selected last time no longer exists.
    last_selected_profile_name: str | None


class LastSelectedProfileRequest(BaseModel):
    profile_name: str


class NewProfileRequest(BaseModel):
    # The file name without .yaml and the value of profile:=
    profile_name: str
    # As the user typed it, kept as a comment at the top of the file
    profile_display_name: str


class ProjectorDisplayChoiceRequest(BaseModel):
    # A display_id from GET /api/displays
    display_id: int


class ProfileCopyRequest(BaseModel):
    # The copy's file name without .yaml and the value of profile:=
    new_profile_name: str
    # As the user typed it, kept as a comment at the top of the copy
    new_profile_display_name: str


@profiles_router.get('/api/profiles')
def get_profile_list() -> ProfileListResponse:
    """List the profiles (config/profiles/<name>.yaml) with what they run, and the last choice."""
    profile_names = read_profile_names()
    # Read once for all profiles: SDL opens the displays per call
    connected_displays, displays_error_text = read_connected_displays_for_summary()
    profile_summaries = []
    for profile_name in profile_names:
        profile_summaries.append(read_profile_summary(profile_name, connected_displays,
                                                      displays_error_text))
    last_selected_profile_name = _read_last_selected_profile_name()
    if last_selected_profile_name not in profile_names:
        last_selected_profile_name = None
    return ProfileListResponse(profiles=profile_summaries,
                               last_selected_profile_name=last_selected_profile_name)


@profiles_router.get('/api/profiles/{profile_name}')
def get_profile(profile_name: str) -> ProfileSummary:
    """Return one profile as the list does; profile_error_text says why one cannot be read."""
    check_profile_exists(profile_name)
    connected_displays, displays_error_text = read_connected_displays_for_summary()
    return read_profile_summary(profile_name, connected_displays, displays_error_text)


@profiles_router.put('/api/profiles/last-selected')
def set_last_selected_profile(request: LastSelectedProfileRequest) -> None:
    """Remember the selected profile, so the wizard opens it next time."""
    # The name ends up in a file path and in profile:=, so it must be an existing profile name.
    check_profile_exists(request.profile_name)
    with open(_get_last_selected_profile_path(), 'w') as last_selected_profile_file:
        last_selected_profile_file.write(request.profile_name)


@profiles_router.post('/api/profiles')
def create_profile(request: NewProfileRequest) -> None:
    """
    Create config/profiles/<name>.yaml without cameras and projector.

    The user adds them afterwards in the Cameras and Projectors areas; the profile names an empty
    camera list, so no camera of another parameter file is taken over unnoticed (a launch refuses
    the profile until it has a camera).
    """
    _check_new_profile_name(request.profile_name)
    profile_path = get_profile_file_path(request.profile_name)
    creation_date_text = datetime.date.today().isoformat()
    profile_lines = [
        _create_profile_header_line(request.profile_display_name, request.profile_name),
        f'# Created by the setup wizard on {creation_date_text}.',
        'par_launch:',
        f'  {ROS_PARAMETERS_KEY}:',
        f'    {PAR_LAUNCH_CAMERAS_KEY}: {{}}',
    ]
    # The profiles folder is gitignored, so the first profile of an installation creates it
    create_folder_of_file(profile_path)
    try:
        # 'x' creates the file only if it does not exist, so an existing profile is never
        # overwritten, even by two requests at once
        with open(profile_path, 'x') as profile_file:
            profile_file.write('\n'.join(profile_lines) + '\n')
    except FileExistsError:
        raise HTTPException(status_code=409,
                            detail=f'A profile named {request.profile_name!r} exists already')


@profiles_router.put('/api/profiles/{profile_name}/projector-display')
def set_projector_display(profile_name: str, request: ProjectorDisplayChoiceRequest) -> None:
    """Store which connected display is the profile's projector: its id and its identity."""
    check_profile_exists(profile_name)
    _write_projector_display_into_profile(profile_name,
                                          _find_connected_display(request.display_id))


@profiles_router.post('/api/profiles/{profile_name}/copy')
def copy_profile(profile_name: str, request: ProfileCopyRequest) -> None:
    """
    Copy the profile under a new name, with its calibrations, so it runs on the same setup at once.

    The copy's file is the original's, comments and all, under a new header; its intrinsics and
    extrinsics folders are copies, changed or recalibrated independently of the original's.
    """
    # Only the name of a listed profile reaches a path, so no other file can be read
    check_profile_exists(profile_name)
    new_profile_name = request.new_profile_name
    _check_new_profile_name(new_profile_name)
    new_profile_path = get_profile_file_path(new_profile_name)
    if os.path.exists(new_profile_path):
        raise HTTPException(status_code=409,
                            detail=f'A profile named {new_profile_name!r} exists already')
    # Calibration folders without a profile file are left over by hand; they are never merged
    # into or overwritten, since measured calibrations take real work to redo
    copied_folder_paths = []
    for calibration_folder_path in (FOLDER_PATH_CAMERA_INTRINSICS, FOLDER_PATH_EXTRINSICS):
        source_folder_path = get_path_in_config_folder(f'{calibration_folder_path}/{profile_name}')
        new_folder_path = get_path_in_config_folder(
            f'{calibration_folder_path}/{new_profile_name}')
        if os.path.exists(new_folder_path):
            raise HTTPException(status_code=409,
                                detail=f'{new_folder_path} exists already, without a profile: '
                                       f'move it away or choose another name')
        if os.path.isdir(source_folder_path):
            copied_folder_paths.append((source_folder_path, new_folder_path))

    with open(get_profile_file_path(profile_name)) as source_profile_file:
        source_profile_lines = source_profile_file.read().splitlines()
    # The wizard's header names the original; a hand-written first line is kept below the new one
    if source_profile_lines and source_profile_lines[0].startswith(PROFILE_HEADER_LINE_START):
        source_profile_lines = source_profile_lines[1:]
    copy_date_text = datetime.date.today().isoformat()
    new_profile_lines = [
        _create_profile_header_line(request.new_profile_display_name, new_profile_name),
        f'# Copied by the setup wizard from profile {profile_name} on {copy_date_text}.',
        *source_profile_lines,
    ]
    for source_folder_path, new_folder_path in copied_folder_paths:
        shutil.copytree(source_folder_path, new_folder_path)
    # The profile file last: once it exists, the profile is listed and launched with its
    # calibrations in place. 'x' never overwrites a profile made in the meantime
    try:
        with open(new_profile_path, 'x') as new_profile_file:
            new_profile_file.write('\n'.join(new_profile_lines) + '\n')
    except FileExistsError:
        raise HTTPException(status_code=409,
                            detail=f'A profile named {new_profile_name!r} exists already')


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
    profile_path = get_profile_file_path(profile_name)
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


def _check_new_profile_name(profile_name: str) -> None:
    """HTTP 422 unless the name is one profile:= accepts; it becomes a file and folder name."""
    if not FILE_NAME_PART_PATTERN.fullmatch(profile_name):
        raise HTTPException(status_code=422,
                            detail=f'{profile_name!r} is no valid profile name: use only '
                                   f'letters, digits, _ and -')


def _create_profile_header_line(profile_display_name: str, profile_name: str) -> str:
    """Return the first line of a profile the wizard writes, naming it and its profile:=."""
    # One line, so a typed line break cannot end the comment and add YAML of its own
    one_line_display_name = ' '.join(profile_display_name.split())
    return (f'{PROFILE_HEADER_LINE_START}{one_line_display_name}: only what differs from '
            f'par_setup.yaml (profile:={profile_name}).')


def _get_last_selected_profile_path() -> str:
    return get_path_in_config_folder(f'{FOLDER_PATH_PROFILES}/{LAST_SELECTED_PROFILE_FILE_NAME}')


def _read_last_selected_profile_name() -> str | None:
    last_selected_profile_path = _get_last_selected_profile_path()
    if not os.path.exists(last_selected_profile_path):
        return None
    with open(last_selected_profile_path) as last_selected_profile_file:
        return last_selected_profile_file.read().strip()


def _find_connected_display(display_id: int) -> ConnectedDisplay:
    """Return the connected display with this display_id; HTTP 422 when there is none."""
    for connected_display in read_connected_displays_or_raise():
        if connected_display.display_id == display_id:
            return connected_display
    raise HTTPException(status_code=422,
                        detail=f'Display {display_id} is not connected: search the displays '
                               f'again and choose a connected one')


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
    write_node_settings_into_profile(profile_name, PAR_LAUNCH_NODE_NAME, setting_value_by_name,
                                     always_written_setting_names=('projector_display_id',))
