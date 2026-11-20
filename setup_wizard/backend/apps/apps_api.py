# Written by Claude Code
"""
Apps API of the setup wizard backend: the installed apps a profile can offer, most of them to
put on the projector, RViz to run next to that app, and which of them a profile offers, puts on the
projector and feeds from which camera (par_launch.apps, projector_app, app_inputs).

Every installed PAR app registers in the ament index under par_framework_apps (blueprint:
templates/par_app/), so a new app shows up here without a change to the wizard. Its entry is
read and checked by the same par_apps function par.launch.py starts it with. Their settings
are read and saved by node_settings_api.py. RViz is not a PAR app (it does not draw on the
projector): it is listed with uses_projector false and stored as par.launch.py's rviz switch.
"""

from ament_index_python.resources import has_resource
from fastapi import APIRouter, HTTPException
from par_framework_core.par_apps import (get_par_app_package_names, PAR_APP_ENTRY_INPUTS_KEY,
                                         PROJECTOR_APP_NONE, read_par_app_entry)
from par_framework_core.sensor_nodes import get_sensor_node_package_names, read_sensor_node_entry
from profiles.profile_files import (PAR_LAUNCH_NODE_NAME, read_camera_name_by_input_by_app,
                                    read_enabled_app_names, read_profile_cameras_or_raise,
                                    read_profile_launch_section, RVIZ_LAUNCH_SWITCH_NAME,
                                    write_app_inputs, write_node_settings_into_profile)
from pydantic import BaseModel

# Special case: RViz is no PAR app with an entry in the index, it is par.launch.py's switch rviz
# (rviz2 with the framework's configuration, and rviz_bridge). Its app name is that switch,
# profile_files.RVIZ_LAUNCH_SWITCH_NAME.
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
    # The display names of the sensor nodes among them, which run on the cameras the app reads
    required_sensor_node_display_names: list[str] = []
    # par_apps.PAR_APP_CALIBRATION_NAMES the app uses; it also starts without them
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


class ProjectorAppChoiceRequest(BaseModel):
    # par_launch.projector_app: none, or one of the profile's apps (par_launch.apps)
    app_name: str


class EnabledAppsRequest(BaseModel):
    # par_launch.apps: app_names of installed apps from GET /api/apps
    app_names: list[str]


class AppInputsRequest(BaseModel):
    # One of the profile's apps (par_launch.apps)
    app_name: str
    # Camera name per input of the app's entry; an input left out reads the only camera of a run
    camera_name_by_input: dict[str, str]


@apps_router.get('/api/apps')
def get_installed_app_list() -> InstalledAppListResponse:
    """List the installed apps: those that can own the projector, and RViz."""
    return InstalledAppListResponse(installed_apps=_read_installed_app_summaries())


def _read_installed_app_summaries() -> list[InstalledAppSummary]:
    """Return the installed apps: those that can own the projector, and RViz."""
    # Simplification: the index is searched along AMENT_PREFIX_PATH as it was when the backend
    # started, and colcon gives every package its own prefix, so an app built for the first time
    # appears after a backend restart. Upgrade: re-read install/setup.bash's prefixes per request.
    installed_apps = []
    for app_package_name in get_par_app_package_names():
        installed_apps.append(_read_installed_app_summary(app_package_name))
    is_rviz_installed = all(
        has_resource('packages', rviz_package_name) for rviz_package_name in RVIZ_PACKAGE_NAMES)
    if is_rviz_installed:
        installed_apps.append(InstalledAppSummary(
            app_name=RVIZ_LAUNCH_SWITCH_NAME,
            display_name=RVIZ_DISPLAY_NAME,
            description=RVIZ_DESCRIPTION,
            uses_projector=False,
            required_launch_switch_names=[],
            used_calibration_names=[]))
    return installed_apps


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
        required_sensor_node_display_names=_get_sensor_node_display_names(
            par_app_entry['required_launch_switches']),
        used_calibration_names=par_app_entry['used_calibrations'],
        settings_node_names=par_app_entry['settings_node_names'],
        input_names=list(par_app_entry[PAR_APP_ENTRY_INPUTS_KEY]))


