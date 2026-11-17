# Written by Claude Code
"""
Profile files for the setup wizard backend: reading and writing config/profiles/<name>.yaml.

A profile holds only what differs from par_setup.yaml, as ROS 2 parameter file sections keyed by
node name. Reading goes through launch_helpers wherever a launch reads the same (par_launch, the
cameras), so the wizard sees a profile exactly as `par.launch.py profile:=<name>` does. Writing
(write_node_settings_into_profile) keeps a key only where it differs from par_setup.yaml and
rewrites the file with ruamel.yaml's round trip, keeping the comments, quotes and layout of a
hand-written profile; the helpers below it move the empty lines and comments ruamel.yaml stores
with the last line of a section, so adding or deleting keys and sections does not tear them from
the section they belong to. Also the par_launch values of the apps (par_launch.apps, rviz,
app_inputs), which several APIs read and write.
"""

import datetime
import os
import re
import shutil
import tempfile
import threading

from fastapi import HTTPException
from launch import LaunchContext
from par_framework_core.launch_helpers import (FILE_NAME_PART_PATTERN, FOLDER_PATH_PROFILES,
                                               get_camera_namespace,
                                               get_installed_par_setup_path,
                                               get_path_in_config_folder, get_profile_file_path,
                                               PAR_LAUNCH_APP_INPUTS_KEY,
                                               PAR_LAUNCH_CAMERAS_KEY, ProfileCamera,
                                               PROFILE_FILE_EXTENSION, read_launch_section,
                                               read_profile_cameras)
from pydantic import BaseModel
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import CommentMark
from ruamel.yaml.tokens import CommentToken
import yaml

# Deleted profiles and removed cameras' files are moved here
# (config/profiles/.deleted/<name>_<time>/); profile listings skip it, since it is a folder, not
# a .yaml file.
DELETED_PROFILES_FOLDER_NAME = '.deleted'
# In the folder of a removed camera: its node sections (/cameras/<camera name>/...) taken out of
# the profile, so a new camera of the same name does not inherit them
DELETED_NODE_SECTIONS_FILE_NAME = 'node_sections.yaml'
# What reading a profile raises when it is broken (written by hand): a missing or malformed key,
# an unreadable file, invalid YAML
PROFILE_READ_ERROR_TYPES = (RuntimeError, KeyError, OSError, yaml.YAMLError)

# Why a profile without cameras cannot run; a launch refuses it too
# (launch_helpers.read_profile_cameras)
NO_CAMERA_TO_RUN_TEXT = 'The profile has no camera yet: add one in the Cameras area first'

# par.launch.py's switch for RViz with rviz_bridge. The Apps area lists RViz as an app under this
# name (apps_api.py), stored as this switch instead of in par_launch.apps.
RVIZ_LAUNCH_SWITCH_NAME = 'rviz'
# The node section of the launch files' own values
PAR_LAUNCH_NODE_NAME = '/par_launch'

# The key under each node section of a ROS 2 parameter file
ROS_PARAMETERS_KEY = 'ros__parameters'
# Written above a node section the wizard adds to a profile; the leading empty line separates it
# from the section before, as in the hand-written profiles
ADDED_NODE_SECTION_COMMENT = '\nSaved by the setup wizard'
# In ruamel.yaml's comment record of a key, the position of what follows its value
RUAMEL_COMMENT_AFTER_VALUE_INDEX = 2
# In ruamel.yaml's comment record of a sequence item, the position of what follows the item
RUAMEL_COMMENT_AFTER_SEQUENCE_ITEM_INDEX = 0
# Long lines (e.g. a page app's command) stay on one line instead of being wrapped on rewrite
PROFILE_YAML_LINE_WIDTH_CHARACTERS = 4096

# One rewrite of a profile file at a time; requests run in a thread pool.
_profile_write_lock = threading.Lock()


class DeletedProfileResponse(BaseModel):
    # Where the profile file and its extrinsics were moved to, to restore them by hand; '' when a
    # removed camera had no files to move
    deleted_profile_folder_path: str


