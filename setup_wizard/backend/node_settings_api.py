# Written by Claude Code
"""
Node settings API of the setup wizard backend: the settings of sensor nodes and apps, read once.

A ROS 2 node declares its parameters (name, type, range, description) in code when it starts;
no file lists them. So the backend starts the node once on its own, without camera, profile or
the rest of the framework, reads its parameters through the standard parameter services, stops
it again and caches what it reported per installed package. Editing then needs no running node:
the shown values are the profile's where it sets them, else the cached ones (par_setup.yaml's or
the node's own defaults), and saving writes the changes into the profile, converted to the cached
types, which the node reads at its next start.

Which nodes: a sensor node is started as par.launch.py starts it (executable = package, node name
<package>_node); an app as its ament index entry says (executable or launch_file), and its
settings nodes are the ones the entry names in settings_node_names. Node names from the network
must be one of these, since they reach parameter clients and launch arguments.
"""

from dataclasses import dataclass
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time

from ament_index_python.packages import get_package_share_directory
import camera_preview_api
from fastapi import APIRouter, HTTPException
from par_framework_core.launch_helpers import (get_par_app_package_names,
                                               get_sensor_node_package_names, read_par_app_entry)
from process_groups import LAUNCH_STOP_SIGNALS, stop_process_group
import profiles_api
from pydantic import BaseModel
from rclpy.parameter import Parameter
import run_api

NODE_KIND_SENSOR_NODE = 'sensor_node'
NODE_KIND_APP = 'app'
# par.launch.py names each sensor node <package>_node, without a namespace
SENSOR_NODE_NAME_SUFFIX = '_node'
# How long a node may take to start and answer before the read counts as failed
SETTINGS_READ_TIMEOUT_S = 20.0
SETTINGS_READ_POLL_INTERVAL_S = 0.5
SETTINGS_READ_STOP_TIMEOUT_S = 10.0
SETTINGS_READ_LOG_TAIL_LINE_COUNT = 8
SETTINGS_CACHE_FOLDER_PATH = os.path.join(os.path.expanduser('~'), '.cache', 'par_setup_wizard',
                                          'node_settings')
PARAMETER_TYPE_BY_TYPE_NAME = {
    type_name: Parameter.Type(parameter_type)
    for parameter_type, type_name in camera_preview_api.TYPE_NAME_BY_PARAMETER_TYPE.items()}

node_settings_router = APIRouter()

# Reads that run or failed, by (node kind, package); a finished read is in the cache file
_settings_read_by_key = {}
_settings_reads_lock = threading.Lock()


@dataclass
class _SettingsRead:
    # Set when the read failed: why, for the user; None while it runs
    error_text: str | None = None
    is_running: bool = True


class NodeSettingsResponse(BaseModel):
    full_node_name: str
    # With the profile's values
    settings: list[camera_preview_api.NodeSetting]


class NodeSettingsSaveRequest(BaseModel):
    profile_name: str
    # NODE_KIND_SENSOR_NODE or NODE_KIND_APP
    node_kind: str
    package_name: str
    full_node_name: str
    # None resets a setting to its default: the profile's key for it is removed
    setting_value_by_name: dict[str, bool | int | float | str | list | None]


class NodeSettingsSaveResponse(BaseModel):
    node_section_name: str
    written_setting_names: list[str]
    removed_setting_names: list[str]


class NodeSettingsRefreshRequest(BaseModel):
    node_kind: str
    package_name: str


@node_settings_router.get('/api/node-settings')
def get_node_settings(profile_name: str, node_kind: str, package_name: str,
                      full_node_name: str) -> NodeSettingsResponse:
    """
    Return the node's settings with the profile's values.

    503 while they are read for the first time (the node is started for it in the background),
    409 when reading failed, with the reason; Refresh tries again.
    """
    profiles_api.check_profile_exists(profile_name)
    _check_settings_node(node_kind, package_name, full_node_name)
    cached_settings_by_node_name = _read_cached_settings(node_kind, package_name)
    if cached_settings_by_node_name is None:
        _start_settings_read_unless_known(node_kind, package_name)
        with _settings_reads_lock:
            settings_read = _settings_read_by_key[(node_kind, package_name)]
            if settings_read.error_text is not None:
                raise HTTPException(status_code=409, detail=settings_read.error_text)
        raise HTTPException(status_code=503, detail=f'Reading the settings of {package_name}')
    if full_node_name not in cached_settings_by_node_name:
        raise HTTPException(status_code=409,
                            detail=f'{full_node_name} did not start when {package_name} was read; '
                                   f'check its name in the app entry, then Refresh')
    profile_value_by_name = profiles_api.read_profile_node_settings(profile_name, full_node_name)
    settings = []
    for cached_setting in cached_settings_by_node_name[full_node_name]:
        shown_setting = cached_setting.model_copy()
        # The value read without a profile is what the node uses when the profile sets nothing
        shown_setting.has_default_value = True
        shown_setting.default_value = cached_setting.setting_value
        if shown_setting.setting_name in profile_value_by_name:
            shown_setting.setting_value = profile_value_by_name[shown_setting.setting_name]
        settings.append(shown_setting)
    return NodeSettingsResponse(full_node_name=full_node_name, settings=settings)


