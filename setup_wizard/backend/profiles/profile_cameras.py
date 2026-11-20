# Written by Claude Code
"""
Profile cameras for the setup wizard backend: adding and removing a profile's named cameras.

A profile names its cameras in par_launch.cameras (name -> '<type>[:<serial>]'; the first is the
main camera). Adding one checks it against the profile's other cameras; its pose is the generic
placeholder until it is measured. Removing one moves its calibrations and node sections to
config/profiles/.deleted/ and takes its name out of everything that refers to it, so the next
launch does not refuse the profile. Used by the camera endpoints (cameras_api.py) and the
new-profile endpoint (profiles_api.py).
"""

import os
import shutil

from cameras.camera_types import read_installed_camera_entry
from fastapi import HTTPException
from par_framework_core.camera_poses import CAMERA_POSE_KEYS, CAMERA_TF_PUBLISHER_NAME_SUFFIX
from par_framework_core.camera_types import (CAMERA_ENTRY_INTRINSICS_KEY, CAMERA_ENTRY_SERIAL_KEY,
                                             CAMERA_INTRINSICS_SOURCE_CALIBRATABLE,
                                             CAMERA_SERIAL_SOURCE_NONE, read_camera_entry)
from par_framework_core.par_launch_cameras import (CAMERA_NAME_PATTERN, PAR_LAUNCH_CAMERAS_KEY,
                                                   ProfileCamera)
from par_framework_core.sensor_nodes import get_sensor_node_package_names
from par_framework_core.setup_files import (FILE_NAME_PART_PATTERN, get_extrinsics_relative_path,
                                            get_path_in_config_folder,
                                            get_unit_intrinsics_file_path)
from profiles.profile_files import (create_deleted_folder,
                                    find_camera_node_section_names, find_profile_camera,
                                    move_camera_node_sections, PAR_LAUNCH_NODE_NAME,
                                    read_camera_name_by_input_by_app,
                                    read_profile_cameras_or_raise, read_profile_document,
                                    read_profile_launch_section,
                                    write_app_inputs, write_node_settings_into_profile)
from pydantic import BaseModel

# The extrinsics files of a camera, by their prefix in the profile's extrinsics folder
CAMERA_EXTRINSICS_FILE_PREFIXES = ('camera_pose', 'projection_mapping', 'projection_corners')


class NewCameraRequest(BaseModel):
    # Its name in par_launch.cameras (lower case letters, digits and _), e.g. overhead
    camera_name: str
    # A camera type from GET /api/cameras
    camera_type: str
    # The unit's serial; '' for a camera type that has none
    serial: str = ''