class NodeSettingsWriteResult(BaseModel):
    # The node's section in the profile the settings were written to
    node_section_name: str
    # Written into the profile, because they differ from par_setup.yaml
    written_setting_names: list[str]
    # Removed from the profile (or never written), because par_setup.yaml has the same value
    removed_setting_names: list[str]


def read_profile_names() -> list[str]:
    """Return the profile file names, sorted, without those that profile:= would reject."""
    profiles_folder_path = get_path_in_config_folder(FOLDER_PATH_PROFILES)
    if not os.path.isdir(profiles_folder_path):
        return []
    profile_names = []
    for file_name in os.listdir(profiles_folder_path):
        profile_name, file_extension = os.path.splitext(file_name)
        if file_extension != PROFILE_FILE_EXTENSION:
            continue
        if not FILE_NAME_PART_PATTERN.fullmatch(profile_name):
            continue
        profile_names.append(profile_name)
    return sorted(profile_names)


def check_profile_exists(profile_name: str) -> None:
    """Raise 404 unless profile_name names a saved profile, e.g. before it reaches profile:=."""
    if profile_name not in read_profile_names():
        raise HTTPException(status_code=404, detail=f'No profile named {profile_name!r}')


def create_profile_launch_context(profile_name: str) -> LaunchContext:
    """Return a launch context like `ros2 launch ... par.launch.py profile:=<profile_name>`."""
    # So launch_helpers merges par_setup.yaml and the profile exactly as a launch does.
    profile_launch_context = LaunchContext()
    default_params_file_path = get_installed_par_setup_path()
    profile_launch_context.launch_configurations['params_file'] = default_params_file_path
    profile_launch_context.launch_configurations['profile'] = profile_name
    # No per-run override, as in a launch without projector_display_id:=
    profile_launch_context.launch_configurations['projector_display_id'] = ''
    return profile_launch_context


def read_profile_launch_section(profile_name: str) -> dict:
    """Return the profile's par_launch section as a launch reads it; 404 or 409 when it cannot."""
    check_profile_exists(profile_name)
    profile_launch_context = create_profile_launch_context(profile_name)
    try:
        return read_launch_section(profile_launch_context)
    except PROFILE_READ_ERROR_TYPES as error:
        raise HTTPException(status_code=409,
                            detail=f'Cannot read the profile {profile_name}: {error}') from error


def read_profile_cameras_or_raise(profile_name: str) -> list[ProfileCamera]:
    """Return the profile's cameras (ProfileCamera), the main one first; 409 with the reason."""
    try:
        return read_profile_cameras_allowing_none(profile_name)
    except PROFILE_READ_ERROR_TYPES as error:
        raise HTTPException(status_code=409,
                            detail=f'Cannot read the cameras of {profile_name}: {error}'
                            ) from error


def read_profile_cameras_allowing_none(profile_name: str) -> list[ProfileCamera]:
    """
    Return the profile's cameras, the main one first; [] when the profile names none yet.

    A new profile starts with an empty par_launch.cameras and gets its cameras in the Cameras
    area. A launch refuses such a profile (launch_helpers.read_profile_cameras), so the wizard
    reads that case itself and leaves every other one, broken files included, to launch_helpers.
    Raises PROFILE_READ_ERROR_TYPES like read_profile_cameras.
    """
    profile_launch_parameters = read_profile_own_launch_parameters(profile_name)
    if profile_launch_parameters.get(PAR_LAUNCH_CAMERAS_KEY) == {}:
        return []
    return read_profile_cameras(create_profile_launch_context(profile_name))


def read_profile_own_launch_parameters(profile_name: str) -> dict:
    """
    Return the par_launch parameters the profile's own file sets, without par_setup.yaml's.

    {} when it sets none or its par_launch section is not a mapping; a broken file is left to the
    readers that go through launch_helpers. Raises OSError or yaml.YAMLError when unreadable.
    """
    with open(get_profile_file_path(profile_name)) as profile_file:
        profile_document = yaml.safe_load(profile_file) or {}
    if not isinstance(profile_document, dict):
        return {}
    launch_section = profile_document.get(PAR_LAUNCH_NODE_NAME.lstrip('/')) or {}
    if not isinstance(launch_section, dict):
        return {}
    profile_launch_parameters = launch_section.get(ROS_PARAMETERS_KEY) or {}
    if not isinstance(profile_launch_parameters, dict):
        return {}
    return profile_launch_parameters


