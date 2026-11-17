# Written by Claude Code
"""
Node catalog of the setup wizard: what the repositories of config/node_catalog.list offer (apps,
camera types, sensor processing nodes), read from the repositories themselves before they are
installed, and which repositories and released packages installing a choice needs.

Each catalog repository is kept as a blob-less clone without a checkout in the user's cache folder
(git clone --depth 1 --filter=blob:none --no-checkout): only the latest commit's file list is
downloaded, and `git show` fetches just the files read here, the ament index entries
(resource/par_framework_*/<name>) and the package.xml files, wherever the packages sit in the
repository. The entries are checked with the same functions as installed ones (launch_helpers), so
the repository stays the one place that describes what it offers.
"""

import os
import re
import subprocess
from typing import NamedTuple
import xml.etree.ElementTree as ElementTree

from par_framework_core.launch_helpers import (CAMERA_ENTRY_REQUIRED_PACKAGES_KEY,
                                               CAMERA_RESOURCE_TYPE, check_camera_entry,
                                               check_par_app_entry, check_sensor_node_entry,
                                               PAR_APP_RESOURCE_TYPE,
                                               parse_ament_index_entry_text,
                                               SENSOR_NODE_RESOURCE_TYPE)
from pydantic import BaseModel

# The repository this backend belongs to: setup_wizard/backend/ -> two folders up
REPOSITORY_ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NODE_CATALOG_LIST_PATH = os.path.join(REPOSITORY_ROOT_PATH, 'config', 'node_catalog.list')
NODES_SOURCE_FOLDER_PATH = os.path.join(REPOSITORY_ROOT_PATH, 'src')
# The user's cache folder (XDG base directory spec): $XDG_CACHE_HOME, by default ~/.cache
CATALOG_CACHE_FOLDER_PATH = os.path.join(
    os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache'),
    'par_setup_wizard', 'catalog')
# A clone or fetch over the network may be slow; reading the local clone is quick
GIT_NETWORK_TIMEOUT_S = 180
GIT_LOCAL_TIMEOUT_S = 60

# The branch column of a node list: "-" or left out means the remote's default branch
NO_BRANCH_TEXT = '-'
# A node list's directory names become folder names: nothing that could leave the folder. URLs and
# branches go to git as arguments; a leading '-' would make git read them as options
NODE_LIST_DIRECTORY_NAME_PATTERN = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]*')
NODE_LIST_VALUE_PATTERN = re.compile(r'[^-\s]\S*')

# What the wizard offers, one kind per ament index resource type
OFFER_KIND_APP = 'app'
OFFER_KIND_CAMERA = 'camera'
OFFER_KIND_SENSOR_NODE = 'sensor_node'
OFFER_KIND_BY_RESOURCE_TYPE = {
    PAR_APP_RESOURCE_TYPE: OFFER_KIND_APP,
    CAMERA_RESOURCE_TYPE: OFFER_KIND_CAMERA,
    SENSOR_NODE_RESOURCE_TYPE: OFFER_KIND_SENSOR_NODE,
}
# An ament index entry in a repository: <package folder>/resource/<resource type>/<entry name>,
# the package folder being the repository root or any folder below it
INDEX_ENTRY_PATH_PATTERN = re.compile(
    r'(?:^|/)resource/(' + '|'.join(OFFER_KIND_BY_RESOURCE_TYPE) + r')/([^/]+)$')
PACKAGE_MANIFEST_PATH_PATTERN = re.compile(r'(?:^|/)package\.xml$')
# The package.xml tags naming packages that must be there to build or run it
PACKAGE_DEPENDENCY_TAG_NAMES = ('depend', 'build_depend', 'build_export_depend', 'exec_depend')


class NodeListEntry(NamedTuple):
    """One line of a node list: <directory> <git-url> [branch]."""

    directory_name: str
    url: str
    # None: the remote's default branch
    branch: str | None


class CatalogOffer(BaseModel):
    # One of the OFFER_KIND_* values
    kind: str
    # The entry's name: the app's or sensor node's package, the camera type
    name: str
    display_name: str = ''
    description: str = ''
    # The catalog repository offering it; None for a camera type of this repository (core)
    repository_directory_name: str | None = None
    # What it needs besides its repository: an app's required sensor nodes (its
    # required_launch_switches), a sensor node's required_sensor_nodes, a camera's
    # required_packages
    required_package_names: list[str] = []
    # Packages it needs that a released package (rosdep key) may provide, e.g. a camera driver
    ros_package_candidate_names: list[str] = []


