# Written by Claude Code
"""
Install API of the setup wizard backend: what config/node_catalog.list's repositories offer
(node_catalog.py), refreshed from the network on request, what installing a choice of offers
needs, and the install itself.

A refresh runs in a background thread, a few repositories at a time; the app polls its state. The
catalog read from the downloaded clones is kept in memory until the next refresh. Camera types
this repository registers itself (core) are offered too, so their released drivers can be chosen.

An install adds the plan to the store lists and runs scripts/local_build.sh --non-interactive in
its own process group, its output in a log file; the app polls its state. What needs root (apt
packages, `rosdep init`) ends the build with one sudo command for the user to run in a terminal;
starting the install again then continues it. After a successful build the backend restarts
itself, because it reads the ament index only once, at its start.
"""

from concurrent.futures import ThreadPoolExecutor
import os
import subprocess
import sys
import tempfile
import threading

import apps_api
from ament_index_python.packages import get_package_share_directory
from ament_index_python.resources import has_resource
from backend_shared_helpers import read_log_lines
from camera_types import read_camera_types
from fastapi import APIRouter, HTTPException
from node_catalog import (add_install_plan_to_store_lists, add_user_catalog_repository,
                          CatalogOffer, CatalogRepository, compute_install_plan,
                          get_camera_version_package_name, InstallPlan, OFFER_KIND_APP,
                          OFFER_KIND_CAMERA, OFFER_KIND_SENSOR_NODE, parse_package_manifest,
                          read_catalog_list_entries, read_catalog_repository,
                          read_user_catalog_directory_names, remove_user_catalog_repository,
                          REPOSITORY_ROOT_PATH, update_catalog_cache)
from par_framework_core.launch_helpers import (get_par_app_package_names,
                                               get_sensor_node_package_names,
                                               read_sensor_node_entry)
from profile_run_state import is_profile_running, profile_run_lock
from pydantic import BaseModel
import run_api

# Repositories downloaded at the same time during a refresh: faster than one by one, without
# opening a connection per repository at once
CATALOG_REFRESH_PARALLEL_DOWNLOAD_COUNT = 4

CATALOG_REFRESH_PHASE_IDLE = 'idle'
CATALOG_REFRESH_PHASE_RUNNING = 'running'
CATALOG_REFRESH_PHASE_DONE = 'done'
REPOSITORY_REFRESH_STATUS_PENDING = 'pending'
REPOSITORY_REFRESH_STATUS_OK = 'ok'
REPOSITORY_REFRESH_STATUS_FAILED = 'failed'

BACKEND_FOLDER_PATH = os.path.dirname(os.path.abspath(__file__))
LOCAL_BUILD_SCRIPT_PATH = os.path.join(REPOSITORY_ROOT_PATH, 'scripts', 'local_build.sh')
LOCAL_BUILD_NON_INTERACTIVE_OPTION = '--non-interactive'
# What local_build.sh --non-interactive prints and returns when something needs root; both must
# stay as they are in the script
LOCAL_BUILD_SUDO_COMMAND_LINE_PREFIX = 'needs sudo: '
LOCAL_BUILD_EXIT_CODE_NEEDS_SUDO = 3
INSTALL_LOG_PATH = os.path.join(tempfile.gettempdir(), 'par_setup_wizard_install.log')
INSTALL_LOG_TAIL_LINE_COUNT = 20
BASH_EXECUTABLE_PATH = '/bin/bash'
# Set for the backend that a successful install restarts, so it reports the install as done
INSTALL_DONE_ENVIRONMENT_NAME = 'PAR_SETUP_WIZARD_INSTALL_DONE'

# What the install state reports: nothing installed since the start, building, a sudo command is
# needed, the build failed, the backend restarts, the backend restarted after a successful build
INSTALL_PHASE_IDLE = 'idle'
INSTALL_PHASE_RUNNING = 'running'
INSTALL_PHASE_NEEDS_SUDO = 'needs_sudo'
INSTALL_PHASE_FAILED = 'failed'
INSTALL_PHASE_RESTARTING = 'restarting'
INSTALL_PHASE_INSTALLED = 'installed'

