# Written by Claude Code
"""
The camera types registered in the ament index and their entries.

A camera type registers a marker file share/ament_index/resource_index/par_framework_cameras/
<camera type> whose content is the type's entry, a YAML mapping (format:
README.md of par_framework_core). The entry names the launch file that starts the driver; core
never knows a driver itself.
"""

import os
import re

from ament_index_python.packages import get_package_share_directory
from ament_index_python.resources import get_resources
from par_framework_core.ament_index_entries import (check_entry_has_only_known_keys,
                                                    check_entry_text_keys, is_list_of_texts,
                                                    PLAIN_NAME_PATTERN, read_ament_index_entry)
from par_framework_core.setup_files import FILE_NAME_PART_PATTERN


# The streams a camera may offer, named relative to its namespace by the image_pipeline convention.
# Framework nodes subscribe to them by these relative names; a camera's launch file maps its
# driver's own names onto them below the camera's namespace
CAMERA_STREAM_NAMES = ('image_raw', 'image_raw/compressed', 'camera_info', 'set_camera_info',
                       'depth_registered/image_raw', 'ir/image_raw', 'depth_sensor/ir/image_raw',
                       'depth_sensor/depth/image_raw', 'depth_sensor/camera_info', 'events')

CAMERA_RESOURCE_TYPE = 'par_framework_cameras'
# Where the entry format is documented, named in error messages
CAMERA_ENTRY_FORMAT_DOCUMENTATION_TEXT = 'packages/par-framework-core/README.md (Camera types)'
CAMERA_ENTRY_TEXT_KEYS = ('display_name', 'description')
# package and launch_file: the launch file is share/<package>/launch/<launch_file>
CAMERA_ENTRY_NAME_KEYS = ('package', 'launch_file')
# The child frame of the camera's mount transform is <camera name>_<body_frame>
CAMERA_ENTRY_BODY_FRAME_KEY = 'body_frame'
CAMERA_ENTRY_STREAMS_KEY = 'streams'
# calibratable: intrinsics file per unit, written by run_cameracalibrator.sh; factory: the driver
# publishes its own; none: no camera_info
CAMERA_ENTRY_INTRINSICS_KEY = 'intrinsics'
CAMERA_INTRINSICS_SOURCE_CALIBRATABLE = 'calibratable'
CAMERA_INTRINSICS_SOURCE_FACTORY = 'factory'
CAMERA_INTRINSICS_SOURCE_NONE = 'none'
CAMERA_INTRINSICS_SOURCES = (CAMERA_INTRINSICS_SOURCE_CALIBRATABLE,
                             CAMERA_INTRINSICS_SOURCE_FACTORY, CAMERA_INTRINSICS_SOURCE_NONE)
# Optional: how the units of a type are told apart. none: one unit per setup, no serial (the
# default); typed: the launch file passes a serial, which the user types; listed: as typed, and
# the setup wizard lists the connected units' serials with one of CAMERA_ENTRY_UNIT_LOOKUP_KEYS
CAMERA_ENTRY_SERIAL_KEY = 'serial'
CAMERA_SERIAL_SOURCE_NONE = 'none'
CAMERA_SERIAL_SOURCE_TYPED = 'typed'
CAMERA_SERIAL_SOURCE_LISTED = 'listed'
CAMERA_SERIAL_SOURCES = (CAMERA_SERIAL_SOURCE_NONE, CAMERA_SERIAL_SOURCE_TYPED,
                         CAMERA_SERIAL_SOURCE_LISTED)
