# Written by Claude Code
"""
Cameras API of the setup wizard backend: the camera types installed, their connected units, and
the cameras a profile names.

The camera types and their entries come from camera_types.py. A connected unit's serial is read
the way its entry says (serial: listed). Adding a camera to a profile and removing one from it run
through profile_cameras.py, which also checks the cameras of a new profile.
"""

import glob
import os

from cameras.camera_types import CameraType, read_camera_types, read_installed_camera_entry
from fastapi import APIRouter
from par_framework_core.launch_helpers import (CAMERA_ENTRY_SERIAL_KEY,
                                               CAMERA_ENTRY_USB_PRODUCT_ID_KEY,
                                               CAMERA_ENTRY_USB_SERIAL_BASE_KEY,
                                               CAMERA_ENTRY_USB_VENDOR_ID_KEY,
                                               CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY,
                                               CAMERA_SERIAL_SOURCE_LISTED,
                                               FILE_NAME_PART_PATTERN)
from profiles.profile_cameras import (check_new_camera, NewCameraRequest,
                                      remove_camera_from_profile, write_camera_placeholder_pose,
                                      write_profile_cameras)
from profiles.profile_files import (check_profile_exists, DeletedProfileResponse,
                                    read_profile_cameras_or_raise)
from pydantic import BaseModel

# serial: listed with v4l_by_id_prefix: the connected units are
# /dev/v4l/by-id/<prefix>_<serial>-video-index0, the names UVC drivers match a serial against
V4L_BY_ID_FOLDER_PATH = '/dev/v4l/by-id'
V4L_BY_ID_CAPTURE_SUFFIX = '-video-index0'
# serial: listed with usb_vendor_id: Linux lists each USB device's vendor id, product id and
# serial text here
USB_DEVICES_FOLDER_PATH = '/sys/bus/usb/devices'

cameras_router = APIRouter()


class CameraTypeListResponse(BaseModel):
    camera_types: list[CameraType]


@cameras_router.get('/api/cameras')
def get_camera_type_list() -> CameraTypeListResponse:
    """List every installed camera type with its entry and whether its packages are installed."""
    return CameraTypeListResponse(camera_types=read_camera_types())


class ConnectedCameraUnitsResponse(BaseModel):
    # The entry's serial: none (one unit per setup), typed or listed
    serial_source: str
    # The connected units' serials; only filled for serial_source listed
    serials: list[str]


@cameras_router.get('/api/cameras/{camera_type}/units')
def get_connected_camera_units(camera_type: str) -> ConnectedCameraUnitsResponse:
    """List the serials of the connected units of a camera type whose entry says how."""
    camera_entry = read_installed_camera_entry(camera_type)
    serial_source = camera_entry[CAMERA_ENTRY_SERIAL_KEY]
    if serial_source != CAMERA_SERIAL_SOURCE_LISTED:
        return ConnectedCameraUnitsResponse(serial_source=serial_source, serials=[])
    usb_vendor_id = camera_entry[CAMERA_ENTRY_USB_VENDOR_ID_KEY]
    if usb_vendor_id is not None:
        serials = _read_usb_serials(usb_vendor_id, camera_entry[CAMERA_ENTRY_USB_PRODUCT_ID_KEY],
                                    camera_entry[CAMERA_ENTRY_USB_SERIAL_BASE_KEY])
    else:
        serials = _read_v4l_by_id_serials(camera_entry[CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY])
    return ConnectedCameraUnitsResponse(serial_source=serial_source, serials=serials)


@cameras_router.post('/api/profiles/{profile_name}/cameras')
def add_camera(profile_name: str, request: NewCameraRequest) -> None:
    """Add a named camera to the profile's par_launch.cameras; every run starts it."""
    check_profile_exists(profile_name)
    profile_cameras = read_profile_cameras_or_raise(profile_name)
    new_camera = check_new_camera(profile_cameras, request.camera_name, request.camera_type,
                                  request.serial)
    write_camera_placeholder_pose(profile_name, new_camera)
    write_profile_cameras(profile_name, [*profile_cameras, new_camera])


@cameras_router.delete('/api/profiles/{profile_name}/cameras/{camera_name}')
def remove_camera(profile_name: str, camera_name: str) -> DeletedProfileResponse:
    """
    Remove a camera from the profile; its calibrations move to config/profiles/.deleted/.

    Its node sections (/cameras/<camera name>/...) move there too, into
    DELETED_NODE_SECTIONS_FILE_NAME, so a new camera of the same name starts with the defaults.
    """
    check_profile_exists(profile_name)
    deleted_folder_path = remove_camera_from_profile(profile_name, camera_name)
    return DeletedProfileResponse(deleted_profile_folder_path=deleted_folder_path)


def _read_v4l_by_id_serials(name_prefix: str) -> list[str]:
    """Return the serials in /dev/v4l/by-id/<name_prefix>_<serial>-video-index0, sorted."""
    serials = []
    entry_pattern = os.path.join(V4L_BY_ID_FOLDER_PATH,
                                 f'{name_prefix}*{V4L_BY_ID_CAPTURE_SUFFIX}')
    for entry_path in sorted(glob.glob(entry_pattern)):
        entry_name = os.path.basename(entry_path)
        serial = entry_name.removeprefix(name_prefix).removesuffix(V4L_BY_ID_CAPTURE_SUFFIX)
        serial = serial.lstrip('_')
        # Only what profile and file names accept
        if serial and FILE_NAME_PART_PATTERN.fullmatch(serial):
            serials.append(serial)
    return serials


def _read_usb_serials(usb_vendor_id: str, usb_product_id: str | None,
                      usb_serial_base: int) -> list[str]:
    """
    Return the serials of the connected USB devices of a vendor, sorted.

    usb_product_id, when given, takes only that product's devices.
    usb_serial_base 16 converts a serial the device reports in hexadecimal to the decimal number
    its driver takes.
    """
    serials = []
    vendor_id_path_pattern = os.path.join(USB_DEVICES_FOLDER_PATH, '*', 'idVendor')
    for vendor_id_path in sorted(glob.glob(vendor_id_path_pattern)):
        device_folder_path = os.path.dirname(vendor_id_path)
        product_id_path = os.path.join(device_folder_path, 'idProduct')
        serial_path = os.path.join(device_folder_path, 'serial')
        try:
            with open(vendor_id_path) as vendor_id_file:
                device_vendor_id = vendor_id_file.read().strip()
            if device_vendor_id != usb_vendor_id:
                continue
            if usb_product_id is not None:
                with open(product_id_path) as product_id_file:
                    device_product_id = product_id_file.read().strip()
                if device_product_id != usb_product_id:
                    continue
            with open(serial_path) as serial_file:
                reported_serial = serial_file.read().strip()
            if usb_serial_base == 16:
                serial = str(int(reported_serial, 16))
            else:
                serial = reported_serial
        except (OSError, ValueError):
            # Unplugged meanwhile, or a device without a serial number: not a unit to offer
            continue
        # Only what profile and file names accept
        if serial and FILE_NAME_PART_PATTERN.fullmatch(serial):
            serials.append(serial)
    return sorted(serials)