install_router = APIRouter()
# Guards everything below; the refresh thread and the request handlers both change it
_catalog_lock = threading.Lock()
_catalog_refresh_phase = CATALOG_REFRESH_PHASE_IDLE
_repository_refresh_state_by_name = {}
# The catalog read after the last refresh; None until the first read
_catalog_repositories = None

# Guards the install's state below; the request handlers and the thread waiting for the build
# both change it. Lock order: profile_run_state.profile_run_lock before _install_lock
_install_lock = threading.Lock()
# The latest build's process; None before the first since this backend started
_install_process = None
# The command of the build's "needs sudo: " line; None unless it ended with one
_install_sudo_command_text = None
# The phase while no build process tells it: idle, restarting, or installed in the backend that a
# successful install restarted
_install_phase = INSTALL_PHASE_IDLE
if os.environ.pop(INSTALL_DONE_ENVIRONMENT_NAME, None) is not None:
    _install_phase = INSTALL_PHASE_INSTALLED
# The uvicorn.Server a successful install shuts down; None when the backend runs without one
_backend_server = None


class RepositoryRefreshState(BaseModel):
    directory_name: str
    # One of the REPOSITORY_REFRESH_STATUS_* values
    status: str
    # git's message when it failed
    error_text: str | None = None


class CatalogRefreshState(BaseModel):
    # One of the CATALOG_REFRESH_PHASE_* values
    phase: str
    repositories: list[RepositoryRefreshState] = []


class OfferState(CatalogOffer):
    # True when the offer is installed: the app or sensor node is registered, the camera type is
    # registered and its required packages are installed
    is_installed: bool = False
    # The <version> of the version package's package.xml where it is installed (the workspace
    # or /opt/ros); None when it is not installed
    installed_version: str | None = None
    # The <version> in the catalog repository providing the version package, as downloaded last;
    # None for a released package (e.g. a camera driver from apt), which no catalog repository has
    available_version: str | None = None


class CatalogState(BaseModel):
    offers: list[OfferState] = []
    repositories: list[CatalogRepository] = []
    # Why the catalog list itself could not be read; None when it could
    catalog_error_text: str | None = None


class OfferChoice(BaseModel):
    # One of the OFFER_KIND_* values
    kind: str
    name: str


class UserRepositoryRequest(BaseModel):
    # A git URL, e.g. https://github.com/<owner>/<repo>.git
    url: str
    # None or empty: the remote's default branch
    branch: str | None = None


class InstallPlanRequest(BaseModel):
    chosen_offers: list[OfferChoice]


class InstallState(BaseModel):
    # One of the INSTALL_PHASE_* values
    phase: str
    # For needs_sudo: the command to run in a terminal before starting the install again
    sudo_command_text: str | None = None
    # For failed: the build's exit code
    exit_code: int | None = None
    # The last lines of the build's output, as they are
    log_lines: list[str] = []


@install_router.post('/api/catalog/refresh')
def start_catalog_refresh() -> CatalogRefreshState:
    """Start downloading the catalog repositories' latest commits; a running refresh continues."""
    global _catalog_refresh_phase, _repository_refresh_state_by_name
    try:
        node_list_entries = read_catalog_list_entries()
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail=f'The catalog list cannot be read: {error}')
    with _catalog_lock:
        if _catalog_refresh_phase != CATALOG_REFRESH_PHASE_RUNNING:
            _catalog_refresh_phase = CATALOG_REFRESH_PHASE_RUNNING
            _repository_refresh_state_by_name = {}
            for node_list_entry in node_list_entries:
                _repository_refresh_state_by_name[node_list_entry.directory_name] = (
                    RepositoryRefreshState(directory_name=node_list_entry.directory_name,
                                           status=REPOSITORY_REFRESH_STATUS_PENDING))
            threading.Thread(target=_refresh_catalog, args=(node_list_entries,),
                             daemon=True).start()
        return _read_catalog_refresh_state()