def find_profile_camera(profile_cameras: list[ProfileCamera], camera_name: str) -> ProfileCamera:
    """Return the profile's camera of this name; HTTP 404 when it has none."""
    for profile_camera in profile_cameras:
        if profile_camera.camera_name == camera_name:
            return profile_camera
    raise HTTPException(status_code=404, detail=f'The profile has no camera {camera_name!r}')


def read_profile_node_settings(profile_name: str, full_node_name: str) -> dict:
    """Return the node's parameters as the profile sets them; {} when it sets none."""
    check_profile_exists(profile_name)
    profile_document = read_profile_document(profile_name)
    if not isinstance(profile_document, dict):
        raise HTTPException(status_code=409,
                            detail=f'{get_profile_file_path(profile_name)} holds no node sections')
    node_section_name = _find_node_section_name(profile_document, full_node_name)
    if node_section_name is None:
        return {}
    node_section = profile_document[node_section_name] or {}
    return node_section.get(ROS_PARAMETERS_KEY) or {}


def read_profile_document(profile_name: str):
    """Return the profile file's content as read by yaml.safe_load; {} for an empty file."""
    with open(get_profile_file_path(profile_name)) as profile_file:
        return yaml.safe_load(profile_file) or {}


def read_enabled_app_names(launch_section: dict) -> list[str]:
    """Return par_launch.apps as names, then RViz when par_launch.rviz is on; [] without any."""
    listed_app_names = launch_section.get('apps') or []
    if not isinstance(listed_app_names, list):
        raise RuntimeError(f'par_launch.apps must be a list of app names, not '
                           f'{listed_app_names!r}')
    enabled_app_names = [str(app_name) for app_name in listed_app_names]
    if launch_section.get(RVIZ_LAUNCH_SWITCH_NAME) is True:
        enabled_app_names.append(RVIZ_LAUNCH_SWITCH_NAME)
    return enabled_app_names


def read_camera_name_by_input_by_app(launch_section: dict) -> dict[str, dict[str, str]]:
    """Return par_launch.app_inputs; malformed parts are left out, the launch names them."""
    stored_app_inputs = launch_section.get(PAR_LAUNCH_APP_INPUTS_KEY)
    camera_name_by_input_by_app = {}
    if not isinstance(stored_app_inputs, dict):
        return camera_name_by_input_by_app
    for app_name, camera_name_by_input in stored_app_inputs.items():
        if not isinstance(camera_name_by_input, dict):
            continue
        checked_camera_name_by_input = {}
        for input_name, camera_name in camera_name_by_input.items():
            if isinstance(input_name, str) and isinstance(camera_name, str):
                checked_camera_name_by_input[input_name] = camera_name
        camera_name_by_input_by_app[str(app_name)] = checked_camera_name_by_input
    return camera_name_by_input_by_app


def write_app_inputs(profile_name: str,
                     camera_name_by_input_by_app: dict[str, dict[str, str]]) -> None:
    """Write par_launch.app_inputs, leaving out apps without a bound input."""
    stored_app_inputs = {}
    for app_name, camera_name_by_input in camera_name_by_input_by_app.items():
        if camera_name_by_input:
            stored_app_inputs[app_name] = camera_name_by_input
    # None removes the key once no app has a bound input
    stored_value = stored_app_inputs or None
    write_node_settings_into_profile(profile_name, PAR_LAUNCH_NODE_NAME,
                                     {PAR_LAUNCH_APP_INPUTS_KEY: stored_value})


def create_deleted_folder(folder_name_stem: str) -> str:
    """Create and return a new folder in config/profiles/.deleted/ for files moved out of use."""
    deletion_time_text = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    deleted_folder_path = get_path_in_config_folder(
        f'{FOLDER_PATH_PROFILES}/{DELETED_PROFILES_FOLDER_NAME}/'
        f'{folder_name_stem}_{deletion_time_text}')
    os.makedirs(deleted_folder_path)
    return deleted_folder_path