@apps_router.put('/api/profiles/{profile_name}/projector-app')
def set_projector_app(profile_name: str, request: ProjectorAppChoiceRequest) -> None:
    """Store which of the profile's apps it puts on the projector (par_launch.projector_app)."""
    launch_section = read_profile_launch_section(profile_name)
    if request.app_name == RVIZ_LAUNCH_SWITCH_NAME:
        raise HTTPException(status_code=422,
                            detail='RViz does not draw on the projector; it runs next to the '
                                   'app on the projector')
    if request.app_name != PROJECTOR_APP_NONE:
        if request.app_name not in read_enabled_app_names(launch_section):
            raise HTTPException(status_code=422,
                                detail=f'{request.app_name} is not one of the profile\'s apps; '
                                       f'add it under Apps first')
        _check_startable_app(request.app_name)
    # As the sensor node switches: none is par_setup.yaml's value, so choosing it removes the key
    write_node_settings_into_profile(profile_name, PAR_LAUNCH_NODE_NAME,
                                     {'projector_app': request.app_name})


@apps_router.put('/api/profiles/{profile_name}/apps')
def set_enabled_apps(profile_name: str, request: EnabledAppsRequest) -> None:
    """
    Store which installed apps the profile offers (par_launch.apps), keeping their order.

    RViz is stored as the switch par_launch.rviz instead, which par.launch.py starts it by.
    """
    launch_section = read_profile_launch_section(profile_name)
    enabled_app_names = []
    is_rviz_enabled = False
    for app_name in request.app_names:
        if app_name in enabled_app_names:
            continue
        _check_startable_app(app_name)
        if app_name == RVIZ_LAUNCH_SWITCH_NAME:
            is_rviz_enabled = True
            continue
        enabled_app_names.append(app_name)
    setting_value_by_name = {'apps': enabled_app_names, RVIZ_LAUNCH_SWITCH_NAME: is_rviz_enabled}
    # The projector app is always one of the profile's apps
    if str(launch_section.get('projector_app', PROJECTOR_APP_NONE)) not in enabled_app_names:
        setting_value_by_name['projector_app'] = PROJECTOR_APP_NONE
    write_node_settings_into_profile(profile_name, PAR_LAUNCH_NODE_NAME, setting_value_by_name)


@apps_router.put('/api/profiles/{profile_name}/app-inputs')
def set_app_inputs(profile_name: str, request: AppInputsRequest) -> None:
    """Store which camera each input of one of the profile's apps reads (par_launch.app_inputs)."""
    launch_section = read_profile_launch_section(profile_name)
    if request.app_name not in read_enabled_app_names(launch_section):
        raise HTTPException(status_code=422,
                            detail=f"{request.app_name} is not one of the profile's apps; add it "
                                   f'under Apps first')
    _check_startable_app(request.app_name)
    app_input_names = list(read_par_app_entry(request.app_name)[PAR_APP_ENTRY_INPUTS_KEY])
    unknown_input_names = sorted(set(request.camera_name_by_input) - set(app_input_names))
    if unknown_input_names:
        raise HTTPException(status_code=422,
                            detail=f'{request.app_name} has no inputs {unknown_input_names}; its '
                                   f'inputs: {app_input_names}')
    profile_camera_names = []
    for profile_camera in read_profile_cameras_or_raise(profile_name):
        profile_camera_names.append(profile_camera.camera_name)
    unknown_camera_names = sorted(set(request.camera_name_by_input.values())
                                  - set(profile_camera_names))
    if unknown_camera_names:
        raise HTTPException(status_code=422,
                            detail=f'{unknown_camera_names} are no cameras of the profile; its '
                                   f'cameras: {profile_camera_names}')
    camera_name_by_input_by_app = read_camera_name_by_input_by_app(launch_section)
    camera_name_by_input_by_app[request.app_name] = dict(request.camera_name_by_input)
    write_app_inputs(profile_name, camera_name_by_input_by_app)


def _check_startable_app(app_name: str) -> None:
    """Raise 422 for no installed app, 409 for one whose entry par.launch.py would refuse."""
    for installed_app in _read_installed_app_summaries():
        if installed_app.app_name != app_name:
            continue
        if installed_app.entry_error_text is not None:
            raise HTTPException(status_code=409, detail=installed_app.entry_error_text)
        return
    raise HTTPException(status_code=422,
                        detail=f'{app_name!r} is no installed app; choose one from GET /api/apps')


def _get_sensor_node_display_names(launch_switch_names: list[str]) -> list[str]:
    """Return the display names of the sensor nodes among the switches; others (rviz) are left out."""
    installed_sensor_node_names = get_sensor_node_package_names()
    display_names = []
    for launch_switch_name in launch_switch_names:
        if launch_switch_name not in installed_sensor_node_names:
            continue
        try:
            display_names.append(read_sensor_node_entry(launch_switch_name)['display_name'])
        except RuntimeError:
            # A broken entry shows under Sensor nodes with its error; its package name suffices
            display_names.append(launch_switch_name)
    return display_names