@install_router.post('/api/catalog/repositories')
def add_user_repository(request: UserRepositoryRequest) -> CatalogRefreshState:
    """Add a repository to the catalog by its URL, then download the catalog anew."""
    with _catalog_lock:
        if _catalog_refresh_phase == CATALOG_REFRESH_PHASE_RUNNING:
            raise HTTPException(status_code=409,
                                detail='The catalog is being downloaded; try again after it')
    try:
        add_user_catalog_repository(request.url, request.branch)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except OSError as error:
        raise HTTPException(status_code=500, detail=f'The repository cannot be stored: {error}')
    return start_catalog_refresh()


@install_router.delete('/api/catalog/repositories/{directory_name}')
def remove_user_repository(directory_name: str) -> None:
    """Remove a repository the user added from the catalog; an installed copy stays installed."""
    global _catalog_repositories
    try:
        remove_user_catalog_repository(directory_name)
    except KeyError:
        raise HTTPException(status_code=404,
                            detail=f'{directory_name} is no repository added in the wizard')
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail=f'The repository cannot be removed: {error}')
    with _catalog_lock:
        if _catalog_repositories is not None:
            _catalog_repositories = [
                catalog_repository for catalog_repository in _catalog_repositories
                if catalog_repository.directory_name != directory_name]


@install_router.get('/api/catalog/refresh')
def get_catalog_refresh_state() -> CatalogRefreshState:
    """Tell whether a refresh runs and how far each repository got."""
    with _catalog_lock:
        return _read_catalog_refresh_state()


@install_router.get('/api/catalog')
def get_catalog() -> CatalogState:
    """Return every offer with its installed state, read from the last downloaded clones."""
    try:
        catalog_repositories = _get_catalog_repositories()
    except (OSError, ValueError) as error:
        return CatalogState(catalog_error_text=f'The catalog list cannot be read: {error}')
    camera_types = read_camera_types()
    installed_camera_types = set()
    for camera_type in camera_types:
        if camera_type.is_installed:
            installed_camera_types.add(camera_type.camera_type)
    installed_app_names = set(get_par_app_package_names())
    installed_sensor_node_names = set(get_sensor_node_package_names())
    available_version_by_package_name = {}
    for catalog_repository in catalog_repositories:
        available_version_by_package_name.update(catalog_repository.package_version_by_name)
    offer_states = []
    for offer in _collect_offers(catalog_repositories, camera_types):
        if offer.kind == OFFER_KIND_APP:
            is_installed = offer.name in installed_app_names
        elif offer.kind == OFFER_KIND_SENSOR_NODE:
            is_installed = offer.name in installed_sensor_node_names
        else:
            is_installed = offer.name in installed_camera_types
        offer_states.append(OfferState(
            **offer.model_dump(), is_installed=is_installed,
            installed_version=_read_installed_package_version(offer.version_package_name),
            available_version=available_version_by_package_name.get(offer.version_package_name)))
    return CatalogState(offers=offer_states, repositories=catalog_repositories)


@install_router.post('/api/install/plan')
def create_install_plan(request: InstallPlanRequest) -> InstallPlan:
    """Return the repositories and released packages that installing the chosen offers needs."""
    return _compute_install_plan_for_choices(request.chosen_offers)