class CatalogRepository(BaseModel):
    directory_name: str
    url: str
    branch: str | None = None
    # The commit the offers were read from (short hash); None until downloaded
    commit_text: str | None = None
    # The ROS packages in the repository, from its package.xml files
    package_names: list[str] = []
    # Packages its package.xml files depend on, without its own
    dependency_package_names: list[str] = []
    offers: list[CatalogOffer] = []
    # Entries that could not be read or are malformed, as error texts
    entry_error_texts: list[str] = []
    # Why the repository could not be read at all, e.g. git's message; None when it could
    error_text: str | None = None


class PlannedRepository(BaseModel):
    directory_name: str
    url: str
    branch: str | None = None
    # Display names of the chosen offers or the repositories that need it
    needed_by_names: list[str] = []
    # True when it is in src/ already
    is_cloned: bool = False


class PlannedRosPackage(BaseModel):
    # The rosdep key, e.g. v4l2_camera
    ros_package_name: str
    needed_by_names: list[str] = []


class InstallPlan(BaseModel):
    repositories: list[PlannedRepository] = []
    ros_packages: list[PlannedRosPackage] = []


def read_node_list_file(node_list_path: str) -> list[NodeListEntry]:
    """
    Return the entries of a file in the nodes.list format, the same rules as scripts/common.sh.

    Comments (from '#') and blank lines are skipped. Raises ValueError naming the line when an
    entry has no URL or a value git or the file system must not get.
    """
    node_list_entries = []
    with open(node_list_path) as node_list_file:
        for line_number, line_text in enumerate(node_list_file, start=1):
            words = line_text.split('#', 1)[0].split()
            if not words:
                continue
            error_start_text = f'{node_list_path} line {line_number}'
            if len(words) < 2:
                raise ValueError(f'{error_start_text}: expected "<dir> <url> [branch]"')
            directory_name, url = words[0], words[1]
            branch = words[2] if len(words) > 2 and words[2] != NO_BRANCH_TEXT else None
            if not NODE_LIST_DIRECTORY_NAME_PATTERN.fullmatch(directory_name):
                raise ValueError(f'{error_start_text}: {directory_name!r} is no plain folder name')
            for value in (url, branch):
                if value is not None and not NODE_LIST_VALUE_PATTERN.fullmatch(value):
                    raise ValueError(f'{error_start_text}: {value!r} must not start with "-"')
            node_list_entries.append(NodeListEntry(directory_name, url, branch))
    return node_list_entries


def get_catalog_cache_path(directory_name: str) -> str:
    """Return the folder of a catalog repository's blob-less clone."""
    return os.path.join(CATALOG_CACHE_FOLDER_PATH, directory_name)


def update_catalog_cache(node_list_entry: NodeListEntry) -> None:
    """
    Download a catalog repository's latest commit (file list only) into its cache folder.

    The first time a blob-less clone without checkout, later a fetch of the branch's latest commit
    that the clone's branch is moved to. Raises RuntimeError with git's message when it fails.
    """
    cache_path = get_catalog_cache_path(node_list_entry.directory_name)
    if not os.path.isdir(os.path.join(cache_path, '.git')):
        os.makedirs(CATALOG_CACHE_FOLDER_PATH, exist_ok=True)
        clone_command = ['clone', '--quiet', '--depth', '1', '--filter=blob:none', '--no-checkout']
        if node_list_entry.branch is not None:
            clone_command += ['--branch', node_list_entry.branch]
        _run_git(clone_command + ['--', node_list_entry.url, cache_path], REPOSITORY_ROOT_PATH,
                 GIT_NETWORK_TIMEOUT_S)
        return
    # The list may name another URL or branch than when the clone was made
    _run_git(['remote', 'set-url', 'origin', node_list_entry.url], cache_path,
             GIT_LOCAL_TIMEOUT_S)
    fetched_reference = node_list_entry.branch or 'HEAD'
    _run_git(['fetch', '--quiet', '--depth', '1', '--filter=blob:none', 'origin',
              fetched_reference], cache_path, GIT_NETWORK_TIMEOUT_S)
    # --soft moves only the branch, there is no checkout to change
    _run_git(['reset', '--quiet', '--soft', 'FETCH_HEAD'], cache_path, GIT_LOCAL_TIMEOUT_S)


