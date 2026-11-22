# Written by Claude Code
"""
Node catalog of the setup wizard: what the repositories of config/catalog_repos.list offer (apps,
camera types, sensor processing nodes), read from the repositories themselves before they are
installed, and which repositories and released packages installing a choice needs.

Each catalog repository is kept as a blob-less clone without a checkout in the user's cache folder
(git clone --depth 1 --filter=blob:none --no-checkout): only the latest commit's file list is
downloaded, and `git show` fetches just the files read here, the ament index entries
(resource/par_framework_*/<name>) and the package.xml files, wherever the packages sit in the
repository. The entries are checked with the same functions as installed ones
(par_framework_core), so the repository stays the one place that describes what it offers.
"""

import os
import re
import subprocess
from typing import NamedTuple
import xml.etree.ElementTree as ElementTree

from par_framework_core.ament_index_entries import parse_ament_index_entry_text
from par_framework_core.camera_types import (CAMERA_ENTRY_FORMAT_DOCUMENTATION_TEXT,
                                             CAMERA_ENTRY_REQUIRED_PACKAGES_KEY,
                                             CAMERA_RESOURCE_TYPE, check_camera_entry)
from par_framework_core.par_apps import (check_par_app_entry,
                                         PAR_APP_ENTRY_FORMAT_DOCUMENTATION_TEXT,
                                         PAR_APP_RESOURCE_TYPE)
from par_framework_core.sensor_nodes import (check_sensor_node_entry,
                                             SENSOR_NODE_ENTRY_FORMAT_DOCUMENTATION_TEXT,
                                             SENSOR_NODE_RESOURCE_TYPE)
from pydantic import BaseModel

# The repository this backend belongs to: setup_wizard/backend/install/ -> three folders up
REPOSITORY_ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
CATALOG_REPOS_LIST_PATH = os.path.join(REPOSITORY_ROOT_PATH, 'config', 'catalog_repos.list')
# Repositories the user added to the catalog by URL in the wizard (gitignored, format of
# required_repos.list)
USER_CATALOG_LIST_PATH = os.path.join(REPOSITORY_ROOT_PATH, 'config', 'user_catalog_repos.list')
USER_CATALOG_LIST_HEADER_TEXT = (
    '# Repositories added to the catalog in the setup wizard, next to config/catalog_repos.list\n'
    '# (gitignored; format of required_repos.list: <directory> <git-url> [branch])\n')
# What the wizard accepts as a repository URL: a URL git understands (https://, ssh://, git://,
# file://) or the scp-like form user@host:path that GitHub's SSH URLs use
REPOSITORY_URL_PATTERN = re.compile(r'(?:(?:https?|ssh|git|file)://\S+|[\w.-]+@[\w.-]+:\S+)')
# The lists scripts/local_build.sh installs from (scripts/common.sh): the tracked required list
# of repositories and the gitignored installed lists of what this installation added. Released
# packages have no required list: one every installation needs is declared in the package.xml of
# the package using it.
REQUIRED_REPOS_LIST_PATH = os.path.join(REPOSITORY_ROOT_PATH, 'config', 'required_repos.list')
INSTALLED_REPOS_LIST_PATH = os.path.join(REPOSITORY_ROOT_PATH, 'config', 'installed_repos.list')
INSTALLED_ROS_PACKAGES_LIST_PATH = os.path.join(REPOSITORY_ROOT_PATH, 'config',
                                                'installed_ros_packages.list')
INSTALLED_REPOS_LIST_HEADER_TEXT = (
    '# Node repositories this installation added to config/required_repos.list (gitignored;\n'
    '# written by the setup wizard, format of required_repos.list: <directory> <git-url>\n'
    '# [branch])\n')
INSTALLED_ROS_PACKAGES_LIST_HEADER_TEXT = (
    '# Released packages this installation uses, e.g. camera drivers (gitignored; written by\n'
    '# the setup wizard). One rosdep key per line, e.g. v4l2_camera; scripts/local_build.sh\n'
    '# installs them. Find a key with: rosdep resolve <key>\n')
