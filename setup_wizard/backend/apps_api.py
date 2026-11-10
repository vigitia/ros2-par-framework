# Written by Claude Code
"""
Apps API of the setup wizard backend: the installed apps a profile can offer and put on the
projector.

Every installed PAR app registers in the ament index under par_framework_apps (blueprint:
templates/par_app/), so a new app shows up here without a change to the wizard. Its entry is
read and checked by the same launch_helpers function par.launch.py starts it with. Their settings
are read and saved by node_settings_api.py.
"""

from ament_index_python.resources import has_resource
from fastapi import APIRouter
from par_framework_core.launch_helpers import (get_par_app_package_names, read_par_app_entry,
                                               RENDERING_MANAGER_APP_NAME)
from pydantic import BaseModel

# Special case: the rendering manager has no entry in the index yet (no launch file of its own),
# so its card text lives here until it has one, and it counts as installed with its bridge.
RENDERING_MANAGER_BRIDGE_PACKAGE_NAME = 'rendering_manager_bridge'
RENDERING_MANAGER_DISPLAY_NAME = 'Rendering manager'
RENDERING_MANAGER_DESCRIPTION = ('Shows websites and desktop apps on the detected pages, one per '
                                 'page.')

apps_router = APIRouter()


class ProjectorAppSummary(BaseModel):
    # The value of par_launch.projector_app that starts the app: its package name
    app_name: str
    display_name: str
    description: str
    # par_launch switches par.launch.py turns on for the app
    required_launch_switch_names: list[str]
    # launch_helpers.PAR_APP_CALIBRATION_NAMES the app uses; it also starts without them
    used_calibration_names: list[str]
    # The app's nodes whose settings the wizard edits (full node names); empty without any
    settings_node_names: list[str] = []
    # Set when the app's entry is malformed: par.launch.py would refuse to start it
    entry_error_text: str | None = None


class ProjectorAppListResponse(BaseModel):
    projector_apps: list[ProjectorAppSummary]


@apps_router.get('/api/apps')
def get_projector_app_list() -> ProjectorAppListResponse:
    """List the installed apps that can own the projector, named as par_launch.projector_app."""
    # Simplification: the index is searched along AMENT_PREFIX_PATH as it was when the backend
    # started, and colcon gives every package its own prefix, so an app built for the first time
    # appears after a backend restart. Upgrade: re-read install/setup.bash's prefixes per request.
    projector_apps = []
    if has_resource('packages', RENDERING_MANAGER_BRIDGE_PACKAGE_NAME):
        projector_apps.append(ProjectorAppSummary(
            app_name=RENDERING_MANAGER_APP_NAME,
            display_name=RENDERING_MANAGER_DISPLAY_NAME,
            description=RENDERING_MANAGER_DESCRIPTION,
            required_launch_switch_names=[],
            used_calibration_names=[]))
    for app_package_name in get_par_app_package_names():
        projector_apps.append(_read_projector_app_summary(app_package_name))
    return ProjectorAppListResponse(projector_apps=projector_apps)


def _read_projector_app_summary(app_package_name: str) -> ProjectorAppSummary:
    try:
        par_app_entry = read_par_app_entry(app_package_name)
    except RuntimeError as error:
        # The entry comes from another repo: one broken app must not hide the others.
        return ProjectorAppSummary(app_name=app_package_name, display_name=app_package_name,
                                   description='', required_launch_switch_names=[],
                                   used_calibration_names=[], entry_error_text=str(error))
    return ProjectorAppSummary(
        app_name=app_package_name,
        display_name=par_app_entry['display_name'],
        description=par_app_entry['description'],
        required_launch_switch_names=par_app_entry['required_launch_switches'],
        used_calibration_names=par_app_entry['used_calibrations'],
        settings_node_names=par_app_entry['settings_node_names'])