@install_router.post('/api/install/start')
def start_install(request: InstallPlanRequest) -> InstallState:
    """
    Add what the chosen offers need to the store lists and build the workspace.

    Refuses while an install or a profile run is active. Starting again with the same offers
    continues an install that needed a sudo command: the lists already have the entries.
    """
    global _install_process, _install_sudo_command_text
    install_plan = _compute_install_plan_for_choices(request.chosen_offers)
    with profile_run_lock, _install_lock:
        if _is_install_running():
            raise HTTPException(status_code=409, detail='An install is running already')
        if is_profile_running():
            raise HTTPException(status_code=409,
                                detail='A profile is running: stop it before installing')
        try:
            add_install_plan_to_store_lists(install_plan)
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=500,
                                detail=f'The store lists cannot be written: {error}')
        # No terminal to answer git's questions: a missing key or password fails at once
        build_environment = dict(os.environ, GIT_TERMINAL_PROMPT='0',
                                 GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=15')
        with open(INSTALL_LOG_PATH, 'w') as install_log_file:
            _install_process = subprocess.Popen(
                [LOCAL_BUILD_SCRIPT_PATH, LOCAL_BUILD_NON_INTERACTIVE_OPTION],
                cwd=REPOSITORY_ROOT_PATH, env=build_environment, stdin=subprocess.DEVNULL,
                stdout=install_log_file, stderr=subprocess.STDOUT, start_new_session=True)
        _install_sudo_command_text = None
        threading.Thread(target=_finish_install, args=(_install_process,), daemon=True).start()
        return _read_install_state()


@install_router.get('/api/install/state')
def get_install_state() -> InstallState:
    """Tell how the latest install went; after a restart following a successful one, installed."""
    with _install_lock:
        return _read_install_state()


def set_backend_server_for_restart(backend_server) -> None:
    """Hand over the uvicorn.Server that a successful install shuts down to restart the backend."""
    global _backend_server
    _backend_server = backend_server


def is_backend_restart_requested() -> bool:
    """Tell whether the backend should start anew after its server has stopped."""
    with _install_lock:
        return _install_phase == INSTALL_PHASE_RESTARTING


def restart_backend() -> None:
    """
    Replace this process by a new backend started in a freshly sourced bash, so the ament index it
    reads includes the packages just built. Call after the server has stopped.

    os.execv keeps the process ID, so whoever started the backend (start_setup_wizard.sh) still
    stops the new one. The new backend reports the install as done (INSTALL_DONE_ENVIRONMENT_NAME).
    """
    ros_setup_path = os.path.join('/opt/ros', os.environ.get('ROS_DISTRO', ''), 'setup.bash')
    workspace_setup_path = os.path.join(REPOSITORY_ROOT_PATH, 'install', 'setup.bash')
    backend_script_path = os.path.join(BACKEND_FOLDER_PATH, 'setup_wizard_backend.py')
    # ROS's setup scripts read unset variables, so no `set -u`; the paths are passed as arguments,
    # not pasted into the command text
    restart_command_text = 'source "$1" && source "$2" && exec "$3" "$4"'
    restart_environment = dict(os.environ)
    restart_environment[INSTALL_DONE_ENVIRONMENT_NAME] = '1'
    os.execve(BASH_EXECUTABLE_PATH,
              [BASH_EXECUTABLE_PATH, '-c', restart_command_text, 'restart_backend',
               ros_setup_path, workspace_setup_path, sys.executable, backend_script_path],
              restart_environment)


def _compute_install_plan_for_choices(offer_choices: list[OfferChoice]) -> InstallPlan:
    """Return the install plan of the chosen offers; 404 for an offer the catalog lacks."""
    try:
        catalog_repositories = _get_catalog_repositories()
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail=f'The catalog list cannot be read: {error}')
    offer_by_kind_and_name = {}
    for offer in _collect_offers(catalog_repositories, read_camera_types()):
        offer_by_kind_and_name[(offer.kind, offer.name)] = offer
    chosen_offers = []
    for offer_choice in offer_choices:
        offer = offer_by_kind_and_name.get((offer_choice.kind, offer_choice.name))
        if offer is None:
            raise HTTPException(status_code=404,
                                detail=f'The catalog offers no {offer_choice.kind} '
                                       f'{offer_choice.name!r}: refresh the catalog')
        chosen_offers.append(offer)
    return compute_install_plan(chosen_offers, catalog_repositories,
                                _InstalledPackageNames())


def _finish_install(install_process) -> None:
    """Wait for the build to end and record how; runs in its own thread."""
    global _install_phase, _install_sudo_command_text
    exit_code = install_process.wait()
    with _install_lock:
        if exit_code == LOCAL_BUILD_EXIT_CODE_NEEDS_SUDO:
            _install_sudo_command_text = _find_sudo_command_text(read_log_lines(INSTALL_LOG_PATH))
        if exit_code != 0 or _backend_server is None:
            return
        _install_phase = INSTALL_PHASE_RESTARTING
    # Outside the install lock: stopping a run waits for it to end. A run started during the
    # build would outlive the restart unnoticed, as the new backend knows nothing of it
    run_api.stop_run()
    # uvicorn shuts down as after Ctrl+C: the lifespans stop the camera launch and ROS; main()
    # then calls restart_backend
    _backend_server.should_exit = True


