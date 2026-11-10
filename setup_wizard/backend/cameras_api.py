# Written by Claude Code
"""
Cameras API of the setup wizard backend: the camera types installed and their connected units.

The camera types are those registered in the ament index (launch_helpers.CAMERA_RESOURCE_TYPE),
each described by its entry, so any camera package following templates/par_camera/ appears here
without code in the wizard. A type counts as installed when every package of its entry's
required_packages is, the same check par.launch.py uses for optional nodes.
"""

import glob
import os

from ament_index_python.resources import has_resource
from fastapi import APIRouter, HTTPException
from par_framework_core.launch_helpers import (CAMERA_ENTRY_INTRINSICS_KEY,
                                               CAMERA_ENTRY_REQUIRED_PACKAGES_KEY,
                                               CAMERA_ENTRY_SERIAL_KEY,
                                               CAMERA_ENTRY_STREAMS_KEY,
                                               CAMERA_ENTRY_USB_SERIAL_BASE_KEY,
                                               CAMERA_ENTRY_USB_VENDOR_ID_KEY,
                                               CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY,
                                               CAMERA_SERIAL_SOURCE_LISTED,
                                               FILE_NAME_PART_PATTERN, get_camera_type_names,
                                               read_camera_entry)
from pydantic import BaseModel

# serial: listed with v4l_by_id_prefix: the connected units are
# /dev/v4l/by-id/<prefix>_<serial>-video-index0, the names UVC drivers match a serial against
V4L_BY_ID_FOLDER_PATH = '/dev/v4l/by-id'
V4L_BY_ID_CAPTURE_SUFFIX = '-video-index0'
# serial: listed with usb_vendor_id: Linux lists each USB device's vendor id and serial text here
USB_DEVICES_FOLDER_PATH = '/sys/bus/usb/devices'

cameras_router = APIRouter()


class CameraType(BaseModel):
    # The camera type, the entry's file name, as in par_launch.cameras and camera:=
    camera_type: str
    display_name: str = ''
    description: str = ''
    required_package_names: list[str] = []
    # True when every package of required_package_names is installed
    is_installed: bool = False
    # The entry's serial: none, typed or listed
    serial_source: str = 'none'
    # The entry's intrinsics: calibratable, factory or none
    intrinsics_source: str = 'none'
    # The streams the camera offers below its namespace, e.g. depth_registered/image_raw
    stream_names: list[str] = []
    # Set when the entry cannot be read; the type cannot be used then
    entry_error_text: str | None = None


class CameraTypeListResponse(BaseModel):
    camera_types: list[CameraType]


@cameras_router.get('/api/cameras')
def get_camera_type_list() -> CameraTypeListResponse:
    """List every installed camera type with its entry and whether its packages are installed."""
    camera_types = []
    for camera_type in get_camera_type_names():
        try:
            camera_entry = read_camera_entry(camera_type)
        except RuntimeError as error:
            # One broken entry must not hide the other camera types
            camera_types.append(CameraType(camera_type=camera_type, entry_error_text=str(error)))
            continue
        required_package_names = camera_entry[CAMERA_ENTRY_REQUIRED_PACKAGES_KEY]
        is_installed = True
        for required_package_name in required_package_names:
            if not has_resource('packages', required_package_name):
                is_installed = False
        camera_types.append(CameraType(
            camera_type=camera_type,
            display_name=camera_entry['display_name'],
            description=camera_entry['description'],
            required_package_names=required_package_names,
            is_installed=is_installed,
            serial_source=camera_entry[CAMERA_ENTRY_SERIAL_KEY],
            intrinsics_source=camera_entry[CAMERA_ENTRY_INTRINSICS_KEY],
            stream_names=camera_entry[CAMERA_ENTRY_STREAMS_KEY]))
    return CameraTypeListResponse(camera_types=camera_types)


def read_installed_camera_entry(camera_type: str) -> dict:
    """Return the entry of an installed, startable camera type; 404, 409 or 422 when it is not."""
    for camera_type_summary in get_camera_type_list().camera_types:
        if camera_type_summary.camera_type != camera_type:
            continue
        if camera_type_summary.entry_error_text is not None:
            raise HTTPException(status_code=409, detail=camera_type_summary.entry_error_text)
        if not camera_type_summary.is_installed:
            required_package_names_text = ', '.join(camera_type_summary.required_package_names)
            raise HTTPException(status_code=409,
                                detail=f'The driver of {camera_type} is not installed '
                                       f'({required_package_names_text}): add it to '
                                       f'config/ros_packages.list and run '
                                       f'./scripts/local_build.sh')
        return read_camera_entry(camera_type)
    raise HTTPException(status_code=404, detail=f'No camera type {camera_type!r} is installed')


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
        serials = _find_usb_serials(usb_vendor_id, camera_entry[CAMERA_ENTRY_USB_SERIAL_BASE_KEY])
    else:
        serials = _find_v4l_by_id_serials(camera_entry[CAMERA_ENTRY_V4L_BY_ID_PREFIX_KEY])
    return ConnectedCameraUnitsResponse(serial_source=serial_source, serials=serials)


def _find_v4l_by_id_serials(name_prefix: str) -> list[str]:
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


def _find_usb_serials(usb_vendor_id: str, usb_serial_base: int) -> list[str]:
    """
    Return the serials of the connected USB devices of a vendor, sorted.

    usb_serial_base 16 converts a serial the device reports in hexadecimal to the decimal number
    its driver takes.
    """
    serials = []
    vendor_id_path_pattern = os.path.join(USB_DEVICES_FOLDER_PATH, '*', 'idVendor')
    for vendor_id_path in sorted(glob.glob(vendor_id_path_pattern)):
        serial_path = os.path.join(os.path.dirname(vendor_id_path), 'serial')
        try:
            with open(vendor_id_path) as vendor_id_file:
                device_vendor_id = vendor_id_file.read().strip()
            if device_vendor_id != usb_vendor_id:
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