def read_catalog_repository(node_list_entry: NodeListEntry) -> CatalogRepository:
    """
    Return what a catalog repository offers, read from its cache folder (no network, except git
    fetching a file it has not read before).

    Problems are reported in the result: error_text when the repository cannot be read at all,
    entry_error_texts for single malformed entries.
    """
    catalog_repository = CatalogRepository(directory_name=node_list_entry.directory_name,
                                           url=node_list_entry.url, branch=node_list_entry.branch)
    cache_path = get_catalog_cache_path(node_list_entry.directory_name)
    if not os.path.isdir(os.path.join(cache_path, '.git')):
        catalog_repository.error_text = 'not downloaded yet: refresh the catalog'
        return catalog_repository
    try:
        catalog_repository.commit_text = _run_git(['rev-parse', '--short', 'HEAD'], cache_path,
                                                  GIT_LOCAL_TIMEOUT_S).strip()
        file_paths = _run_git(['ls-tree', '-r', '--name-only', 'HEAD'], cache_path,
                              GIT_LOCAL_TIMEOUT_S).splitlines()
        package_names = set()
        dependency_package_names = set()
        for file_path in file_paths:
            if PACKAGE_MANIFEST_PATH_PATTERN.search(file_path):
                manifest_text = _read_committed_file_text(cache_path, file_path)
                package_name, package_dependency_names = _parse_package_manifest(manifest_text,
                                                                                 file_path)
                package_names.add(package_name)
                dependency_package_names.update(package_dependency_names)
        catalog_repository.package_names = sorted(package_names)
        catalog_repository.dependency_package_names = sorted(dependency_package_names
                                                             - package_names)
        for file_path in file_paths:
            entry_path_match = INDEX_ENTRY_PATH_PATTERN.search(file_path)
            if entry_path_match is None:
                continue
            resource_type, entry_name = entry_path_match.groups()
            try:
                catalog_repository.offers.append(_read_catalog_offer(
                    cache_path, file_path, resource_type, entry_name,
                    node_list_entry.directory_name))
            except RuntimeError as error:
                catalog_repository.entry_error_texts.append(str(error))
    except (RuntimeError, ValueError) as error:
        catalog_repository.error_text = str(error)
    return catalog_repository


def compute_install_plan(chosen_offers: list[CatalogOffer],
                         catalog_repositories: list[CatalogRepository],
                         installed_package_names: set[str]) -> InstallPlan:
    """
    Return the repositories and released packages that installing chosen_offers needs.

    Followed transitively: an offer needs its repository and its required packages; a repository
    needs the packages its package.xml files depend on. A needed package that a catalog repository
    provides adds that repository. One that is installed adds nothing. Any other package a camera
    type requires becomes a released package (rosdep key); any other package.xml dependency is
    left to rosdep, which installs released packages during the build anyway.
    """
    catalog_repository_by_name = {}
    providing_repository_name_by_package = {}
    for catalog_repository in catalog_repositories:
        catalog_repository_by_name[catalog_repository.directory_name] = catalog_repository
        for package_name in catalog_repository.package_names:
            providing_repository_name_by_package[package_name] = catalog_repository.directory_name

    planned_repository_by_name = {}
    planned_ros_package_by_name = {}
    # (package name, display name of what needs it, whether a released package may provide it)
    pending_package_needs = []

    def add_repository(repository_name, needed_by_name):
        planned_repository = planned_repository_by_name.get(repository_name)
        if planned_repository is None:
            catalog_repository = catalog_repository_by_name[repository_name]
            planned_repository = PlannedRepository(
                directory_name=repository_name, url=catalog_repository.url,
                branch=catalog_repository.branch,
                is_cloned=os.path.isdir(os.path.join(NODES_SOURCE_FOLDER_PATH, repository_name)))
            planned_repository_by_name[repository_name] = planned_repository
            for dependency_package_name in catalog_repository.dependency_package_names:
                pending_package_needs.append((dependency_package_name, repository_name, False))
        if needed_by_name not in planned_repository.needed_by_names:
            planned_repository.needed_by_names.append(needed_by_name)

    for chosen_offer in chosen_offers:
        offer_display_name = chosen_offer.display_name or chosen_offer.name
        if chosen_offer.repository_directory_name is not None:
            add_repository(chosen_offer.repository_directory_name, offer_display_name)
        for required_package_name in chosen_offer.required_package_names:
            is_ros_package_candidate = (required_package_name
                                        in chosen_offer.ros_package_candidate_names)
            pending_package_needs.append((required_package_name, offer_display_name,
                                          is_ros_package_candidate))

    while pending_package_needs:
        package_name, needed_by_name, is_ros_package_candidate = pending_package_needs.pop(0)
        providing_repository_name = providing_repository_name_by_package.get(package_name)
        if providing_repository_name is not None:
            add_repository(providing_repository_name, needed_by_name)
        elif package_name in installed_package_names:
            continue
        elif is_ros_package_candidate:
            planned_ros_package = planned_ros_package_by_name.setdefault(
                package_name, PlannedRosPackage(ros_package_name=package_name))
            if needed_by_name not in planned_ros_package.needed_by_names:
                planned_ros_package.needed_by_names.append(needed_by_name)

    return InstallPlan(repositories=sorted(planned_repository_by_name.values(),
                                           key=lambda planned: planned.directory_name),
                       ros_packages=sorted(planned_ros_package_by_name.values(),
                                           key=lambda planned: planned.ros_package_name))