def _is_install_running() -> bool:
    """Tell whether the build runs; hold _install_lock."""
    return _install_process is not None and _install_process.poll() is None


def _read_install_state() -> InstallState:
    """Return the install state; hold _install_lock."""
    if _install_phase == INSTALL_PHASE_RESTARTING:
        return InstallState(phase=INSTALL_PHASE_RESTARTING)
    log_lines = read_log_lines(INSTALL_LOG_PATH)[-INSTALL_LOG_TAIL_LINE_COUNT:]
    if _install_process is None:
        if _install_phase == INSTALL_PHASE_INSTALLED:
            # The build that the restart followed
            return InstallState(phase=_install_phase, log_lines=log_lines)
        return InstallState(phase=_install_phase)
    exit_code = _install_process.poll()
    if exit_code is None:
        return InstallState(phase=INSTALL_PHASE_RUNNING, log_lines=log_lines)
    if exit_code == LOCAL_BUILD_EXIT_CODE_NEEDS_SUDO and _install_sudo_command_text is not None:
        return InstallState(phase=INSTALL_PHASE_NEEDS_SUDO,
                            sudo_command_text=_install_sudo_command_text, log_lines=log_lines)
    if exit_code == 0:
        # Only without a server to shut down, e.g. the backend imported by a test
        return InstallState(phase=INSTALL_PHASE_INSTALLED, log_lines=log_lines)
    return InstallState(phase=INSTALL_PHASE_FAILED, exit_code=exit_code, log_lines=log_lines)


def _find_sudo_command_text(log_lines: list[str]) -> str | None:
    """Return the command of the build's "needs sudo: " line, None without one."""
    for log_line in reversed(log_lines):
        if log_line.startswith(LOCAL_BUILD_SUDO_COMMAND_LINE_PREFIX):
            return log_line[len(LOCAL_BUILD_SUDO_COMMAND_LINE_PREFIX):]
    return None


class _InstalledPackageNames:
    """Answers `package_name in ...` from the ament index, without listing every package."""

    def __contains__(self, package_name):
        return has_resource('packages', package_name)


def _read_installed_package_version(package_name: str) -> str | None:
    """Return the <version> of an installed package's package.xml; None when not installed."""
    if not package_name or not has_resource('packages', package_name):
        return None
    manifest_path = os.path.join(get_package_share_directory(package_name), 'package.xml')
    try:
        with open(manifest_path) as manifest_file:
            _, package_version, _ = parse_package_manifest(manifest_file.read(), manifest_path)
    except (OSError, ValueError):
        # Installed, but its version cannot be read: shown as installed without a version
        return ''
    return package_version


def _refresh_catalog(node_list_entries) -> None:
    """Download every catalog repository, then read the catalog anew; runs in its own thread."""
    global _catalog_refresh_phase, _catalog_repositories
    with ThreadPoolExecutor(max_workers=CATALOG_REFRESH_PARALLEL_DOWNLOAD_COUNT) as executor:
        executor.map(_refresh_catalog_repository, node_list_entries)
    catalog_repositories = _read_catalog_repositories(node_list_entries)
    with _catalog_lock:
        # A repository that could not be read and failed to download shows the download's error,
        # which names the cause (e.g. no access), not only that nothing was downloaded
        for catalog_repository in catalog_repositories:
            refresh_state = _repository_refresh_state_by_name[catalog_repository.directory_name]
            if catalog_repository.error_text is not None and refresh_state.error_text is not None:
                catalog_repository.error_text = refresh_state.error_text
        _catalog_repositories = catalog_repositories
        _catalog_refresh_phase = CATALOG_REFRESH_PHASE_DONE


def _refresh_catalog_repository(node_list_entry) -> None:
    """Download one repository and record how it went."""
    status = REPOSITORY_REFRESH_STATUS_OK
    error_text = None
    try:
        update_catalog_cache(node_list_entry)
    except (OSError, RuntimeError) as error:
        status = REPOSITORY_REFRESH_STATUS_FAILED
        error_text = str(error)
    with _catalog_lock:
        _repository_refresh_state_by_name[node_list_entry.directory_name] = (
            RepositoryRefreshState(directory_name=node_list_entry.directory_name, status=status,
                                   error_text=error_text))