# Optional: ROS packages the launch file starts besides its own package, e.g. a released driver an
# entry in core starts; a camera type counts as installed when all of them are (default: none)
CAMERA_ENTRY_REQUIRED_PACKAGES_KEY = 'required_packages'
# Optional, the type's default parameter file, relative to share/<package>/ (e.g.
# config/realsense.yaml). Loaded before params_file and the profile, so both override it; for
# third-party drivers, whose defaults the framework cannot set in their code
CAMERA_ENTRY_PARAMETERS_FILE_KEY = 'parameters_file'
# A relative path of plain name parts below the package's share folder, never leaving it
RELATIVE_SHARE_PATH_PATTERN = re.compile(r'[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*')
# The unit lookups of serial: listed, both plain Linux, no driver needed:
# v4l_by_id_prefix: /dev/v4l/by-id/<prefix>_<serial>-video-index0 (UVC cameras);
# usb_vendor_id: the USB devices of this vendor (4 hexadecimal digits), their serial text read in
# usb_serial_base (16 when the device reports in hexadecimal what its driver takes in decimal);
# usb_product_id (optional) narrows them to one product, for a vendor that makes other USB devices
# too or a camera that shows up as several USB devices with the same serial
CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY = 'v4l_by_id_prefix'
CAMERA_ENTRY_USB_VENDOR_ID_KEY = 'usb_vendor_id'
CAMERA_ENTRY_USB_PRODUCT_ID_KEY = 'usb_product_id'
CAMERA_ENTRY_USB_SERIAL_BASE_KEY = 'usb_serial_base'
CAMERA_ENTRY_UNIT_LOOKUP_KEYS = (CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY, CAMERA_ENTRY_USB_VENDOR_ID_KEY)
USB_SERIAL_BASES = (10, 16)
DEFAULT_USB_SERIAL_BASE = 10
# Vendor and product ids alike, as lsusb shows them
USB_ID_PATTERN = re.compile(r'[0-9a-f]{4}')


def get_camera_type_names():
    """Return the camera types registered in the ament index, sorted."""
    return sorted(get_resources(CAMERA_RESOURCE_TYPE))


def read_camera_entry(camera_type):
    """
    Return the checked entry of an installed camera type, a dict with every key of the format.

    Raises RuntimeError naming the fix when the type is not installed or its entry is malformed.
    """
    entry, error_start_text = read_ament_index_entry(
        CAMERA_RESOURCE_TYPE, camera_type, 'camera type', get_camera_type_names(),
        CAMERA_ENTRY_FORMAT_DOCUMENTATION_TEXT)
    return check_camera_entry(entry, error_start_text)


# Separate from read_camera_entry, so the setup wizard checks entries of repositories that are not
# installed yet the same way
def check_camera_entry(entry, error_start_text):
    """
    Return a camera type's entry (a mapping) checked, a dict with every key of the format.

    Raises RuntimeError starting with error_start_text when a key is unknown, missing or of the
    wrong type.
    """
    other_keys = (CAMERA_ENTRY_BODY_FRAME_KEY, CAMERA_ENTRY_STREAMS_KEY,
                  CAMERA_ENTRY_INTRINSICS_KEY)
    required_keys = CAMERA_ENTRY_TEXT_KEYS + CAMERA_ENTRY_NAME_KEYS + other_keys
    optional_keys = (CAMERA_ENTRY_REQUIRED_PACKAGES_KEY, CAMERA_ENTRY_SERIAL_KEY,
                     CAMERA_ENTRY_USB_SERIAL_BASE_KEY, CAMERA_ENTRY_USB_PRODUCT_ID_KEY,
                     CAMERA_ENTRY_PARAMETERS_FILE_KEY, *CAMERA_ENTRY_UNIT_LOOKUP_KEYS)
    check_entry_has_only_known_keys(entry, required_keys + optional_keys, error_start_text)
    check_entry_text_keys(entry, CAMERA_ENTRY_TEXT_KEYS, error_start_text)
    # A package, a file in it and a frame name part, never a path that could point elsewhere
    for name_key in CAMERA_ENTRY_NAME_KEYS + (CAMERA_ENTRY_BODY_FRAME_KEY,):
        name_value = entry.get(name_key)
        if not isinstance(name_value, str) or not PLAIN_NAME_PATTERN.fullmatch(name_value):
            raise RuntimeError(f'{error_start_text}: {name_key} must be a plain name without a '
                               f'path, e.g. blackfly.launch.py or link')
    streams = entry.get(CAMERA_ENTRY_STREAMS_KEY)
    if not is_list_of_texts(streams):
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_STREAMS_KEY} must be a list of '
                           f'stream names')
    unknown_stream_names = sorted(set(streams) - set(CAMERA_STREAM_NAMES))
    if unknown_stream_names:
        raise RuntimeError(f'{error_start_text}: unknown {CAMERA_ENTRY_STREAMS_KEY} '
                           f'{unknown_stream_names}; known: {list(CAMERA_STREAM_NAMES)}')
    if entry.get(CAMERA_ENTRY_INTRINSICS_KEY) not in CAMERA_INTRINSICS_SOURCES:
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_INTRINSICS_KEY} must be one of '
                           f'{list(CAMERA_INTRINSICS_SOURCES)}')

    checked_entry = {}
    for required_key in required_keys:
        checked_entry[required_key] = entry[required_key]
    checked_entry[CAMERA_ENTRY_STREAMS_KEY] = list(streams)
    checked_entry[CAMERA_ENTRY_REQUIRED_PACKAGES_KEY] = _check_camera_entry_required_packages(
        entry, error_start_text)
    checked_entry[CAMERA_ENTRY_PARAMETERS_FILE_KEY] = _check_camera_entry_parameters_file(
        entry, error_start_text)
    checked_entry.update(_check_camera_entry_serial_keys(entry, error_start_text))
    return checked_entry


