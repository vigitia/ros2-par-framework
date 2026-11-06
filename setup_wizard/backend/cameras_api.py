# Written by Claude Code
"""
Cameras API of the setup wizard backend: which cameras the framework supports and which are usable.

A camera counts as available when every ROS package its driver start needs is installed in the
sourced workspace or system, the same check par.launch.py uses for optional nodes.
"""

from ament_index_python.resources import has_resource
from fastapi import APIRouter
from par_framework_core.launch_helpers import CAMERA_DRIVER_REMAPPINGS
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
