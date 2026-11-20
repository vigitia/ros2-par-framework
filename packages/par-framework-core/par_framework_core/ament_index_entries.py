# Written by Claude Code
"""
Reading and checking the entries packages register in the ament index.

Camera types, PAR apps and sensor processing nodes each register a marker file
share/ament_index/resource_index/<resource type>/<name> whose content is a YAML mapping. The
modules camera_types, par_apps and sensor_nodes check their own keys with the helpers here.
"""

import re

from ament_index_python.resources import get_resource
import yaml


# executable, launch_file, package and frame name parts: a name in a package, no path and no
# leading dot (not '..')
PLAIN_NAME_PATTERN = re.compile(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*')


def read_ament_index_entry(resource_type, package_name, entry_kind_text, installed_names,
                           format_documentation_text):
    """
    Return a package's entry under resource_type as (YAML mapping, error start text).

    The error start text names the entry, for the caller's key checks. Raises RuntimeError naming
    the fix when the package has no entry or it is no YAML mapping.
    """
    try:
        entry_text, _ = get_resource(resource_type, package_name)
    except LookupError:
        installed_names_text = ', '.join(installed_names) or 'none'
        raise RuntimeError(f'[ament_index_entries]: {package_name!r} is no installed '
                           f'{entry_kind_text} (installed: {installed_names_text}): add its repo '
                           f'from config/catalog_repos.list to config/installed_repos.list and '
                           f'run ./scripts/local_build.sh')
    error_start_text = (f'[ament_index_entries]: the {entry_kind_text} entry of {package_name} '
                        f'(share/ament_index/resource_index/{resource_type}/{package_name})')
    entry = parse_ament_index_entry_text(entry_text, error_start_text, format_documentation_text)
    return entry, error_start_text


# Separate from read_ament_index_entry, so the setup wizard checks entries read from a repository
# that is not installed yet the same way
def parse_ament_index_entry_text(entry_text, error_start_text, format_documentation_text):
    """
    Return an ament index entry's text loaded as a YAML mapping.

    error_start_text names the entry in the error, e.g. "the camera entry of brio (...)". Raises
    RuntimeError naming the fix when the text is no YAML mapping; the caller checks the keys.
    """
    # The entry comes from another repo: every key is checked by the caller, so a typo fails at
    # start instead of e.g. silently not starting a node
    try:
        entry = yaml.safe_load(entry_text)
    except yaml.YAMLError as error:
        raise RuntimeError(f'{error_start_text} is no valid YAML: {error}')
    if not isinstance(entry, dict):
        raise RuntimeError(f'{error_start_text} must be a YAML mapping, see '
                           f'{format_documentation_text}')
    return entry


def check_entry_has_only_known_keys(entry, known_keys, error_start_text):
    """Raise RuntimeError listing the known keys when entry has any other key, e.g. a typo."""
    unknown_keys = sorted(set(entry) - set(known_keys))
    if unknown_keys:
        raise RuntimeError(f'{error_start_text} has unknown keys {unknown_keys}; known: '
                           f'{list(known_keys)}')


def check_entry_text_keys(entry, text_keys, error_start_text):
    """Raise RuntimeError when one of text_keys is missing in entry or holds no text."""
    for text_key in text_keys:
        if not isinstance(entry.get(text_key), str):
            raise RuntimeError(f'{error_start_text} needs {text_key} as text')


def is_list_of_texts(list_value):
    """Return whether list_value is a list whose items are all texts (an empty list is one)."""
    if not isinstance(list_value, list):
        return False
    return all(isinstance(list_item, str) for list_item in list_value)