def _check_camera_entry_required_packages(entry, error_start_text):
    """Return the entry's required_packages checked, [] when left out."""
    required_package_names = entry.get(CAMERA_ENTRY_REQUIRED_PACKAGES_KEY, [])
    is_list_of_package_names = is_list_of_texts(required_package_names) and all(
        PLAIN_NAME_PATTERN.fullmatch(package_name) for package_name in required_package_names)
    if not is_list_of_package_names:
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_REQUIRED_PACKAGES_KEY} must be a '
                           f'list of ROS package names, e.g. [v4l2_camera]')
    return list(required_package_names)


def _check_camera_entry_parameters_file(entry, error_start_text):
    """Return the entry's parameters_file checked, None when left out."""
    parameters_file_relative_path = entry.get(CAMERA_ENTRY_PARAMETERS_FILE_KEY)
    if parameters_file_relative_path is None:
        return None
    is_relative_share_path = (
        isinstance(parameters_file_relative_path, str)
        and RELATIVE_SHARE_PATH_PATTERN.fullmatch(parameters_file_relative_path)
        and '..' not in parameters_file_relative_path.split('/'))
    if not is_relative_share_path:
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_PARAMETERS_FILE_KEY} must be a '
                           f'path below the share folder of its package, e.g. '
                           f'config/realsense.yaml')
    return parameters_file_relative_path


def _check_camera_entry_serial_keys(entry, error_start_text):
    """
    Return the entry's serial keys checked, every one set (None for an unused lookup).

    Raises RuntimeError naming the fix for a value or combination the format does not allow.
    """
    serial_source = entry.get(CAMERA_ENTRY_SERIAL_KEY, CAMERA_SERIAL_SOURCE_NONE)
    if serial_source not in CAMERA_SERIAL_SOURCES:
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_SERIAL_KEY} must be one of '
                           f'{list(CAMERA_SERIAL_SOURCES)}')
    v4l_by_id_prefix = entry.get(CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY)
    usb_vendor_id = entry.get(CAMERA_ENTRY_USB_VENDOR_ID_KEY)
    usb_product_id = entry.get(CAMERA_ENTRY_USB_PRODUCT_ID_KEY)
    usb_serial_base = entry.get(CAMERA_ENTRY_USB_SERIAL_BASE_KEY, DEFAULT_USB_SERIAL_BASE)
    given_unit_lookup_keys = []
    for unit_lookup_key in CAMERA_ENTRY_UNIT_LOOKUP_KEYS:
        if entry.get(unit_lookup_key) is not None:
            given_unit_lookup_keys.append(unit_lookup_key)
    is_listed = serial_source == CAMERA_SERIAL_SOURCE_LISTED
    if is_listed and len(given_unit_lookup_keys) != 1:
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_SERIAL_KEY}: listed needs exactly '
                           f'one of {list(CAMERA_ENTRY_UNIT_LOOKUP_KEYS)}')
    if not is_listed and given_unit_lookup_keys:
        raise RuntimeError(f'{error_start_text}: {list(CAMERA_ENTRY_UNIT_LOOKUP_KEYS)} only go '
                           f'with {CAMERA_ENTRY_SERIAL_KEY}: listed')
    # Part of a glob pattern over /dev/v4l/by-id: a plain name, no wildcards or path
    if v4l_by_id_prefix is not None:
        is_plain_name = isinstance(v4l_by_id_prefix, str) and FILE_NAME_PART_PATTERN.fullmatch(
            v4l_by_id_prefix)
        if not is_plain_name:
            raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY} must be '
                               f'the start of the /dev/v4l/by-id names of the camera before the '
                               f'serial, e.g. usb-046d_Logitech_BRIO')
    if usb_vendor_id is not None:
        _check_usb_id(usb_vendor_id, CAMERA_ENTRY_USB_VENDOR_ID_KEY, "'1e10'", error_start_text)
        if usb_product_id is not None:
            _check_usb_id(usb_product_id, CAMERA_ENTRY_USB_PRODUCT_ID_KEY, "'097c'",
                          error_start_text)
    else:
        for usb_only_key in (CAMERA_ENTRY_USB_SERIAL_BASE_KEY, CAMERA_ENTRY_USB_PRODUCT_ID_KEY):
            if usb_only_key in entry:
                raise RuntimeError(f'{error_start_text}: {usb_only_key} only goes with '
                                   f'{CAMERA_ENTRY_USB_VENDOR_ID_KEY}')
    if usb_serial_base not in USB_SERIAL_BASES:
        raise RuntimeError(f'{error_start_text}: {CAMERA_ENTRY_USB_SERIAL_BASE_KEY} must be one '
                           f'of {list(USB_SERIAL_BASES)}')
    return {CAMERA_ENTRY_SERIAL_KEY: serial_source,
            CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY: v4l_by_id_prefix,
            CAMERA_ENTRY_USB_VENDOR_ID_KEY: usb_vendor_id,
            CAMERA_ENTRY_USB_PRODUCT_ID_KEY: usb_product_id,
            CAMERA_ENTRY_USB_SERIAL_BASE_KEY: usb_serial_base}


