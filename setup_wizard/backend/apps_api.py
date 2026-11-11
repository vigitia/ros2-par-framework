# Written by Claude Code
"""
Apps API of the setup wizard backend: the installed apps a profile can offer, most of them to
put on the projector, RViz to run next to that app.

Every installed PAR app registers in the ament index under par_framework_apps (blueprint:
templates/par_app/), so a new app shows up here without a change to the wizard. Its entry is
read and checked by the same launch_helpers function par.launch.py starts it with. Their settings
are read and saved by node_settings_api.py. RViz is not a PAR app (it does not draw on the
projector): it is listed with uses_projector false and stored as par.launch.py's rviz switch.
"""

from ament_index_python.resources import has_resource
from fastapi import APIRouter
from par_framework_core.launch_helpers import (get_par_app_package_names,
                                               PAR_APP_ENTRY_INPUTS_KEY, read_par_app_entry,
                                               RENDERING_MANAGER_APP_NAME)
import profiles_api
from pydantic import BaseModel

# Special case: the rendering manager has no entry in the index yet (no launch file of its own),
# so its card text lives here until it has one, and it counts as installed with its bridge.
RENDERING_MANAGER_BRIDGE_PACKAGE_NAME = 'rendering_manager_bridge'
RENDERING_MANAGER_DISPLAY_NAME = 'Rendering manager'
RENDERING_MANAGER_DESCRIPTION = ('Shows websites and desktop apps on the detected pages, one per '
                                 'page.')

# Special case: RViz is no PAR app with an entry in the index, it is par.launch.py's switch rviz
# (rviz2 with the framework's configuration, and rviz_bridge). Its app name is that switch,
# profiles_api.RVIZ_LAUNCH_SWITCH_NAME.
RVIZ_PACKAGE_NAMES = ('rviz2', 'rviz_bridge')
RVIZ_DISPLAY_NAME = 'RViz'
RVIZ_DESCRIPTION = ("Shows the setup in 3D on the PAR machine's desktop: the camera image, the "
                    'table and what the sensor nodes detect. Starts with every run of the '
                    'profile, next to the app on the projector.')

apps_router = APIRouter()


class InstalledAppSummary(BaseModel):
    # The value of par_launch.projector_app that starts the app: its package name. For an app
    # that does not use the projector, the par_launch switch that starts it
    app_name: str
    # False: runs next to the app on the projector instead of being chosen as that app
    uses_projector: bool = True
    display_name: str
    description: str
    # par_launch switches par.launch.py turns on for the app
    required_launch_switch_names: list[str]
    # launch_helpers.PAR_APP_CALIBRATION_NAMES the app uses; it also starts without them
    used_calibration_names: list[str]
    # The app's nodes whose settings the wizard edits (full node names); empty without any
    settings_node_names: list[str] = []
    # The inputs of the app's entry, each bound to one of the profile's cameras; empty for an app
    # that reads no camera
    input_names: list[str] = []
    # Set when the app's entry is malformed: par.launch.py would refuse to start it
    entry_error_text: str | None = None


class InstalledAppListResponse(BaseModel):
    installed_apps: list[InstalledAppSummary]


@apps_router.get('/api/apps')
def get_installed_app_list() -> InstalledAppListResponse:
    """List the installed apps: those that can own the projector, and RViz."""
    # Simplification: the index is searched along AMENT_PREFIX_PATH as it was when the backend
    # started, and colcon gives every package its own prefix, so an app built for the first time
    # appears after a backend restart. Upgrade: re-read install/setup.bash's prefixes per request.
    installed_apps = []
    if has_resource('packages', RENDERING_MANAGER_BRIDGE_PACKAGE_NAME):
        installed_apps.append(InstalledAppSummary(
            app_name=RENDERING_MANAGER_APP_NAME,
            display_name=RENDERING_MANAGER_DISPLAY_NAME,
            description=RENDERING_MANAGER_DESCRIPTION,
            required_launch_switch_names=[],
            used_calibration_names=[]))
    for app_package_name in get_par_app_package_names():
        installed_apps.append(_read_installed_app_summary(app_package_name))
    is_rviz_installed = all(
        has_resource('packages', rviz_package_name) for rviz_package_name in RVIZ_PACKAGE_NAMES)
    if is_rviz_installed:
        installed_apps.append(InstalledAppSummary(
            app_name=profiles_api.RVIZ_LAUNCH_SWITCH_NAME,
            display_name=RVIZ_DISPLAY_NAME,
            description=RVIZ_DESCRIPTION,
            uses_projector=False,
            required_launch_switch_names=[],
            used_calibration_names=[]))
    return InstalledAppListResponse(installed_apps=installed_apps)


def _read_installed_app_summary(app_package_name: str) -> InstalledAppSummary:
    try:
        par_app_entry = read_par_app_entry(app_package_name)
    except RuntimeError as error:
        # The entry comes from another repo: one broken app must not hide the others.
        return InstalledAppSummary(app_name=app_package_name, display_name=app_package_name,
                                   description='', required_launch_switch_names=[],
                                   used_calibration_names=[], entry_error_text=str(error))
    return InstalledAppSummary(
        app_name=app_package_name,
        display_name=par_app_entry['display_name'],
        description=par_app_entry['description'],
        required_launch_switch_names=par_app_entry['required_launch_switches'],
        used_calibration_names=par_app_entry['used_calibrations'],
        settings_node_names=par_app_entry['settings_node_names'],
        input_names=list(par_app_entry[PAR_APP_ENTRY_INPUTS_KEY]))
