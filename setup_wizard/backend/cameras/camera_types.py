# Written by Claude Code
"""
Camera types for the setup wizard backend: the installed camera types and their entries.

The camera types are those registered in the ament index (launch_helpers.CAMERA_RESOURCE_TYPE),
each described by its entry, so any camera package following templates/par_camera/ appears here
without code in the wizard. A type counts as installed when every package of its entry's
required_packages is, the same check par.launch.py uses for optional nodes. Read by the cameras
API (cameras_api.py) and by everything that starts or adds a camera (camera_launch_session.py,
profile_cameras.py).
"""

from ament_index_python.resources import has_resource
from fastapi import HTTPException
from par_framework_core.launch_helpers import (CAMERA_ENTRY_INTRINSICS_KEY,
                                               CAMERA_ENTRY_REQUIRED_PACKAGES_KEY,
                                               CAMERA_ENTRY_SERIAL_KEY,
                                               CAMERA_INTRINSICS_SOURCE_NONE,
                                               CAMERA_SERIAL_SOURCE_NONE, get_camera_type_names,
                                               read_camera_entry)
from pydantic import BaseModel


class CameraType(BaseModel):
    # The camera type, the entry's file name, as in par_launch.cameras and camera:=
    camera_type: str
    display_name: str = ''
    description: str = ''
    required_package_names: list[str] = []
    # True when every package of required_package_names is installed
    is_installed: bool = False
    # The entry's serial: none, typed or listed
    serial_source: str = CAMERA_SERIAL_SOURCE_NONE
    # The entry's intrinsics: calibratable, factory or none
    intrinsics_source: str = CAMERA_INTRINSICS_SOURCE_NONE
    # Set when the entry cannot be read; the type cannot be used then
    entry_error_text: str | None = None


def read_camera_types() -> list[CameraType]:
    """Return every camera type in the index with its entry and whether it is installed."""
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
            intrinsics_source=camera_entry[CAMERA_ENTRY_INTRINSICS_KEY]))
    return camera_types


def read_installed_camera_entry(camera_type: str) -> dict:
    """Return the entry of an installed, startable camera type; 404, 409 or 422 when it is not."""
    for camera_type_summary in read_camera_types():
        if camera_type_summary.camera_type != camera_type:
            continue
        if camera_type_summary.entry_error_text is not None:
            raise HTTPException(status_code=409, detail=camera_type_summary.entry_error_text)
        if not camera_type_summary.is_installed:
            required_package_names_text = ', '.join(camera_type_summary.required_package_names)
            raise HTTPException(status_code=409,
                                detail=f'The driver of {camera_type} is not installed '
                                       f'({required_package_names_text}): add a released '
                                       f'driver to config/installed_ros_packages.list, a driver '
                                       f'from config/catalog_repos.list to '
                                       f'config/installed_repos.list, and run '
                                       f'./scripts/local_build.sh')
        return read_camera_entry(camera_type)
    raise HTTPException(status_code=404, detail=f'No camera type {camera_type!r} is installed')
