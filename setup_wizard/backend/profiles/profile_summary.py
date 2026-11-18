# Written by Claude Code
"""
Profile summary for the setup wizard backend: what a profile runs and how far it is set up.

Per profile: its cameras with the state of their intrinsics and pose, its apps and the camera
bound to each app input, and whether its projector is connected where the profile says, checked
the way a launch finds it (by the projector's stored identity). The profile endpoints
(profiles_api.py) list it for every profile.
"""

import os

from launch import LaunchContext
from par_framework_core.connected_displays import (
    ConnectedDisplay, find_projector_display_ids, get_display_mode_text, get_display_title_text,
    get_projector_display_mode, get_projector_identity_title_text,
    PROJECTOR_DISPLAY_MODE_PARAMETER_NAME_BY_ATTRIBUTE, read_connected_displays)
from par_framework_core.launch_helpers import (CAMERA_ENTRY_INTRINSICS_KEY,
                                               CAMERA_INTRINSICS_SOURCE_FACTORY,
                                               CAMERA_INTRINSICS_SOURCE_NONE,
                                               get_extrinsics_relative_path,
                                               get_invalid_pose_keys,
                                               get_path_in_config_folder,
                                               get_unit_intrinsics_file_path, ProfileCamera,
                                               PROJECTOR_APP_NONE, read_camera_entry,
                                               read_launch_section,
                                               read_projector_identity,
                                               read_published_camera_pose,
                                               read_stored_projector_display_id)
from profiles.profile_files import (create_profile_launch_context, PROFILE_READ_ERROR_TYPES,
                                    read_camera_name_by_input_by_app, read_enabled_app_names,
                                    read_profile_cameras_allowing_none,
                                    read_profile_own_launch_parameters)
from pydantic import BaseModel

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
    # Whether the projector is calibrated against this camera (its projection mapping file exists)
    has_projection_mapping: bool = False


class ProfileSummary(BaseModel):
    profile_name: str
    cameras: list[CameraCalibrationSummary]
    app_names: list[str]
    # The apps the profile offers (par_launch.apps), in its order; the projector app is one of them
    enabled_app_names: list[str] = []
    # par_launch.app_inputs: per app, the camera bound to each input; an input left out reads the
    # only camera of a run
    camera_name_by_input_by_app: dict[str, dict[str, str]] = {}
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


def read_connected_displays_for_summary() -> tuple[list[ConnectedDisplay], str | None]:
    """Return the connected displays and None, or [] and why they cannot be read."""
    try:
        return read_connected_displays(), None
    except RuntimeError as error:
        return [], str(error)


def read_profile_summary(profile_name: str, connected_displays: list[ConnectedDisplay],
                         displays_error_text: str | None) -> ProfileSummary:
    """
    Return the cameras and apps the profile starts through par_launch.

    connected_displays is empty and displays_error_text says why when they cannot be read.
    """
    profile_launch_context = create_profile_launch_context(profile_name)
    try:
        launch_section = read_launch_section(profile_launch_context)
        enabled_app_names = read_enabled_app_names(launch_section)
        projector_display_summary = _create_projector_display_summary(
            profile_name, launch_section, connected_displays, displays_error_text)
        cameras = []
        profile_cameras = read_profile_cameras_allowing_none(profile_name)
        for camera_index, profile_camera in enumerate(profile_cameras):
            cameras.append(_create_camera_summary(profile_launch_context, profile_camera,
                                                  camera_index == 0))
    except PROFILE_READ_ERROR_TYPES as error:
        # A profile is written by hand: one broken file must not hide the other profiles.
        return ProfileSummary(profile_name=profile_name, cameras=[], app_names=[],
                              profile_error_text=str(error))

    app_names = []
    projector_app_name = str(launch_section.get('projector_app', PROJECTOR_APP_NONE))
    if projector_app_name != PROJECTOR_APP_NONE:
        app_names.append(projector_app_name)
    camera_name_by_input_by_app = read_camera_name_by_input_by_app(launch_section)
    return ProfileSummary(profile_name=profile_name, cameras=cameras, app_names=app_names,
                          enabled_app_names=enabled_app_names,
                          camera_name_by_input_by_app=camera_name_by_input_by_app,
                          **projector_display_summary)


def _create_projector_display_summary(profile_name: str, launch_section: dict,
                                      connected_displays: list[ConnectedDisplay],
                                      displays_error_text: str | None) -> dict:
    """Return the ProfileSummary fields about the projector, checked like a launch finds it."""
    # The profile's own choice: par_setup.yaml's default display is no projector chosen for it
    stored_projector_display_id = read_stored_projector_display_id(
        read_profile_own_launch_parameters(profile_name))
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
        print(f'[profile_summary]: cannot check the projector: {displays_error_text}')
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
        pose_state=_read_camera_pose_state(profile_launch_context, profile_camera.camera_name),
        has_projection_mapping=_has_projection_mapping(profile_launch_context,
                                                       profile_camera.camera_name))


def _read_camera_intrinsics_state(profile_launch_context: LaunchContext,
                                  profile_camera: ProfileCamera) -> str:
    """Return whether the camera's unit has its lens calibration (INTRINSICS_STATE_*)."""
    intrinsics_source = read_camera_entry(profile_camera.camera_type)[CAMERA_ENTRY_INTRINSICS_KEY]
    if intrinsics_source == CAMERA_INTRINSICS_SOURCE_FACTORY:
        return INTRINSICS_STATE_FACTORY
    if intrinsics_source == CAMERA_INTRINSICS_SOURCE_NONE:
        return INTRINSICS_STATE_UNSUPPORTED
    # Simplification: only checks that the file exists, not that it holds a valid calibration.
    # The same file launch_helpers.get_camera_info_url gives the driver
    intrinsics_path = get_unit_intrinsics_file_path(profile_launch_context,
                                                    profile_camera.camera_type,
                                                    profile_camera.serial)
    if os.path.exists(intrinsics_path):
        return INTRINSICS_STATE_CALIBRATED
    return INTRINSICS_STATE_MISSING


def _has_projection_mapping(profile_launch_context: LaunchContext, camera_name: str) -> bool:
    """Return whether the profile has a projection mapping for the named camera."""
    # Simplification: only checks that the file exists, as for the intrinsics. The same file
    # setup_geometry_api reads for the drawing
    mapping_path = get_path_in_config_folder(get_extrinsics_relative_path(
        profile_launch_context, 'projection_mapping', camera_name))
    return os.path.exists(mapping_path)


def _read_camera_pose_state(profile_launch_context: LaunchContext, camera_name: str) -> str:
    """Return whether the profile has a measured pose for the named camera (POSE_STATE_*)."""
    camera_pose, _, is_pose_measured = read_published_camera_pose(profile_launch_context,
                                                                  camera_name)
    if not is_pose_measured:
        return POSE_STATE_PLACEHOLDER
    if get_invalid_pose_keys(camera_pose):
        return POSE_STATE_INVALID
    return POSE_STATE_MEASURED