def find_camera_node_section_names(profile_document, camera_name: str) -> list[str]:
    """Return the profile's sections of nodes in the camera's namespace, spelt as in the file."""
    if not isinstance(profile_document, dict):
        return []
    camera_namespace_prefix = f'{get_camera_namespace(camera_name)}/'
    section_names = []
    for section_name in profile_document:
        if not isinstance(section_name, str):
            continue
        # The file may spell a node with or without its leading /
        full_section_name = '/' + section_name.lstrip('/')
        if full_section_name.startswith(camera_namespace_prefix):
            section_names.append(section_name)
    return section_names


def move_camera_node_sections(profile_name: str, camera_name: str,
                              deleted_folder_path: str) -> None:
    """
    Move the camera's node sections from the profile into DELETED_NODE_SECTIONS_FILE_NAME.

    The file in deleted_folder_path is written before the profile, so a failure loses nothing. The
    comments above the sections are written at the top of that file.
    """
    profile_path = get_profile_file_path(profile_name)
    round_trip_yaml = _create_round_trip_yaml()
    with _profile_write_lock:
        with open(profile_path) as profile_file:
            profile_document = round_trip_yaml.load(profile_file)
        section_names = find_camera_node_section_names(profile_document, camera_name)
        if not section_names:
            return
        removed_sections = CommentedMap()
        leading_texts = []
        for section_name in section_names:
            removed_sections[section_name] = profile_document[section_name]
            leading_texts.append(_delete_section_keeping_following_comment(profile_document,
                                                                           section_name))
        # The comments written above the removed sections go with them, before their sections
        deleted_sections_path = os.path.join(deleted_folder_path, DELETED_NODE_SECTIONS_FILE_NAME)
        with open(deleted_sections_path, 'w') as deleted_sections_file:
            for leading_text in leading_texts:
                if leading_text.strip():
                    deleted_sections_file.write(leading_text)
            round_trip_yaml.dump(removed_sections, deleted_sections_file)
        _replace_file_contents(profile_path, round_trip_yaml, profile_document)


def write_node_settings_into_profile(profile_name: str, full_node_name: str,
                                     setting_value_by_name: dict,
                                     always_written_setting_names: tuple = (),
                                     added_node_section_comment: str = ADDED_NODE_SECTION_COMMENT
                                     ) -> NodeSettingsWriteResult:
    """
    Write settings of a node into the profile, as ROS reads them at the node's next start.

    Only what differs from par_setup.yaml is kept, as in a hand-written profile: a value equal
    to par_setup.yaml's removes its key, except for always_written_setting_names. A value None
    removes its key too. The file is rewritten with ruamel.yaml's round trip, which keeps
    comments, quotes and layout of everything else. added_node_section_comment goes above the
    node's section when this call adds it (one line per line, a leading newline as empty line).
    """
    check_profile_exists(profile_name)
    profile_path = get_profile_file_path(profile_name)
    default_setting_value_by_name = read_par_setup_node_settings(full_node_name)
    round_trip_yaml = _create_round_trip_yaml()
    with _profile_write_lock:
        profile_document = _load_profile_document_for_writing(profile_path, round_trip_yaml)
        node_section_name = _find_node_section_name(profile_document, full_node_name)
        if node_section_name is None:
            # A namespaced node needs its full name; ROS silently ignores a bare one
            node_section_name = full_node_name
        node_section = _get_mapping_or_create(profile_document.get(node_section_name))
        node_parameters = _get_mapping_or_create(node_section.get(ROS_PARAMETERS_KEY))
        written_setting_names, removed_setting_names = _set_node_parameters(
            node_parameters, setting_value_by_name, default_setting_value_by_name,
            always_written_setting_names)
        _store_node_section(profile_document, node_section_name, node_section, node_parameters,
                            added_node_section_comment)
        _replace_file_contents(profile_path, round_trip_yaml, profile_document)

    return NodeSettingsWriteResult(node_section_name=node_section_name,
                                   written_setting_names=written_setting_names,
                                   removed_setting_names=removed_setting_names)