def _read_catalog_refresh_state() -> CatalogRefreshState:
    """Return the refresh state; hold _catalog_lock."""
    return CatalogRefreshState(phase=_catalog_refresh_phase,
                               repositories=list(_repository_refresh_state_by_name.values()))


def _get_catalog_repositories() -> list[CatalogRepository]:
    """
    Return the catalog read from the downloaded clones: the last refresh's result, else read now.

    Raises OSError or ValueError when the catalog list cannot be read.
    """
    global _catalog_repositories
    with _catalog_lock:
        if _catalog_repositories is not None:
            return _catalog_repositories
    catalog_repositories = _read_catalog_repositories(read_catalog_list_entries())
    with _catalog_lock:
        if _catalog_repositories is None:
            _catalog_repositories = catalog_repositories
        return _catalog_repositories


def _read_catalog_repositories(node_list_entries) -> list[CatalogRepository]:
    """Read every catalog repository from its downloaded clone, marking those the user added."""
    try:
        user_added_directory_names = read_user_catalog_directory_names()
    except (OSError, ValueError):
        # read_catalog_list_entries has read the same list just before; a race with an edit
        user_added_directory_names = set()
    catalog_repositories = []
    for node_list_entry in node_list_entries:
        catalog_repository = read_catalog_repository(node_list_entry)
        catalog_repository.is_user_added = (node_list_entry.directory_name
                                            in user_added_directory_names)
        catalog_repositories.append(catalog_repository)
    return catalog_repositories


def _collect_offers(catalog_repositories, camera_types) -> list[CatalogOffer]:
    """
    Return the catalog repositories' offers plus what is installed but none of them offers: camera
    types registered in this repository (core), and apps and sensor nodes installed by hand or
    from core (e.g. RViz). camera_types: read_camera_types().

    Something installed that a catalog repository offers too is that repository's.
    """
    offers = []
    offered_names_by_kind = {OFFER_KIND_APP: set(), OFFER_KIND_CAMERA: set(),
                             OFFER_KIND_SENSOR_NODE: set()}
    for catalog_repository in catalog_repositories:
        for offer in catalog_repository.offers:
            offers.append(offer)
            offered_names_by_kind[offer.kind].add(offer.name)
    for installed_app in apps_api.get_installed_app_list().installed_apps:
        if installed_app.app_name in offered_names_by_kind[OFFER_KIND_APP]:
            continue
        offers.append(CatalogOffer(kind=OFFER_KIND_APP, name=installed_app.app_name,
                                   display_name=installed_app.display_name,
                                   description=installed_app.description,
                                   version_package_name=installed_app.app_name))
    for sensor_node_package_name in get_sensor_node_package_names():
        if sensor_node_package_name in offered_names_by_kind[OFFER_KIND_SENSOR_NODE]:
            continue
        try:
            sensor_node_entry = read_sensor_node_entry(sensor_node_package_name)
        except RuntimeError:
            # Malformed: the Sensor nodes area reports it
            continue
        offers.append(CatalogOffer(kind=OFFER_KIND_SENSOR_NODE, name=sensor_node_package_name,
                                   display_name=sensor_node_entry['display_name'],
                                   description=sensor_node_entry['description'],
                                   version_package_name=sensor_node_package_name))
    offered_camera_types = offered_names_by_kind[OFFER_KIND_CAMERA]
    for camera_type in camera_types:
        if camera_type.camera_type in offered_camera_types:
            continue
        if camera_type.entry_error_text is not None:
            continue
        # Its required packages are what is missing to start it, usually a released driver
        offers.append(CatalogOffer(kind=OFFER_KIND_CAMERA, name=camera_type.camera_type,
                                   display_name=camera_type.display_name,
                                   description=camera_type.description,
                                   required_package_names=camera_type.required_package_names,
                                   ros_package_candidate_names=camera_type.required_package_names,
                                   version_package_name=get_camera_version_package_name(
                                       camera_type.required_package_names, '')))
    return offers