@node_settings_router.post('/api/node-settings/save')
def save_node_settings(request: NodeSettingsSaveRequest) -> NodeSettingsSaveResponse:
    """Write the changed settings into the profile, in the types the node reported."""
    _check_settings_node(request.node_kind, request.package_name, request.full_node_name)
    if not request.setting_value_by_name:
        raise HTTPException(status_code=400, detail='No setting changed')
    cached_settings_by_node_name = _read_cached_settings(request.node_kind, request.package_name)
    if cached_settings_by_node_name is None:
        raise HTTPException(status_code=409, detail='The settings have not been read yet')
    type_name_by_setting_name = {}
    for cached_setting in cached_settings_by_node_name.get(request.full_node_name, []):
        type_name_by_setting_name[cached_setting.setting_name] = cached_setting.type_name
    converted_value_by_name = {}
    for setting_name, setting_value in request.setting_value_by_name.items():
        type_name = type_name_by_setting_name.get(setting_name)
        if type_name not in PARAMETER_TYPE_BY_TYPE_NAME:
            raise HTTPException(status_code=400,
                                detail=f'{request.full_node_name} has no setting {setting_name} '
                                       f'that can be saved')
        if setting_value is None:
            # Removed from the profile: the node uses par_setup.yaml's or its own default again
            converted_value_by_name[setting_name] = None
            continue
        converted_value_by_name[setting_name] = camera_preview_api.convert_setting_value(
            setting_value, PARAMETER_TYPE_BY_TYPE_NAME[type_name])
    write_result = profiles_api.write_node_settings_into_profile(
        request.profile_name, request.full_node_name, converted_value_by_name)
    return NodeSettingsSaveResponse(
        node_section_name=write_result.node_section_name,
        written_setting_names=write_result.written_setting_names,
        removed_setting_names=write_result.removed_setting_names)


@node_settings_router.post('/api/node-settings/refresh')
def refresh_node_settings(request: NodeSettingsRefreshRequest) -> None:
    """Forget what was read for the package, so the next request reads it again."""
    _get_settings_node_names(request.node_kind, request.package_name)
    with _settings_reads_lock:
        settings_read = _settings_read_by_key.get((request.node_kind, request.package_name))
        if settings_read is not None and settings_read.is_running:
            raise HTTPException(status_code=409, detail='The settings are being read right now')
        _settings_read_by_key.pop((request.node_kind, request.package_name), None)
        cache_file_path = _get_cache_file_path(request.node_kind, request.package_name)
        if os.path.exists(cache_file_path):
            os.remove(cache_file_path)


def _get_settings_node_names(node_kind, package_name):
    """Return the package's nodes with settings; 404 for an unknown kind or package."""
    if node_kind == NODE_KIND_SENSOR_NODE:
        if package_name not in get_sensor_node_package_names():
            raise HTTPException(status_code=404,
                                detail=f'No installed sensor node {package_name!r}')
        return ['/' + package_name + SENSOR_NODE_NAME_SUFFIX]
    if node_kind == NODE_KIND_APP:
        return _read_par_app_entry_or_raise(package_name)['settings_node_names']
    raise HTTPException(status_code=404, detail=f'Unknown node kind {node_kind!r}')


def _read_par_app_entry_or_raise(package_name):
    if package_name not in get_par_app_package_names():
        raise HTTPException(status_code=404, detail=f'No installed app {package_name!r}')
    try:
        return read_par_app_entry(package_name)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def _check_settings_node(node_kind, package_name, full_node_name):
    if full_node_name not in _get_settings_node_names(node_kind, package_name):
        raise HTTPException(status_code=404,
                            detail=f'{full_node_name} is no settings node of {package_name}')


def _get_cache_file_path(node_kind, package_name):
    return os.path.join(SETTINGS_CACHE_FOLDER_PATH, f'{node_kind}_{package_name}.json')


