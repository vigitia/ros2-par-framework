# Written by Claude Code
"""
The PAR apps registered in the ament index, their entries, and which cameras they read.

A PAR app registers an installed marker file
share/ament_index/resource_index/par_framework_apps/<package> whose content is the app's entry, a
YAML mapping (blueprint and format: templates/par_app/ of ros2-par-framework).
"""

import re

from ament_index_python.resources import get_resources
from par_framework_core.ament_index_entries import (check_entry_has_only_known_keys,
                                                    check_entry_text_keys, is_list_of_texts,
                                                    PLAIN_NAME_PATTERN, read_ament_index_entry)


PAR_APP_RESOURCE_TYPE = 'par_framework_apps'
PAR_APP_ENTRY_TEXT_KEYS = ('display_name', 'description')
# executable and launch_file: a plain name in the app's package (PLAIN_NAME_PATTERN)
PAR_APP_ENTRY_START_KEYS = ('executable', 'launch_file')
PAR_APP_ENTRY_LIST_KEYS = ('required_launch_switches', 'used_calibrations', 'settings_node_names')
# settings_node_names: the app's nodes whose parameters the setup wizard edits, as full ROS node
# names (namespace and name), e.g. /demo_app_node
PAR_APP_FULL_NODE_NAME_PATTERN = re.compile(r'(/[A-Za-z_][A-Za-z0-9_]*)+')
# What used_calibrations may name, so a misspelt name fails instead of never being reported missing
PAR_APP_CALIBRATION_NAMES = ('camera_intrinsics', 'camera_pose', 'projection_mapping',
                             'projector_center')
# Inputs: the cameras an app reads, each with the topic names below a camera's namespace it reads
# from it, e.g. {camera: [pages, camera_info]}. The app runs in the root namespace and
# par.launch.py remaps its names onto the camera bound to the input in par_launch.app_inputs: an
# app with one input reads the plain names (pages), an app with several inputs prefixes each with
# its input (tracking/pages, capture/image_raw)
PAR_APP_ENTRY_INPUTS_KEY = 'inputs'
PAR_APP_INPUT_NAME_PATTERN = re.compile(r'[a-z][a-z0-9_]*')
# A topic name relative to the camera's namespace, e.g. pages or image_raw/compressed
PAR_APP_INPUT_TOPIC_NAME_PATTERN = re.compile(r'[a-z][a-z0-9_]*(/[a-z][a-z0-9_]*)*')
# par_launch.app_inputs: per app, the camera name bound to each of its inputs,
# e.g. {demo_app: {camera: overhead}}
PAR_LAUNCH_APP_INPUTS_KEY = 'app_inputs'
# par_launch.apps: the apps a profile offers, from which the setup wizard's Run menu chooses the
# projector app
PAR_LAUNCH_APPS_KEY = 'apps'
# par_launch.projector_app chooses the one app on the projector: none or a PAR app's package
PROJECTOR_APP_NONE = 'none'


def get_par_app_package_names():
    """Return the packages that registered a PAR app in the ament index, sorted."""
    return sorted(get_resources(PAR_APP_RESOURCE_TYPE))


def read_offered_par_app_names(launch_section):
    """
    Return the installed PAR apps par_launch.apps offers, in its order.

    Other names (rviz, an app not installed) are left out. Raises
    RuntimeError naming the fix when par_launch.apps is no list.
    """
    listed_app_names = launch_section.get(PAR_LAUNCH_APPS_KEY) or []
    if not isinstance(listed_app_names, list):
        raise RuntimeError(f'[par_apps]: par_launch.{PAR_LAUNCH_APPS_KEY} must be a list of app '
                           f'names, e.g. {PAR_LAUNCH_APPS_KEY}: [demo_app], not '
                           f'{listed_app_names!r}')
    installed_app_names = get_par_app_package_names()
    offered_app_names = []
    for app_name in listed_app_names:
        if str(app_name) in installed_app_names:
            offered_app_names.append(str(app_name))
    return offered_app_names


def read_par_app_entry(app_package_name):
    """
    Return the checked entry of an installed PAR app, a dict with every key of the format.

    executable or launch_file is set, the other one is None; the lists are empty when left out.
    Raises RuntimeError naming the fix when the app is not installed or its entry is malformed.
    """
    entry, error_start_text = read_ament_index_entry(
        PAR_APP_RESOURCE_TYPE, app_package_name, 'PAR app', get_par_app_package_names(),
        'templates/par_app/')
    return check_par_app_entry(entry, error_start_text)