# One rosdep key, the same rule as read_ros_packages_list in scripts/common.sh
ROS_PACKAGE_KEY_PATTERN = re.compile(r'[A-Za-z0-9_.-]+')
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
    # The package whose package.xml version is shown as the offer's version: the app's or sensor
    # node's own package; for a camera its driver, the first of its required packages, else the
    # package of its launch file. Empty when there is none
    version_package_name: str = ''


class CatalogRepository(BaseModel):
    directory_name: str
    url: str
    branch: str | None = None
    # The ROS packages in the repository, from its package.xml files
    package_names: list[str] = []
    # The <version> of each of its packages, by package name
    package_version_by_name: dict[str, str] = {}
    # Packages its package.xml files depend on, without its own
    dependency_package_names: list[str] = []
    offers: list[CatalogOffer] = []
    # Entries that could not be read or are malformed, as error texts
    entry_error_texts: list[str] = []
    # Why the repository could not be read at all, e.g. git's message; None when it could
    error_text: str | None = None
    # True for a repository the user added (config/user_catalog_repos.list), which the user can
    # remove
    is_user_added: bool = False


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
    Return the entries of a file in the required_repos.list format, the same rules as
    scripts/common.sh.

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


def read_catalog_list_entries() -> list[NodeListEntry]:
    """
    Return the catalog's repositories: config/catalog_repos.list, then
    config/user_catalog_repos.list when it exists. Raises OSError or ValueError when a list
    cannot be read or names a directory twice.
    """
    catalog_list_entries = read_node_list_file(CATALOG_REPOS_LIST_PATH)
    if os.path.isfile(USER_CATALOG_LIST_PATH):
        catalog_list_entries += read_node_list_file(USER_CATALOG_LIST_PATH)
    listed_directory_names = set()
    for node_list_entry in catalog_list_entries:
        if node_list_entry.directory_name in listed_directory_names:
            raise ValueError(f'{node_list_entry.directory_name} is listed twice in '
                             f'{CATALOG_REPOS_LIST_PATH} and {USER_CATALOG_LIST_PATH}')
        listed_directory_names.add(node_list_entry.directory_name)
    return catalog_list_entries


def read_user_catalog_directory_names() -> set[str]:
    """Return the directories of config/user_catalog_repos.list; empty when it does not exist."""
    if not os.path.isfile(USER_CATALOG_LIST_PATH):
        return set()
    directory_names = set()
    for node_list_entry in read_node_list_file(USER_CATALOG_LIST_PATH):
        directory_names.add(node_list_entry.directory_name)
    return directory_names


def add_user_catalog_repository(url: str, branch: str | None) -> NodeListEntry:
    """
    Add a repository to config/user_catalog_repos.list, its directory named after the URL's last
    part (e.g. my_app for https://github.com/someone/my_app.git). Returns the new entry.

    Raises ValueError for a URL or branch git must not get, or a directory name that core, the
    catalog or the user list has already; OSError when the list cannot be written.
    """
    url = url.strip()
    if not REPOSITORY_URL_PATTERN.fullmatch(url) or not NODE_LIST_VALUE_PATTERN.fullmatch(url):
        raise ValueError(f'{url!r} is no repository URL, e.g. '
                         f'https://github.com/<owner>/<repo>.git or '
                         f'git@github.com:<owner>/<repo>.git')
    if branch is not None:
        branch = branch.strip() or None
    if branch is not None and not NODE_LIST_VALUE_PATTERN.fullmatch(branch):
        raise ValueError(f'{branch!r} is no branch name')
    # The last part of the path, after '/' or the ':' of user@host:path
    url_last_part = re.split(r'[/:]', url.rstrip('/'))[-1]
    if url_last_part.endswith('.git'):
        url_last_part = url_last_part[:-len('.git')]
    directory_name = re.sub(r'[^A-Za-z0-9_.-]', '_', url_last_part).lstrip('.-')
    if not NODE_LIST_DIRECTORY_NAME_PATTERN.fullmatch(directory_name):
        raise ValueError(f'No folder name can be made from {url!r}')
    taken_directory_names = set()
    required_and_catalog_entries = (read_node_list_file(REQUIRED_REPOS_LIST_PATH)
                                    + read_catalog_list_entries())
    for node_list_entry in required_and_catalog_entries:
        taken_directory_names.add(node_list_entry.directory_name)
    if directory_name in taken_directory_names:
        raise ValueError(f'A repository named {directory_name} is listed already')
    line_words = [directory_name, url]
    if branch is not None:
        line_words.append(branch)
    _append_lines_to_list_file(USER_CATALOG_LIST_PATH, USER_CATALOG_LIST_HEADER_TEXT,
                               [' '.join(line_words)])
    return NodeListEntry(directory_name, url, branch)