def _load_profile_document_for_writing(profile_path: str, round_trip_yaml: YAML) -> CommentedMap:
    """Return the profile as ruamel.yaml's round-trip mapping; 409 when it holds no sections."""
    with open(profile_path) as profile_file:
        profile_document = round_trip_yaml.load(profile_file)
    if profile_document is None:
        profile_document = CommentedMap()
    if not isinstance(profile_document, CommentedMap):
        raise HTTPException(status_code=409,
                            detail=f'{profile_path} holds no node sections; fix it by hand '
                                   f'before saving settings into it')
    return profile_document


def _get_mapping_or_create(yaml_value):
    """Return yaml_value when it is a mapping, else a new empty one to fill."""
    if not isinstance(yaml_value, dict):
        return CommentedMap()
    return yaml_value


def _set_node_parameters(node_parameters, setting_value_by_name: dict,
                         default_setting_value_by_name: dict,
                         always_written_setting_names: tuple) -> tuple[list[str], list[str]]:
    """Write or remove each setting in node_parameters; return the written and removed names."""
    written_setting_names = []
    removed_setting_names = []
    for setting_name, setting_value in setting_value_by_name.items():
        # Simplification: settings are written flat (image_raw.jpeg_quality), so one written
        # nested in the profile by hand is not found and stays as well; ROS then takes the
        # later one. Upgrade: look up dotted names in nested sections too.
        is_removed = _is_par_setup_value(setting_name, setting_value,
                                         default_setting_value_by_name)
        if setting_name in always_written_setting_names:
            is_removed = False
        if is_removed:
            if setting_name in node_parameters:
                _delete_key_keeping_comment_after_section(node_parameters, setting_name)
            removed_setting_names.append(setting_name)
        elif setting_name in node_parameters:
            node_parameters[setting_name] = setting_value
            written_setting_names.append(setting_name)
        else:
            _add_key_keeping_comment_after_section(node_parameters, setting_name, setting_value)
            written_setting_names.append(setting_name)
    return written_setting_names, removed_setting_names


def _is_par_setup_value(setting_name: str, setting_value,
                        default_setting_value_by_name: dict) -> bool:
    """Tell whether a setting needs no key in the profile: None, or par_setup.yaml's value."""
    # None asks for the key to be removed, e.g. a list with no entry left
    if setting_value is None:
        return True
    if setting_name not in default_setting_value_by_name:
        return False
    return _is_same_value(default_setting_value_by_name[setting_name], setting_value)


def _store_node_section(profile_document: CommentedMap, node_section_name: str, node_section,
                        node_parameters, added_node_section_comment: str) -> None:
    """Put the node's parameters into the profile; drop a section left with nothing in it."""
    if node_parameters:
        node_section[ROS_PARAMETERS_KEY] = node_parameters
        is_new_node_section = node_section_name not in profile_document
        profile_document[node_section_name] = node_section
        if is_new_node_section:
            profile_document.yaml_set_comment_before_after_key(
                node_section_name, before=added_node_section_comment)
    elif node_section_name in profile_document:
        # Nothing left that differs; a section with other keys besides the parameters stays
        if ROS_PARAMETERS_KEY in node_section:
            del node_section[ROS_PARAMETERS_KEY]
        if not node_section:
            del profile_document[node_section_name]


def _add_key_keeping_comment_after_section(yaml_mapping: CommentedMap, key: str,
                                           value) -> None:
    """Add key at the end; what follows the old last key's line moves after the new key."""
    # ruamel.yaml stores the empty lines and comments before the next section with the last key
    # of this one, so a key appended after it would land below them, inside the next section's
    # comment. A comment on the old last key's own line stays with it
    keys = list(yaml_mapping.keys())
    yaml_mapping[key] = value
    if not keys:
        return
    following_text = _take_text_after_value_line(yaml_mapping, keys[-1])
    _append_text_after_value_line(yaml_mapping, key, following_text)