def _get_installed_package_stamp(package_name):
    """Return when the package was installed last, so a rebuild invalidates the cache."""
    # Simplification: with colcon's --symlink-install, a Python node's code changes without a
    # new install, so a newly declared parameter shows only after Refresh. Upgrade: also compare
    # the modification times of the package's installed Python files.
    package_xml_path = os.path.join(get_package_share_directory(package_name), 'package.xml')
    return os.path.getmtime(package_xml_path)


def _read_cached_settings(node_kind, package_name):
    """Return {full node name: [NodeSetting]} from the cache, None when absent or outdated."""
    cache_file_path = _get_cache_file_path(node_kind, package_name)
    try:
        with open(cache_file_path) as cache_file:
            cache_document = json.load(cache_file)
    except (OSError, json.JSONDecodeError):
        return None
    if cache_document.get('installed_package_stamp') != _get_installed_package_stamp(package_name):
        return None
    cached_settings_by_node_name = {}
    for full_node_name, settings_json in cache_document['settings_by_node_name'].items():
        cached_settings_by_node_name[full_node_name] = [
            camera_preview_api.NodeSetting(**setting_json) for setting_json in settings_json]
    return cached_settings_by_node_name


def _start_settings_read_unless_known(node_kind, package_name):
    """Start reading in the background, unless a read runs or failed (then Refresh retries)."""
    with _settings_reads_lock:
        settings_read = _settings_read_by_key.get((node_kind, package_name))
        if settings_read is not None and (settings_read.is_running or settings_read.error_text):
            return
        _settings_read_by_key[(node_kind, package_name)] = _SettingsRead()
    threading.Thread(target=_read_settings_into_cache, args=(node_kind, package_name),
                     daemon=True).start()


def _read_settings_into_cache(node_kind, package_name):
    """Start the package's nodes alone, read their parameters, stop them, write the cache."""
    error_text = None
    try:
        _start_nodes_and_write_cache(node_kind, package_name)
    except HTTPException as error:
        error_text = str(error.detail)
    except (OSError, RuntimeError) as error:
        error_text = f'Reading the settings of {package_name} failed: {error}'
    with _settings_reads_lock:
        settings_read = _settings_read_by_key[(node_kind, package_name)]
        settings_read.is_running = False
        settings_read.error_text = error_text
        if error_text is None:
            # Done: the cache answers from now on
            del _settings_read_by_key[(node_kind, package_name)]


def _start_nodes_and_write_cache(node_kind, package_name):
    settings_node_names = _get_settings_node_names(node_kind, package_name)
    preview_session = camera_preview_api.get_camera_preview_session()
    preview_ros_node = preview_session.preview_ros_node
    # A node of the same name would answer with a profile's values, and the second one would
    # publish next to it. What this backend runs is known for sure; a launch from a terminal only
    # through the ROS graph, which a backend started a moment ago has not fully discovered yet.
    if _is_backend_launch_running(preview_session):
        raise HTTPException(status_code=409,
                            detail='A profile, preview or calibration runs: stop it, then Refresh '
                                   'to read the settings')
    already_running_node_names = sorted(
        set(settings_node_names) & _get_graph_full_node_names(preview_ros_node))
    if already_running_node_names:
        raise HTTPException(status_code=409,
                            detail=f'{", ".join(already_running_node_names)} runs already: stop '
                                   f'it, then Refresh to read the settings')

    log_file_path = os.path.join(tempfile.gettempdir(),
                                 f'par_setup_wizard_settings_{node_kind}_{package_name}.log')
    with open(log_file_path, 'w') as log_file:
        node_process = subprocess.Popen(_create_start_command(node_kind, package_name),
                                        stdout=log_file, stderr=subprocess.STDOUT,
                                        start_new_session=True)
    deadline_monotonic_s = time.monotonic() + SETTINGS_READ_TIMEOUT_S
    try:
        _wait_for_nodes(preview_ros_node, settings_node_names, node_process, log_file_path,
                        deadline_monotonic_s)
        settings_by_node_name = {}
        for full_node_name in settings_node_names:
            node_settings = _read_settings_once_answering(
                preview_session, full_node_name, node_process, log_file_path,
                deadline_monotonic_s)
            settings_by_node_name[full_node_name] = [
                node_setting.model_dump() for node_setting in node_settings]
    finally:
        stop_process_group(node_process, LAUNCH_STOP_SIGNALS, SETTINGS_READ_STOP_TIMEOUT_S)

    os.makedirs(SETTINGS_CACHE_FOLDER_PATH, exist_ok=True)
    cache_document = {'installed_package_stamp': _get_installed_package_stamp(package_name),
                      'settings_by_node_name': settings_by_node_name}
    with open(_get_cache_file_path(node_kind, package_name), 'w') as cache_file:
        json.dump(cache_document, cache_file, indent=2)


