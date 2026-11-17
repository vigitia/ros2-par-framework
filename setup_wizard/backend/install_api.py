# Written by Claude Code
"""
Install API of the setup wizard backend, catalog part: what config/node_catalog.list's
repositories offer (node_catalog.py), refreshed from the network on request, and what installing
a choice of offers needs.

A refresh runs in a background thread, a few repositories at a time; the app polls its state. The
catalog read from the downloaded clones is kept in memory until the next refresh. Camera types
this repository registers itself (core) are offered too, so their released drivers can be chosen.
"""

from concurrent.futures import ThreadPoolExecutor
import threading

from ament_index_python.resources import has_resource
from camera_types import read_camera_types
from fastapi import APIRouter, HTTPException
from node_catalog import (CatalogOffer, CatalogRepository, compute_install_plan,
                          InstallPlan, NODE_CATALOG_LIST_PATH,
                          OFFER_KIND_APP, OFFER_KIND_CAMERA, OFFER_KIND_SENSOR_NODE,
                          read_catalog_repository, read_node_list_file, update_catalog_cache)
from par_framework_core.launch_helpers import (get_par_app_package_names,
                                               get_sensor_node_package_names)
from pydantic import BaseModel

# Repositories downloaded at the same time during a refresh: faster than one by one, without
# opening a connection per repository at once
CATALOG_REFRESH_PARALLEL_DOWNLOAD_COUNT = 4

CATALOG_REFRESH_PHASE_IDLE = 'idle'
CATALOG_REFRESH_PHASE_RUNNING = 'running'
CATALOG_REFRESH_PHASE_DONE = 'done'
REPOSITORY_REFRESH_STATUS_PENDING = 'pending'
REPOSITORY_REFRESH_STATUS_OK = 'ok'
REPOSITORY_REFRESH_STATUS_FAILED = 'failed'

install_router = APIRouter()
# Guards everything below; the refresh thread and the request handlers both change it
_catalog_lock = threading.Lock()
_catalog_refresh_phase = CATALOG_REFRESH_PHASE_IDLE
_repository_refresh_state_by_name = {}
# The catalog read after the last refresh; None until the first read
_catalog_repositories = None


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


class CatalogState(BaseModel):
    offers: list[OfferState] = []
    repositories: list[CatalogRepository] = []
    # Why the catalog list itself could not be read; None when it could
    catalog_error_text: str | None = None


class OfferChoice(BaseModel):
    # One of the OFFER_KIND_* values
    kind: str
    name: str


class InstallPlanRequest(BaseModel):
    chosen_offers: list[OfferChoice]


@install_router.post('/api/catalog/refresh')
def start_catalog_refresh() -> CatalogRefreshState:
    """Start downloading the catalog repositories' latest commits; a running refresh continues."""
    global _catalog_refresh_phase, _repository_refresh_state_by_name
    try:
        node_list_entries = read_node_list_file(NODE_CATALOG_LIST_PATH)
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
    offer_states = []
    for offer in _collect_offers(catalog_repositories, camera_types):
        if offer.kind == OFFER_KIND_APP:
            is_installed = offer.name in installed_app_names
        elif offer.kind == OFFER_KIND_SENSOR_NODE:
            is_installed = offer.name in installed_sensor_node_names
        else:
            is_installed = offer.name in installed_camera_types
        offer_states.append(OfferState(**offer.model_dump(), is_installed=is_installed))
    return CatalogState(offers=offer_states, repositories=catalog_repositories)


@install_router.post('/api/install/plan')
def create_install_plan(request: InstallPlanRequest) -> InstallPlan:
    """Return the repositories and released packages that installing the chosen offers needs."""
    try:
        catalog_repositories = _get_catalog_repositories()
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail=f'The catalog list cannot be read: {error}')
    offer_by_kind_and_name = {}
    for offer in _collect_offers(catalog_repositories, read_camera_types()):
        offer_by_kind_and_name[(offer.kind, offer.name)] = offer
    chosen_offers = []
    for offer_choice in request.chosen_offers:
        offer = offer_by_kind_and_name.get((offer_choice.kind, offer_choice.name))
        if offer is None:
            raise HTTPException(status_code=404,
                                detail=f'The catalog offers no {offer_choice.kind} '
                                       f'{offer_choice.name!r}: refresh the catalog')
        chosen_offers.append(offer)
    return compute_install_plan(chosen_offers, catalog_repositories,
                                _InstalledPackageNames())


class _InstalledPackageNames:
    """Answers `package_name in ...` from the ament index, without listing every package."""

    def __contains__(self, package_name):
        return has_resource('packages', package_name)


def _refresh_catalog(node_list_entries) -> None:
    """Download every catalog repository, then read the catalog anew; runs in its own thread."""
    global _catalog_refresh_phase, _catalog_repositories
    with ThreadPoolExecutor(max_workers=CATALOG_REFRESH_PARALLEL_DOWNLOAD_COUNT) as executor:
        executor.map(_refresh_catalog_repository, node_list_entries)
    catalog_repositories = []
    for node_list_entry in node_list_entries:
        catalog_repositories.append(read_catalog_repository(node_list_entry))
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
    catalog_repositories = []
    for node_list_entry in read_node_list_file(NODE_CATALOG_LIST_PATH):
        catalog_repositories.append(read_catalog_repository(node_list_entry))
    with _catalog_lock:
        if _catalog_repositories is None:
            _catalog_repositories = catalog_repositories
        return _catalog_repositories


def _collect_offers(catalog_repositories, camera_types) -> list[CatalogOffer]:
    """
    Return the catalog repositories' offers plus the installed camera types none of them offers,
    e.g. those registered in this repository (core). camera_types: read_camera_types().

    An installed camera type that a catalog repository offers too is that repository's.
    """
    offers = []
    offered_camera_types = set()
    for catalog_repository in catalog_repositories:
        for offer in catalog_repository.offers:
            offers.append(offer)
            if offer.kind == OFFER_KIND_CAMERA:
                offered_camera_types.add(offer.name)
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
                                   ros_package_candidate_names=camera_type.required_package_names))
    return offers