def _delete_key_keeping_comment_after_section(yaml_mapping: CommentedMap, key: str) -> None:
    """Delete key; what follows the last key's line moves to the new last key."""
    # Without this, deleting a section's last setting also deletes the empty lines and comments
    # that separate the section from the next one. A comment on the deleted key's own line
    # belonged to it and goes with it
    keys = list(yaml_mapping.keys())
    is_last_key = keys[-1] == key
    following_text = ''
    if is_last_key:
        following_text = _take_text_after_value_line(yaml_mapping, key)
    del yaml_mapping[key]
    if is_last_key and len(keys) >= 2:
        _append_text_after_value_line(yaml_mapping, keys[-2], following_text)


def _delete_section_keeping_following_comment(profile_document: CommentedMap,
                                              section_name: str) -> str:
    """
    Delete a node section; return the empty lines and comments written above it.

    What follows the section (the next section's comment) takes the place of that text.
    """
    # ruamel.yaml stores the text between two sections with the last line of the section before,
    # so deleting a section alone would delete the next section's comment, and leave its own
    # above the next section.
    # Simplification: the first section of a file has nothing before it to carry the following
    # text, which then leaves with the deleted section; the first section is par_launch in every
    # profile the wizard writes. Upgrade: store it as the document's start comment
    section_names = list(profile_document.keys())
    section_index = section_names.index(section_name)
    if section_index == 0:
        del profile_document[section_name]
        return ''
    following_text = ''
    last_line_comment_slot = _find_last_line_comment_slot(profile_document[section_name])
    if last_line_comment_slot is not None:
        following_text = _take_text_after_line(*last_line_comment_slot)
    del profile_document[section_name]
    leading_text = ''
    previous_comment_slot = _find_last_line_comment_slot(
        profile_document[section_names[section_index - 1]])
    if previous_comment_slot is not None:
        leading_text = _take_text_after_line(*previous_comment_slot)
        _append_text_after_line(*previous_comment_slot, following_text)
    return leading_text


def _find_last_line_comment_slot(yaml_value) -> tuple[dict, object, int] | None:
    """
    Return where ruamel.yaml stores the text after yaml_value's last line; None for a scalar.

    As (comment items, key or index, position in its comment record), following nested mappings
    and sequences down to their last line.
    """
    last_line_comment_slot = None
    while True:
        if isinstance(yaml_value, CommentedMap) and yaml_value:
            last_key = list(yaml_value.keys())[-1]
            last_line_comment_slot = (yaml_value.ca.items, last_key,
                                      RUAMEL_COMMENT_AFTER_VALUE_INDEX)
            yaml_value = yaml_value[last_key]
        elif isinstance(yaml_value, CommentedSeq) and yaml_value:
            last_index = len(yaml_value) - 1
            last_line_comment_slot = (yaml_value.ca.items, last_index,
                                      RUAMEL_COMMENT_AFTER_SEQUENCE_ITEM_INDEX)
            yaml_value = yaml_value[last_index]
        else:
            return last_line_comment_slot


def _take_text_after_value_line(yaml_mapping: CommentedMap, key: str) -> str:
    """Remove and return what ruamel.yaml stores after the line of key's value ('' if nothing)."""
    return _take_text_after_line(yaml_mapping.ca.items, key, RUAMEL_COMMENT_AFTER_VALUE_INDEX)


def _append_text_after_value_line(yaml_mapping: CommentedMap, key: str,
                                  following_text: str) -> None:
    """Put following_text (empty lines, comments) after the line of key's value."""
    _append_text_after_line(yaml_mapping.ca.items, key, RUAMEL_COMMENT_AFTER_VALUE_INDEX,
                            following_text)


