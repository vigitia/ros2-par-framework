# Written by Claude Code
"""
The cameras of a PAR setup: par_launch.cameras of the parameter files, and their namespaces.

par_launch.cameras maps each camera's name to its unit, '<camera type>' or
'<camera type>:<serial>', e.g. {overhead: 'blackfly:22260470'}. The name makes the camera's
namespace (/cameras/<name>), its frames (<name>_link, ...) and its extrinsics files; the unit
makes its intrinsics file (camera_info_<type>_<serial>.yaml), since they belong to the lens. A
replaced unit keeps its name, topics, pose and projection mapping.
"""

import collections
import re

from par_framework_core.camera_types import (CAMERA_ENTRY_SERIAL_KEY, CAMERA_RESOURCE_TYPE,
                                             CAMERA_SERIAL_SOURCE_NONE, get_camera_type_names,
                                             read_camera_entry)
from par_framework_core.setup_files import (FILE_NAME_PART_PATTERN, PAR_LAUNCH_SECTION_NAME,
                                            read_launch_section, read_params_file)


# Every camera runs in CAMERAS_NAMESPACE/<camera name>, e.g. /cameras/blackfly
CAMERAS_NAMESPACE = '/cameras'
PAR_LAUNCH_CAMERAS_KEY = 'cameras'
# A camera name is part of ROS names and file names: lower case, digits and _, starting with a
# letter (ROS names may not contain - or start with a digit)
CAMERA_NAME_PATTERN = re.compile(r'[a-z][a-z0-9_]*')
# The par_launch keys of the one-camera format, refused with a message naming the fix
OLD_PAR_LAUNCH_CAMERA_KEYS = ('camera', 'additional_cameras', 'capture_camera')
# A camera to start: its name, its type (an entry in CAMERA_RESOURCE_TYPE) and its unit's serial
# ('' opens the first unit found)
ProfileCamera = collections.namedtuple('ProfileCamera', ['camera_name', 'camera_type', 'serial'])


def get_camera_namespace(camera_name):
    """Return the namespace a camera runs in: /cameras/<camera name>."""
    return f'{CAMERAS_NAMESPACE}/{camera_name}'


def read_profile_cameras(params_file_paths):
    """
    Return the cameras par_launch.cameras names, in its order, as ProfileCamera tuples.

    Raises RuntimeError naming the fix when the list is missing or malformed, or when the
    parameter files still use the one-camera keys.
    """
    launch_section = read_launch_section(params_file_paths)
    old_keys = [key for key in OLD_PAR_LAUNCH_CAMERA_KEYS if key in launch_section]
    if old_keys:
        raise RuntimeError(f'[par_launch_cameras]: par_launch.{", par_launch.".join(old_keys)}: '
                           f'no longer read; name every camera in par_launch.'
                           f'{PAR_LAUNCH_CAMERAS_KEY} instead, e.g. {PAR_LAUNCH_CAMERAS_KEY}: '
                           f"{{overhead: 'blackfly:22260470'}}, and remove {', '.join(old_keys)}")
    # The last parameter file that names cameras sets all of them: a profile's cameras replace
    # par_setup.yaml's default instead of being merged with it key by key
    camera_unit_text_by_name = None
    cameras_source_path = None
    for params_file_path in params_file_paths:
        file_parameters = read_params_file(params_file_path)
        launch_section_of_file = file_parameters.get(PAR_LAUNCH_SECTION_NAME) or {}
        launch_parameters = launch_section_of_file.get('ros__parameters') or {}
        if PAR_LAUNCH_CAMERAS_KEY in launch_parameters:
            camera_unit_text_by_name = launch_parameters[PAR_LAUNCH_CAMERAS_KEY]
            cameras_source_path = params_file_path
    if not isinstance(camera_unit_text_by_name, dict) or not camera_unit_text_by_name:
        # Par_setup.yaml names no camera, so this is where a launch without profile:= ends up
        raise RuntimeError(f'[par_launch_cameras]: no cameras: pass profile:=<name> (the setup '
                           f'wizard, ./scripts/start_setup_wizard.sh, creates one), map each '
                           f'camera name to its unit in par_launch.{PAR_LAUNCH_CAMERAS_KEY} of '
                           f'the profile, e.g. {PAR_LAUNCH_CAMERAS_KEY}: {{overhead: '
                           f'"blackfly:22260470"}}, or pass camera:=<type>[:<serial>]')

    profile_cameras = []
    for camera_name, camera_unit_text in camera_unit_text_by_name.items():
        source_text = f'par_launch.{PAR_LAUNCH_CAMERAS_KEY}.{camera_name} in {cameras_source_path}'
        if not isinstance(camera_name, str) or not CAMERA_NAME_PATTERN.fullmatch(camera_name):
            raise RuntimeError(f'[par_launch_cameras]: {source_text}: a camera name may only '
                               f'hold lower case letters, digits and _, starting with a letter')
        camera_type, serial = parse_camera_unit_text(camera_unit_text, source_text)
        profile_cameras.append(ProfileCamera(camera_name, camera_type, serial))
    return profile_cameras


def parse_camera_unit_text(camera_unit_text, source_text):
    """Return (camera type, serial) of '<type>' or '<type>:<serial>'; the serial may be ''."""
    # str(): YAML reads a unit written as a bare number, e.g. a serial alone, as an int
    camera_type, _, serial = str(camera_unit_text).partition(':')
    camera_type_names = get_camera_type_names()
    if camera_type not in camera_type_names:
        camera_type_names_text = ', '.join(camera_type_names) or 'none'
        raise RuntimeError(f'[par_launch_cameras]: {source_text}: unknown camera type '
                           f'{camera_type!r} in {camera_unit_text!r}; write <type> or '
                           f'<type>:<serial> with one of the installed camera types '
                           f'({camera_type_names_text}). A camera type is installed with the '
                           f'package that registers it ({CAMERA_RESOURCE_TYPE})')
    if serial and not FILE_NAME_PART_PATTERN.fullmatch(serial):
        raise RuntimeError(f'[par_launch_cameras]: {source_text}: {serial!r} is no serial '
                           f'number: use only letters, digits, _ and -')
    # The launch file would ignore it, while the intrinsics file is named after it
    is_serial_unsupported = (
        read_camera_entry(camera_type)[CAMERA_ENTRY_SERIAL_KEY] == CAMERA_SERIAL_SOURCE_NONE)
    if serial and is_serial_unsupported:
        raise RuntimeError(f'[par_launch_cameras]: {source_text}: camera type {camera_type} has '
                           f'no serial numbers ({CAMERA_ENTRY_SERIAL_KEY}: none in its entry); '
                           f'write {camera_type!r} alone')
    return camera_type, serial