def _create_start_command(node_kind, package_name):
    """Return the command starting the package's nodes alone, with par_setup.yaml's values."""
    ros2_executable_path = shutil.which('ros2')
    if ros2_executable_path is None:
        raise RuntimeError('ros2 not found: start the backend in a bash with ROS and the '
                           'workspace sourced')
    par_setup_path = os.path.join(get_package_share_directory('par_framework_core'), 'config',
                                  'par_setup.yaml')
    if node_kind == NODE_KIND_SENSOR_NODE:
        # As par.launch.py starts it: executable and package share the name
        return [ros2_executable_path, 'run', package_name, package_name, '--ros-args',
                '-r', f'__node:={package_name}{SENSOR_NODE_NAME_SUFFIX}',
                '--params-file', par_setup_path]
    par_app_entry = _read_par_app_entry_or_raise(package_name)
    # Simplification: the app starts as it would on the projector, so an app that opens a window
    # shows it for the few seconds of the read. Upgrade: a convention for a headless start.
    if par_app_entry['executable'] is not None:
        return [ros2_executable_path, 'run', package_name, par_app_entry['executable'],
                '--ros-args', '--params-file', par_setup_path]
    return [ros2_executable_path, 'launch', package_name, par_app_entry['launch_file'],
            f'params_file:={par_setup_path}']


def _read_settings_once_answering(preview_session, full_node_name, node_process, log_file_path,
                                  deadline_monotonic_s):
    """
    Return the node's settings, asking again until it answers or the deadline passes.

    A node is in the ROS graph as soon as it exists, but answers parameter requests only once it
    spins, i.e. after its constructor: one that opens a window or loads a model there first
    answers seconds later, longer than a single request waits.
    """
    while True:
        try:
            parameter_client = camera_preview_api.get_node_parameter_client(preview_session,
                                                                            full_node_name)
            return camera_preview_api.read_node_settings(parameter_client)
        except HTTPException:
            if node_process.poll() is not None:
                raise RuntimeError(f'it ended while starting:\n{_read_log_tail(log_file_path)}')
            if time.monotonic() > deadline_monotonic_s:
                raise RuntimeError(f'{full_node_name} did not answer within '
                                   f'{SETTINGS_READ_TIMEOUT_S:.0f} s:\n'
                                   f'{_read_log_tail(log_file_path)}')
            time.sleep(SETTINGS_READ_POLL_INTERVAL_S)


def _wait_for_nodes(preview_ros_node, full_node_names, node_process, log_file_path,
                    deadline_monotonic_s):
    """Wait until every node is in the ROS graph; fail when the process ends or time runs out."""
    while time.monotonic() < deadline_monotonic_s:
        if set(full_node_names) <= _get_graph_full_node_names(preview_ros_node):
            return
        if node_process.poll() is not None:
            raise RuntimeError(f'it ended while starting:\n{_read_log_tail(log_file_path)}')
        time.sleep(SETTINGS_READ_POLL_INTERVAL_S)
    missing_node_names = sorted(set(full_node_names) - _get_graph_full_node_names(preview_ros_node))
    raise RuntimeError(f'{", ".join(missing_node_names)} did not start within '
                       f'{SETTINGS_READ_TIMEOUT_S:.0f} s:\n{_read_log_tail(log_file_path)}')


def _is_backend_launch_running(preview_session):
    """Tell whether this backend runs a profile (Run) or a camera launch (preview, calibration)."""
    if run_api.get_run_state().phase == run_api.RUN_PHASE_RUNNING:
        return True
    with preview_session.session_lock:
        camera_process = preview_session.camera_process
        return camera_process is not None and camera_process.poll() is None


def _get_graph_full_node_names(preview_ros_node):
    graph_full_node_names = set()
    for node_name, node_namespace in preview_ros_node.get_node_names_and_namespaces():
        graph_full_node_names.add(camera_preview_api.join_node_name(node_namespace, node_name))
    return graph_full_node_names


def _read_log_tail(log_file_path):
    try:
        with open(log_file_path) as log_file:
            log_lines = log_file.read().splitlines()
    except OSError:
        return '(no output)'
    return '\n'.join(log_lines[-SETTINGS_READ_LOG_TAIL_LINE_COUNT:])