# Separate from read_par_app_entry, so the setup wizard checks entries of repositories that are not
# installed yet the same way
def check_par_app_entry(entry, error_start_text):
    """
    Return a PAR app's entry (a mapping) checked, a dict with every key of the format.

    executable or launch_file is set, the other one is None; the lists are empty when left out.
    Raises RuntimeError starting with error_start_text when a key is unknown, missing or of the
    wrong type.
    """
    known_keys = (PAR_APP_ENTRY_TEXT_KEYS + PAR_APP_ENTRY_START_KEYS + PAR_APP_ENTRY_LIST_KEYS
                  + (PAR_APP_ENTRY_INPUTS_KEY,))
    check_entry_has_only_known_keys(entry, known_keys, error_start_text)
    check_entry_text_keys(entry, PAR_APP_ENTRY_TEXT_KEYS, error_start_text)

    given_start_keys = [start_key for start_key in PAR_APP_ENTRY_START_KEYS if start_key in entry]
    if len(given_start_keys) != 1:
        raise RuntimeError(f'{error_start_text} needs exactly one of executable and launch_file')
    start_value = entry[given_start_keys[0]]
    # A file or program name in the package, never a path that could point elsewhere
    if not isinstance(start_value, str) or not PLAIN_NAME_PATTERN.fullmatch(start_value):
        raise RuntimeError(f'{error_start_text}: {given_start_keys[0]} must be a plain name '
                           f'without a path, e.g. example_app or example_app.launch.py')

    for list_key in PAR_APP_ENTRY_LIST_KEYS:
        if not is_list_of_texts(entry.get(list_key, [])):
            raise RuntimeError(f'{error_start_text}: {list_key} must be a list of names')
    invalid_node_names = []
    for settings_node_name in entry.get('settings_node_names', []):
        if not PAR_APP_FULL_NODE_NAME_PATTERN.fullmatch(settings_node_name):
            invalid_node_names.append(settings_node_name)
    if invalid_node_names:
        raise RuntimeError(f'{error_start_text}: settings_node_names must be full node names '
                           f'such as /example_app_node, not {invalid_node_names}')
    unknown_calibration_names = sorted(
        set(entry.get('used_calibrations', [])) - set(PAR_APP_CALIBRATION_NAMES))
    if unknown_calibration_names:
        raise RuntimeError(f'{error_start_text}: unknown used_calibrations '
                           f'{unknown_calibration_names}; known: '
                           f'{list(PAR_APP_CALIBRATION_NAMES)}')

    checked_entry = {}
    for text_key in PAR_APP_ENTRY_TEXT_KEYS:
        checked_entry[text_key] = entry[text_key]
    for start_key in PAR_APP_ENTRY_START_KEYS:
        checked_entry[start_key] = entry.get(start_key)
    for list_key in PAR_APP_ENTRY_LIST_KEYS:
        checked_entry[list_key] = list(entry.get(list_key, []))
    checked_entry[PAR_APP_ENTRY_INPUTS_KEY] = _check_par_app_inputs(
        entry.get(PAR_APP_ENTRY_INPUTS_KEY, {}), error_start_text)
    return checked_entry


def _check_par_app_inputs(inputs, error_start_text):
    """Return an app entry's inputs as {input name: [topic name, ...]}, checked."""
    example_text = 'e.g. inputs: {camera: [pages, camera_info]}'
    if not isinstance(inputs, dict):
        raise RuntimeError(f'{error_start_text}: {PAR_APP_ENTRY_INPUTS_KEY} must map each input '
                           f'to the topic names it reads, {example_text}')
    checked_inputs = {}
    for input_name, topic_names in inputs.items():
        if not isinstance(input_name, str) or not PAR_APP_INPUT_NAME_PATTERN.fullmatch(input_name):
            raise RuntimeError(f'{error_start_text}: input {input_name!r}: an input name may only '
                               f'hold lower case letters, digits and _, starting with a letter')
        is_list_of_topic_names = is_list_of_texts(topic_names) and bool(topic_names) and all(
            PAR_APP_INPUT_TOPIC_NAME_PATTERN.fullmatch(topic_name) for topic_name in topic_names)
        if not is_list_of_topic_names:
            raise RuntimeError(f'{error_start_text}: input {input_name} must list the topic names '
                               f'it reads below the namespace of the camera, without a leading /, '
                               f'{example_text}')
        checked_inputs[input_name] = list(topic_names)
    return checked_inputs