def remove_user_catalog_repository(directory_name: str) -> None:
    """
    Remove a repository from config/user_catalog_repos.list, keeping the other lines and comments.
    An installed copy stays installed. Raises KeyError when the list does not have it.
    """
    if directory_name not in read_user_catalog_directory_names():
        raise KeyError(directory_name)
    with open(USER_CATALOG_LIST_PATH) as list_file:
        line_texts = list_file.readlines()
    kept_line_texts = []
    for line_text in line_texts:
        words = line_text.split('#', 1)[0].split()
        if words and words[0] == directory_name:
            continue
        kept_line_texts.append(line_text)
    with open(USER_CATALOG_LIST_PATH, 'w') as list_file:
        list_file.writelines(kept_line_texts)


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
        file_paths = _run_git(['ls-tree', '-r', '--name-only', 'HEAD'], cache_path,
                              GIT_LOCAL_TIMEOUT_S).splitlines()
        package_names = set()
        dependency_package_names = set()
        for file_path in file_paths:
            if PACKAGE_MANIFEST_PATH_PATTERN.search(file_path):
                manifest_text = _read_committed_file_text(cache_path, file_path)
                package_name, package_version, package_dependency_names = (
                    parse_package_manifest(manifest_text, file_path))
                package_names.add(package_name)
                catalog_repository.package_version_by_name[package_name] = package_version
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


def add_install_plan_to_installed_lists(install_plan: InstallPlan) -> None:
    """
    Add the plan's repositories and released packages to the installed lists, which
    scripts/local_build.sh installs next to the required list. Creates a missing installed list.

    What a required or installed list has already is not added again, so a plan can be added
    twice, e.g. when an install is continued. Raises OSError when a list cannot be read or
    written, ValueError when one is malformed or a package name is no rosdep key.
    """
    listed_directory_names = set()
    for list_path in (REQUIRED_REPOS_LIST_PATH, INSTALLED_REPOS_LIST_PATH):
        if os.path.isfile(list_path):
            for node_list_entry in read_node_list_file(list_path):
                listed_directory_names.add(node_list_entry.directory_name)
    new_node_list_lines = []
    for planned_repository in install_plan.repositories:
        if planned_repository.directory_name in listed_directory_names:
            continue
        line_words = [planned_repository.directory_name, planned_repository.url]
        if planned_repository.branch is not None:
            line_words.append(planned_repository.branch)
        new_node_list_lines.append(' '.join(line_words))

    listed_ros_package_names = set()
    if os.path.isfile(INSTALLED_ROS_PACKAGES_LIST_PATH):
        installed_ros_package_names = _read_ros_packages_list_file(
            INSTALLED_ROS_PACKAGES_LIST_PATH)
        listed_ros_package_names.update(installed_ros_package_names)
    new_ros_package_lines = []
    for planned_ros_package in install_plan.ros_packages:
        ros_package_name = planned_ros_package.ros_package_name
        if not ROS_PACKAGE_KEY_PATTERN.fullmatch(ros_package_name):
            raise ValueError(f'{ros_package_name!r} is no rosdep key')
        if ros_package_name not in listed_ros_package_names:
            new_ros_package_lines.append(ros_package_name)

    _append_lines_to_list_file(INSTALLED_REPOS_LIST_PATH, INSTALLED_REPOS_LIST_HEADER_TEXT,
                               new_node_list_lines)
    _append_lines_to_list_file(INSTALLED_ROS_PACKAGES_LIST_PATH,
                               INSTALLED_ROS_PACKAGES_LIST_HEADER_TEXT, new_ros_package_lines)