def check_new_camera(profile_cameras: list[ProfileCamera], camera_name: str, camera_type: str,
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
    camera_entry = read_installed_camera_entry(camera_type)
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
    _check_unit_is_new(cameras_of_type, camera_type, serial)
    return ProfileCamera(camera_name, camera_type, serial)


def _check_unit_is_new(cameras_of_type: list[ProfileCamera], camera_type: str,
                       serial: str) -> None:
    """Raise 409 or 422 unless serial names a unit the profile's cameras of its type are not."""
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


def create_camera_unit_text(profile_camera: ProfileCamera) -> str:
    """Return the camera's value in par_launch.cameras: '<type>' or '<type>:<serial>'."""
    if profile_camera.serial:
        return f'{profile_camera.camera_type}:{profile_camera.serial}'
    return profile_camera.camera_type


def get_camera_tf_publisher_section_name(camera_name: str) -> str:
    """Return the node section of the camera's pose publisher, e.g. /overhead_tf_publisher."""
    return f'/{camera_name}{CAMERA_TF_PUBLISHER_NAME_SUFFIX}'


def write_profile_cameras(profile_name: str, profile_cameras: list[ProfileCamera]) -> None:
    """Write par_launch.cameras, keeping the cameras' order: the first is the main camera."""
    camera_unit_text_by_name = {}
    for profile_camera in profile_cameras:
        camera_unit_text_by_name[profile_camera.camera_name] = create_camera_unit_text(
            profile_camera)
    # Pinned even when it equals par_setup.yaml's: the profile names its own cameras
    write_node_settings_into_profile(profile_name, PAR_LAUNCH_NODE_NAME,
                                     {PAR_LAUNCH_CAMERAS_KEY: camera_unit_text_by_name},
                                     always_written_setting_names=(PAR_LAUNCH_CAMERAS_KEY,))


def remove_camera_from_profile(profile_name: str, camera_name: str) -> str:
    """
    Remove a camera from the profile; return where its files went, '' when it had none.

    Its calibrations and node sections (/cameras/<camera name>/...) move to
    config/profiles/.deleted/, so a new camera of the same name starts with the defaults. The
    last camera can go too: the profile then names no camera and cannot run until one is added.
    """
    profile_cameras = read_profile_cameras_or_raise(profile_name)
    removed_camera = find_profile_camera(profile_cameras, camera_name)
    deleted_folder_path = _move_camera_files_out_of_use(profile_name, removed_camera)
    remaining_cameras = []
    for profile_camera in profile_cameras:
        if profile_camera.camera_name != camera_name:
            remaining_cameras.append(profile_camera)
    write_profile_cameras(profile_name, remaining_cameras)
    # Nothing may name the removed camera any more, or the next launch refuses the profile
    launch_section = read_profile_launch_section(profile_name)
    _remove_camera_from_sensor_node_lists(profile_name, launch_section, camera_name)
    _unbind_camera_from_app_inputs(profile_name, launch_section, camera_name)
    _remove_camera_placeholder_pose(profile_name, camera_name)
    return deleted_folder_path


def _move_camera_files_out_of_use(profile_name: str, removed_camera: ProfileCamera) -> str:
    """Move the camera's calibration files and node sections into a new deleted folder."""
    existing_file_paths = _read_existing_camera_file_paths(profile_name, removed_camera)
    camera_node_section_names = find_camera_node_section_names(
        read_profile_document(profile_name), removed_camera.camera_name)
    has_camera_node_sections = bool(camera_node_section_names)
    # A camera never calibrated or set leaves nothing to keep, so no empty folder is created for it
    deleted_folder_path = ''
    if existing_file_paths or has_camera_node_sections:
        deleted_folder_path = create_deleted_folder(
            f'{profile_name}_{removed_camera.camera_name}')
    for existing_file_path in existing_file_paths:
        shutil.move(existing_file_path, deleted_folder_path)
    if has_camera_node_sections:
        move_camera_node_sections(profile_name, removed_camera.camera_name, deleted_folder_path)
    return deleted_folder_path


def _read_existing_camera_file_paths(profile_name: str,
                                     profile_camera: ProfileCamera) -> list[str]:
    """Return the camera's intrinsics and extrinsics files that exist."""
    file_paths = [get_unit_intrinsics_file_path(profile_name,
                                                profile_camera.camera_type,
                                                profile_camera.serial)]
    for file_prefix in CAMERA_EXTRINSICS_FILE_PREFIXES:
        extrinsics_relative_path = get_extrinsics_relative_path(
            profile_name, file_prefix, profile_camera.camera_name)
        file_paths.append(get_path_in_config_folder(extrinsics_relative_path))
    existing_file_paths = []
    for file_path in file_paths:
        if os.path.exists(file_path):
            existing_file_paths.append(file_path)
    return existing_file_paths


def _remove_camera_from_sensor_node_lists(profile_name: str, launch_section: dict,
                                          camera_name: str) -> None:
    """Take the camera out of every par_launch.<sensor node> list that names it."""
    camera_list_by_sensor_node = {}
    for sensor_node_name in get_sensor_node_package_names():
        listed_camera_names = launch_section.get(sensor_node_name)
        if not isinstance(listed_camera_names, list):
            continue
        if camera_name not in listed_camera_names:
            continue
        remaining_camera_names = []
        for listed_camera_name in listed_camera_names:
            if listed_camera_name != camera_name:
                remaining_camera_names.append(listed_camera_name)
        # A node left on no camera leaves the profile (None removes its key): a missing key
        # already means no camera
        if remaining_camera_names:
            camera_list_by_sensor_node[sensor_node_name] = remaining_camera_names
        else:
            camera_list_by_sensor_node[sensor_node_name] = None
    if camera_list_by_sensor_node:
        write_node_settings_into_profile(profile_name, PAR_LAUNCH_NODE_NAME,
                                         camera_list_by_sensor_node)


def _unbind_camera_from_app_inputs(profile_name: str, launch_section: dict,
                                   camera_name: str) -> None:
    """Unbind every app input bound to the camera in par_launch.app_inputs."""
    # An unbound input reads the only camera of a run, or must be bound anew
    camera_name_by_input_by_app = read_camera_name_by_input_by_app(launch_section)
    for camera_name_by_input in camera_name_by_input_by_app.values():
        for input_name in list(camera_name_by_input):
            if camera_name_by_input[input_name] == camera_name:
                del camera_name_by_input[input_name]
    write_app_inputs(profile_name, camera_name_by_input_by_app)


def _remove_camera_placeholder_pose(profile_name: str, camera_name: str) -> None:
    """Remove the camera's placeholder pose from the profile."""
    # A section par_setup.yaml holds stays there
    removed_pose_value_by_key = {}
    for pose_key in CAMERA_POSE_KEYS:
        removed_pose_value_by_key[pose_key] = None
    write_node_settings_into_profile(profile_name,
                                     get_camera_tf_publisher_section_name(camera_name),
                                     removed_pose_value_by_key)


def get_camera_intrinsics_file_path(profile_name: str, camera_name: str) -> str | None:
    """
    Return the path of the intrinsics file the framework gives the profile's camera at launch.

    The same file launch_helpers.get_camera_info_url names, whatever the driver calls its
    parameter for it. None when the framework gives the camera none: its type is not
    calibratable (intrinsics: factory or none in its entry).
    """
    profile_camera = find_profile_camera(read_profile_cameras_or_raise(profile_name), camera_name)
    intrinsics_source = read_camera_entry(profile_camera.camera_type)[CAMERA_ENTRY_INTRINSICS_KEY]
    if intrinsics_source != CAMERA_INTRINSICS_SOURCE_CALIBRATABLE:
        return None
    return get_unit_intrinsics_file_path(profile_name, profile_camera.camera_type,
                                         profile_camera.serial)