def _check_usb_id(usb_id, entry_key, example_text, error_start_text):
    """Raise RuntimeError naming the fix unless usb_id is 4 lower case hexadecimal digits."""
    is_usb_id = isinstance(usb_id, str) and USB_ID_PATTERN.fullmatch(usb_id)
    if not is_usb_id:
        raise RuntimeError(f'{error_start_text}: {entry_key} must be 4 lower case hexadecimal '
                           f'digits as text, as lsusb shows it, e.g. {example_text}')


def get_camera_launch_file_path(camera_type, camera_entry):
    """
    Return the installed launch file a camera type's entry names.

    Raises RuntimeError naming the fix when the file is not installed.
    """
    launch_file_path = os.path.join(get_package_share_directory(camera_entry['package']),
                                    'launch', camera_entry['launch_file'])
    if not os.path.isfile(launch_file_path):
        raise RuntimeError(f'[camera_types]: the camera type {camera_type} names the launch file '
                           f'{launch_file_path}, which is not installed: install launch/ in the '
                           f'setup.py data_files of {camera_entry["package"]} '
                           f'({CAMERA_ENTRY_FORMAT_DOCUMENTATION_TEXT}) and run '
                           f'./scripts/local_build.sh')
    return launch_file_path


def get_camera_type_params_file_paths(camera_entry):
    """
    Return the camera type's default parameter file as a list: one path, or none without one.

    Raises RuntimeError naming the fix when the entry names a file that is not installed.
    """
    parameters_file_relative_path = camera_entry[CAMERA_ENTRY_PARAMETERS_FILE_KEY]
    if parameters_file_relative_path is None:
        return []
    package_share_path = get_package_share_directory(camera_entry['package'])
    parameters_file_path = os.path.join(package_share_path, parameters_file_relative_path)
    if not os.path.isfile(parameters_file_path):
        raise RuntimeError(f'[camera_types]: the camera entry names {parameters_file_path} as '
                           f'{CAMERA_ENTRY_PARAMETERS_FILE_KEY}, which is not installed: install '
                           f'it in the setup.py data_files of {camera_entry["package"]} and run '
                           f'./scripts/local_build.sh')
    return [parameters_file_path]


def get_camera_body_frame_id(camera_name, camera_entry):
    """Return the camera's body frame, the child of its mount transform: <name>_<body_frame>."""
    return f'{camera_name}_{camera_entry[CAMERA_ENTRY_BODY_FRAME_KEY]}'