def _read_ros_packages_list_file(list_path: str) -> list[str]:
    """Return the keys of a file in installed_ros_packages.list's format; ValueError if bad."""
    ros_package_names = []
    with open(list_path) as list_file:
        for line_number, line_text in enumerate(list_file, start=1):
            words = line_text.split('#', 1)[0].split()
            if not words:
                continue
            if len(words) > 1 or not ROS_PACKAGE_KEY_PATTERN.fullmatch(words[0]):
                raise ValueError(f'{list_path} line {line_number}: expected one rosdep key')
            ros_package_names.append(words[0])
    return ros_package_names


def _append_lines_to_list_file(list_path: str, header_text: str, new_lines: list[str]) -> None:
    """Append lines to a list file; a missing file is created with header_text first."""
    if not new_lines:
        return
    is_new_file = not os.path.isfile(list_path)
    with open(list_path, 'a+') as list_file:
        if is_new_file:
            list_file.write(header_text)
        else:
            # A last line without a line break would merge with the first new one
            list_file.seek(0)
            existing_text = list_file.read()
            if existing_text and not existing_text.endswith('\n'):
                list_file.write('\n')
        for new_line in new_lines:
            list_file.write(new_line + '\n')


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
            parse_ament_index_entry_text(entry_text, error_start_text,
                                         PAR_APP_ENTRY_FORMAT_DOCUMENTATION_TEXT),
            error_start_text)
        offer.required_package_names = checked_entry['required_launch_switches']
        offer.version_package_name = entry_name
    elif offer_kind == OFFER_KIND_SENSOR_NODE:
        checked_entry = check_sensor_node_entry(
            parse_ament_index_entry_text(entry_text, error_start_text,
                                         SENSOR_NODE_ENTRY_FORMAT_DOCUMENTATION_TEXT),
            error_start_text)
        offer.required_package_names = checked_entry['required_sensor_nodes']
        offer.version_package_name = entry_name
    else:
        checked_entry = check_camera_entry(
            parse_ament_index_entry_text(entry_text, error_start_text,
                                         CAMERA_ENTRY_FORMAT_DOCUMENTATION_TEXT),
            error_start_text)
        # The launch file's package is usually this repository's own; a released driver comes
        # through required_packages
        camera_required_package_names = checked_entry[CAMERA_ENTRY_REQUIRED_PACKAGES_KEY]
        offer.required_package_names = camera_required_package_names + [checked_entry['package']]
        offer.ros_package_candidate_names = list(camera_required_package_names)
        offer.version_package_name = get_camera_version_package_name(
            camera_required_package_names, checked_entry['package'])
    offer.display_name = checked_entry['display_name']
    offer.description = checked_entry['description']
    return offer


def get_camera_version_package_name(required_package_names: list[str],
                                    launch_package_name: str) -> str:
    """Return the package whose version a camera type shows: its driver, else its launch file's."""
    if required_package_names:
        return required_package_names[0]
    return launch_package_name


def parse_package_manifest(manifest_text: str,
                           manifest_path: str) -> tuple[str, str, set[str]]:
    """
    Return a package.xml's package name, its version (empty without <version>) and the packages
    it depends on; ValueError when it is broken.
    """
    try:
        manifest_root = ElementTree.fromstring(manifest_text)
    except ElementTree.ParseError as error:
        raise ValueError(f'{manifest_path} is no valid XML: {error}')
    package_name = (manifest_root.findtext('name') or '').strip()
    if not package_name:
        raise ValueError(f'{manifest_path} has no <name>')
    package_version = (manifest_root.findtext('version') or '').strip()
    dependency_package_names = set()
    for tag_name in PACKAGE_DEPENDENCY_TAG_NAMES:
        for dependency_element in manifest_root.findall(tag_name):
            dependency_package_name = (dependency_element.text or '').strip()
            if dependency_package_name:
                dependency_package_names.add(dependency_package_name)
    return package_name, package_version, dependency_package_names


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