def get_app_input_camera_names(launch_section, app_name, app_inputs, profile_camera_names,
                               started_camera_names):
    """
    Return {input name: camera name} for every input of the app's entry.

    par_launch.app_inputs.<app>.<input> binds an input to a camera of par_launch.cameras; an
    input left unbound reads the only camera of the run. Raises RuntimeError naming the fix when
    a binding is malformed, names an unknown input or camera, or a camera this run does not
    start, and when an unbound input has several cameras to choose from.
    """
    example_text = f'e.g. {PAR_LAUNCH_APP_INPUTS_KEY}: {{{app_name}: {{<input>: <camera>}}}}'
    input_camera_name_by_app = launch_section.get(PAR_LAUNCH_APP_INPUTS_KEY, {})
    if not isinstance(input_camera_name_by_app, dict):
        raise RuntimeError(f'[par_apps]: par_launch.{PAR_LAUNCH_APP_INPUTS_KEY} must map each '
                           f'app to the cameras of its inputs, {example_text}')
    bound_camera_name_by_input = input_camera_name_by_app.get(app_name, {})
    error_start_text = f'[par_apps]: par_launch.{PAR_LAUNCH_APP_INPUTS_KEY}.{app_name}'
    if not isinstance(bound_camera_name_by_input, dict):
        raise RuntimeError(f'{error_start_text} must map each input to a camera, {example_text}')
    unknown_input_names = sorted(set(bound_camera_name_by_input) - set(app_inputs))
    if unknown_input_names:
        raise RuntimeError(f'{error_start_text} names the inputs {unknown_input_names}, which '
                           f'{app_name} does not have; its inputs: {list(app_inputs)}')

    camera_name_by_input = {}
    for input_name in app_inputs:
        bound_camera_name = bound_camera_name_by_input.get(input_name)
        if bound_camera_name is None:
            if len(started_camera_names) != 1:
                raise RuntimeError(f'{error_start_text}.{input_name} is not set, and this run '
                                   f'starts the cameras {started_camera_names}: bind the input '
                                   f'to one of them, {example_text}')
            camera_name_by_input[input_name] = started_camera_names[0]
            continue
        if bound_camera_name not in profile_camera_names:
            raise RuntimeError(f'{error_start_text}.{input_name}: {bound_camera_name!r} is no '
                               f'camera of par_launch.cameras; known: {profile_camera_names}')
        if bound_camera_name not in started_camera_names:
            raise RuntimeError(f'{error_start_text}.{input_name} reads {bound_camera_name}, '
                               f'which this run does not start (camera:='
                               f'{started_camera_names[0]}): start it too, or pass '
                               f'projector_app:={PROJECTOR_APP_NONE}')
        camera_name_by_input[input_name] = bound_camera_name
    return camera_name_by_input


def get_par_app_sensor_node_camera_names(par_app_entry, camera_name_by_input, main_camera_name,
                                         sensor_node_names):
    """
    Return {sensor node: [camera name]}: where the app's required sensor nodes run for it.

    They run on every camera the app reads (camera_name_by_input, from
    get_app_input_camera_names); an app without inputs reads no camera of its own, so they run on
    the main camera. Required launch switches that are no sensor node (rviz) are left out.
    par.launch.py starts them this way and the setup wizard shows them, so both follow this one
    rule.
    """
    # Simplification: the required sensor nodes run on every camera the app reads, also on a
    # camera whose input does not use them (e.g. markers on a capture camera). Upgrade: the entry
    # names the required sensor nodes per input
    app_camera_names = []
    for camera_name in camera_name_by_input.values():
        if camera_name not in app_camera_names:
            app_camera_names.append(camera_name)
    if not app_camera_names:
        app_camera_names = [main_camera_name]
    camera_names_by_sensor_node = {}
    for switch_name in par_app_entry['required_launch_switches']:
        if switch_name in sensor_node_names:
            camera_names_by_sensor_node[switch_name] = list(app_camera_names)
    return camera_names_by_sensor_node
