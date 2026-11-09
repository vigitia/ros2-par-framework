# Written by Claude Code
"""
Cameras API of the setup wizard backend: which cameras the framework supports and which are usable.

A camera counts as available when every ROS package its driver start needs is installed in the
sourced workspace or system, the same check par.launch.py uses for optional nodes.
"""

import glob
import os

from ament_index_python.resources import has_resource
from fastapi import APIRouter, HTTPException
from par_framework_core.launch_helpers import (CAMERA_DRIVER_REMAPPINGS,
                                               CAMERA_SERIAL_SOURCE_BY_CAMERA,
                                               FILE_NAME_PART_PATTERN)
from pydantic import BaseModel

# The ROS packages each camera's start in launch_helpers.create_camera_nodes runs (the
# Node(package=...) in its create_*_node functions), without tf2_ros, which every ROS installation
# has.
# Simplification: this copies knowledge of those functions. Upgrade: launch_helpers lists the
# driver packages per camera, used by them and by this backend.
DRIVER_PACKAGE_NAMES_BY_CAMERA = {
    'brio': ('logitech_brio',),
    'kinect': ('azure_kinect_ros_driver',),
    'realsense': ('realsense2_camera',),
    'webcam': ('v4l2_camera',),
    'blackfly': ('spinnaker_camera_driver',),
    'cu40': ('see3cam_cu40',),
    'event': ('metavision_driver', 'event_camera_renderer'),
}

# The cameras whose connected units are told apart by their /dev/v4l/by-id entry, the same entry
# their driver matches the serial parameter against (find_brio_camera_id, find_cu40_device_path):
# the part of the name after the product name is the serial.
# Simplification: the Blackfly needs Spinnaker's enumeration, so its serial is typed by hand.
# Upgrade: list its units through the driver's package.
V4L_BY_ID_PREFIX_BY_CAMERA = {
    'brio': 'usb-046d_Logitech_BRIO',
    'cu40': 'usb-e-con_systems_See3CAM_CU40',
}
V4L_BY_ID_FOLDER_PATH = '/dev/v4l/by-id'
V4L_BY_ID_CAPTURE_SUFFIX = '-video-index0'

cameras_router = APIRouter()


class SupportedCamera(BaseModel):
    # A key of launch_helpers.CAMERA_DRIVER_REMAPPINGS, as used in par_launch.camera and camera:=.
    camera_name: str
    driver_package_names: list[str]
    # True when every package of driver_package_names is installed.
    is_installed: bool


class CameraListResponse(BaseModel):
    cameras: list[SupportedCamera]


@cameras_router.get('/api/cameras')
def get_camera_list() -> CameraListResponse:
    """List every camera the framework supports, with whether its driver packages are installed."""
    cameras = []
    for camera_name in CAMERA_DRIVER_REMAPPINGS:
        # A camera added to launch_helpers but not here counts as not installed instead of failing.
        driver_package_names = DRIVER_PACKAGE_NAMES_BY_CAMERA.get(camera_name, ())
        is_installed = len(driver_package_names) > 0
        for driver_package_name in driver_package_names:
            if not has_resource('packages', driver_package_name):
                is_installed = False
        cameras.append(SupportedCamera(camera_name=camera_name,
                                       driver_package_names=list(driver_package_names),
                                       is_installed=is_installed))
    return CameraListResponse(cameras=cameras)


class ConnectedCameraUnitsResponse(BaseModel):
    # True for a camera type that has serials: several units of it can be in one profile
    is_serial_supported: bool = True
    # False when the backend cannot list this camera's units: the serial is typed by hand
    is_listing_supported: bool
    serials: list[str]


@cameras_router.get('/api/cameras/{camera_name}/units')
def get_connected_camera_units(camera_name: str) -> ConnectedCameraUnitsResponse:
    """List the serials of the connected units of a camera type that has serials."""
    if camera_name not in CAMERA_DRIVER_REMAPPINGS:
        raise HTTPException(status_code=404, detail=f'Unknown camera {camera_name!r}')
    if camera_name not in CAMERA_SERIAL_SOURCE_BY_CAMERA:
        return ConnectedCameraUnitsResponse(is_serial_supported=False, is_listing_supported=False,
                                            serials=[])
    name_prefix = V4L_BY_ID_PREFIX_BY_CAMERA.get(camera_name)
    if name_prefix is None:
        return ConnectedCameraUnitsResponse(is_listing_supported=False, serials=[])
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
    return ConnectedCameraUnitsResponse(is_listing_supported=True, serials=serials)