def _read_catalog_offer(cache_path: str, entry_file_path: str, resource_type: str,
                        entry_name: str, repository_name: str) -> CatalogOffer:
    """Return the offer of one ament index entry; RuntimeError when it is malformed."""
    error_start_text = f'the entry {entry_file_path} of {repository_name}'
    entry_text = _read_committed_file_text(cache_path, entry_file_path)
    offer_kind = OFFER_KIND_BY_RESOURCE_TYPE[resource_type]
    offer = CatalogOffer(kind=offer_kind, name=entry_name,
                         repository_directory_name=repository_name)
    if offer_kind == OFFER_KIND_APP:
        checked_entry = check_par_app_entry(
            parse_ament_index_entry_text(entry_text, error_start_text, 'templates/par_app/'),
            error_start_text)
        offer.required_package_names = checked_entry['required_launch_switches']
    elif offer_kind == OFFER_KIND_SENSOR_NODE:
        checked_entry = check_sensor_node_entry(
            parse_ament_index_entry_text(entry_text, error_start_text,
                                         'templates/sensor_processing_node_entry.yaml'),
            error_start_text)
        offer.required_package_names = checked_entry['required_sensor_nodes']
    else:
        checked_entry = check_camera_entry(
            parse_ament_index_entry_text(entry_text, error_start_text, 'templates/par_camera/'),
            error_start_text)
        # The launch file's package is usually this repository's own; a released driver comes
        # through required_packages
        camera_required_package_names = checked_entry[CAMERA_ENTRY_REQUIRED_PACKAGES_KEY]
        offer.required_package_names = camera_required_package_names + [checked_entry['package']]
        offer.ros_package_candidate_names = list(camera_required_package_names)
    offer.display_name = checked_entry['display_name']
    offer.description = checked_entry['description']
    return offer


def _parse_package_manifest(manifest_text: str, manifest_path: str) -> tuple[str, set[str]]:
    """Return a package.xml's package name and the packages it depends on; ValueError if broken."""
    try:
        manifest_root = ElementTree.fromstring(manifest_text)
    except ElementTree.ParseError as error:
        raise ValueError(f'{manifest_path} is no valid XML: {error}')
    package_name = (manifest_root.findtext('name') or '').strip()
    if not package_name:
        raise ValueError(f'{manifest_path} has no <name>')
    dependency_package_names = set()
    for tag_name in PACKAGE_DEPENDENCY_TAG_NAMES:
        for dependency_element in manifest_root.findall(tag_name):
            dependency_package_name = (dependency_element.text or '').strip()
            if dependency_package_name:
                dependency_package_names.add(dependency_package_name)
    return package_name, dependency_package_names


def _read_committed_file_text(cache_path: str, file_path: str) -> str:
    """Return a file of the clone's latest commit; git fetches it if it has not yet."""
    return _run_git(['show', f'HEAD:{file_path}'], cache_path, GIT_NETWORK_TIMEOUT_S)


def _run_git(git_arguments: list[str], working_folder_path: str, timeout_s: float) -> str:
    """
    Run git without a terminal and return its output; RuntimeError with git's message on failure.

    GIT_TERMINAL_PROMPT=0 and ssh's BatchMode make a missing key or password fail at once instead
    of waiting for an answer nobody can give.
    """
    git_environment = dict(os.environ, GIT_TERMINAL_PROMPT='0',
                           GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=15')
    try:
        git_process = subprocess.run(['git'] + git_arguments, cwd=working_folder_path,
                                     env=git_environment, capture_output=True, text=True,
                                     timeout=timeout_s, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'git {git_arguments[0]} took longer than {timeout_s:.0f} s')
    if git_process.returncode != 0:
        git_message_text = git_process.stderr.strip() or git_process.stdout.strip()
        raise RuntimeError(f'git {git_arguments[0]} failed: {git_message_text}')
    return git_process.stdout
