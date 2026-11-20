# Written by Claude Code
"""
The sensor processing nodes registered in the ament index, and which of them run on each camera.

Sensor processing nodes (detectors, page_locator, projection_mask, ...) register a marker file
share/ament_index/resource_index/par_framework_sensor_nodes/<package> whose content is the node's
entry, a YAML mapping (blueprint: templates/sensor_processing_node_entry.yaml of
ros2-par-framework). The package name is its par_launch switch; par.launch.py starts its
executable of the same name as node <package>_node.
"""

from ament_index_python.resources import get_resources
from par_framework_core.ament_index_entries import (check_entry_has_only_known_keys,
                                                    check_entry_text_keys, is_list_of_texts,
                                                    read_ament_index_entry)


SENSOR_NODE_RESOURCE_TYPE = 'par_framework_sensor_nodes'
SENSOR_NODE_ENTRY_TEXT_KEYS = ('display_name', 'description')
SENSOR_NODE_ENTRY_LIST_KEYS = ('required_sensor_nodes',)


def get_sensor_node_package_names():
    """Return the packages that registered a sensor processing node in the ament index, sorted."""
    return sorted(get_resources(SENSOR_NODE_RESOURCE_TYPE))


def get_sensor_node_name(sensor_node_package_name):
    """Return the node name par.launch.py gives a sensor node in its camera's namespace."""
    return f'{sensor_node_package_name}_node'


def read_sensor_node_entry(sensor_node_package_name):
    """
    Return the checked entry of an installed sensor processing node, with every key of the format.

    required_sensor_nodes is empty when left out. Raises RuntimeError naming the fix when the node
    is not installed or its entry is malformed.
    """
    entry, error_start_text = read_ament_index_entry(
        SENSOR_NODE_RESOURCE_TYPE, sensor_node_package_name, 'sensor node',
        get_sensor_node_package_names(), 'templates/sensor_processing_node_entry.yaml')
    return check_sensor_node_entry(entry, error_start_text)


# Separate from read_sensor_node_entry, so the setup wizard checks entries of repositories that are
# not installed yet the same way
def check_sensor_node_entry(entry, error_start_text):
    """
    Return a sensor processing node's entry (a mapping) checked, with every key of the format.

    required_sensor_nodes is empty when left out. Raises RuntimeError starting with
    error_start_text when a key is unknown, missing or of the wrong type.
    """
    known_keys = SENSOR_NODE_ENTRY_TEXT_KEYS + SENSOR_NODE_ENTRY_LIST_KEYS
    check_entry_has_only_known_keys(entry, known_keys, error_start_text)
    check_entry_text_keys(entry, SENSOR_NODE_ENTRY_TEXT_KEYS, error_start_text)
    checked_entry = {}
    for text_key in SENSOR_NODE_ENTRY_TEXT_KEYS:
        checked_entry[text_key] = entry[text_key]
    for list_key in SENSOR_NODE_ENTRY_LIST_KEYS:
        list_value = entry.get(list_key, [])
        if not is_list_of_texts(list_value):
            raise RuntimeError(f'{error_start_text}: {list_key} must be a list of package names')
        checked_entry[list_key] = list(list_value)
    return checked_entry


def add_required_sensor_nodes(selected_sensor_node_names):
    """
    Return the selected sensor nodes plus every node they need (required_sensor_nodes), sorted.

    Follows the requirements of the requirements too, e.g. gesture_detector -> hand_landmarks.
    Raises RuntimeError when a node needs one that is not installed.
    """
    sensor_node_names = set()
    pending_names = list(selected_sensor_node_names)
    while pending_names:
        sensor_node_name = pending_names.pop()
        if sensor_node_name in sensor_node_names:
            continue
        sensor_node_names.add(sensor_node_name)
        pending_names += read_sensor_node_entry(sensor_node_name)['required_sensor_nodes']
    return sorted(sensor_node_names)


def get_sensor_node_names_by_camera(camera_names_by_sensor_node, camera_names):
    """
    Return, per camera of camera_names, the sensor nodes that run on it, sorted.

    camera_names_by_sensor_node is par_launch's lists, {sensor node: [camera name]}. A camera
    runs the nodes listed for it plus every node they need (add_required_sensor_nodes): a node
    reads the outputs of its required ones in its own camera's namespace. Raises RuntimeError
    when a node needs one that is not installed.
    """
    sensor_node_names_by_camera = {}
    for camera_name in camera_names:
        listed_sensor_node_names = []
        for sensor_node_name, listed_camera_names in camera_names_by_sensor_node.items():
            if camera_name in listed_camera_names:
                listed_sensor_node_names.append(sensor_node_name)
        sensor_node_names_by_camera[camera_name] = add_required_sensor_nodes(
            listed_sensor_node_names)
    return sensor_node_names_by_camera