def _take_text_after_line(comment_items: dict, key, comment_index: int) -> str:
    """Remove and return the lines after a key's or item's line, from its comment record."""
    comment_record = comment_items.get(key)
    if comment_record is None:
        return ''
    comment_after_value = comment_record[comment_index]
    if comment_after_value is None:
        return ''
    # The text starts with what is left of the value's own line: a comment there, or only its
    # line break
    comment_text = comment_after_value.value
    line_end_index = comment_text.find('\n')
    if line_end_index < 0:
        return ''
    same_line_text = comment_text[:line_end_index + 1]
    following_text = comment_text[line_end_index + 1:]
    if same_line_text.strip():
        comment_record[comment_index] = CommentToken(
            same_line_text, comment_after_value.start_mark, None)
    else:
        comment_record[comment_index] = None
    return following_text


def _append_text_after_line(comment_items: dict, key, comment_index: int,
                            following_text: str) -> None:
    """Put following_text (empty lines, comments) after a key's or item's line."""
    if not following_text:
        return
    comment_record = comment_items.setdefault(key, [None, None, None, None])
    comment_after_value = comment_record[comment_index]
    if comment_after_value is None:
        # The leading line break ends the value's own line
        comment_record[comment_index] = CommentToken(
            '\n' + following_text, CommentMark(0), None)
        return
    comment_after_value.value = comment_after_value.value + following_text


def _create_round_trip_yaml() -> YAML:
    """Return a ruamel.yaml reader and writer that keeps a profile as it was written by hand."""
    round_trip_yaml = YAML()
    round_trip_yaml.preserve_quotes = True
    round_trip_yaml.width = PROFILE_YAML_LINE_WIDTH_CHARACTERS
    round_trip_yaml.indent(mapping=2, sequence=4, offset=2)
    return round_trip_yaml


def _find_node_section_name(parameter_document: dict, full_node_name: str) -> str | None:
    """Return the section of the node as the file spells it (with or without leading /)."""
    for section_name in parameter_document:
        if not isinstance(section_name, str):
            continue
        if '/' + section_name.lstrip('/') == full_node_name:
            return section_name
    return None


def read_par_setup_node_settings(full_node_name: str) -> dict:
    """
    Return the node's parameters in par_setup.yaml, the defaults a profile overrides.

    Every section that names the node counts, also a wildcard one such as
    /cameras/*/webcam_node; as in ROS, a later section's value wins.
    """
    with open(get_installed_par_setup_path()) as par_setup_file:
        par_setup_document = yaml.safe_load(par_setup_file) or {}
    node_parameters = {}
    for section_name, node_section in par_setup_document.items():
        if not isinstance(section_name, str) or not isinstance(node_section, dict):
            continue
        if not _does_node_section_match(section_name, full_node_name):
            continue
        node_parameters.update(node_section.get(ROS_PARAMETERS_KEY) or {})
    return node_parameters


def _does_node_section_match(section_name: str, full_node_name: str) -> bool:
    """
    Tell whether a parameter file section applies to the node, as rcl matches it.

    * stands for one name part, ** for any number of them, also none, e.g. /**/webcam_node.
    """
    section_pattern_text = ''
    for name_part in section_name.strip('/').split('/'):
        if name_part == '**':
            section_pattern_text += '(/[^/]+)*'
        elif name_part == '*':
            section_pattern_text += '/[^/]+'
        else:
            section_pattern_text += '/' + re.escape(name_part)
    return re.fullmatch(section_pattern_text, full_node_name) is not None


def _is_same_value(par_setup_value, setting_value) -> bool:
    """Compare like ROS: 5 and 5.0 are different parameter types, so not the same value."""
    if type(par_setup_value) is not type(setting_value):
        return False
    return par_setup_value == setting_value


def _replace_file_contents(file_path: str, round_trip_yaml: YAML, yaml_document) -> None:
    """Write the document to a hidden file next to file_path, then put it in place in one step."""
    # A crash or a full disk while writing leaves the old profile intact instead of half a file
    folder_path = os.path.dirname(file_path)
    with tempfile.NamedTemporaryFile('w', dir=folder_path, prefix='.', suffix='.saving',
                                     delete=False) as temporary_file:
        round_trip_yaml.dump(yaml_document, temporary_file)
        temporary_file_path = temporary_file.name
    shutil.copymode(file_path, temporary_file_path)
    os.replace(temporary_file_path, file_path)
