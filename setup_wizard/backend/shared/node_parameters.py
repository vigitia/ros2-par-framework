# Written by Claude Code
"""
Node parameters for the setup wizard backend: a running node's parameters as settings.

Reads a node's parameters through the ROS 2 parameter services (list, describe, get) into
NodeSetting, the form the app edits them in, leaving out the parameters ROS 2 itself adds to every
node and image publisher, and converts a value from the app into a parameter's type. Used for the
previewed camera's driver (camera_preview_api.py), its intrinsics (intrinsics_api.py) and the
one-time settings reads of sensor nodes and apps (node_settings_api.py).
"""

import threading

from fastapi import HTTPException
from pydantic import BaseModel
from rcl_interfaces.msg import ParameterType
from rclpy.parameter import Parameter, parameter_value_to_python
from rclpy.parameter_client import AsyncParameterClient

# Every parameter of a node is shown as a setting, except those ROS 2 itself adds to nodes and
# image publishers: they say nothing about the node, whichever it is.
ROS_INFRASTRUCTURE_PARAMETER_NAMES = ('use_sim_time', 'start_type_description_service')
# rclcpp's QoS overrides of each topic, e.g.
# qos_overrides./cameras/overhead/image_raw.publisher.depth
ROS_INFRASTRUCTURE_PARAMETER_PREFIXES = ('qos_overrides.',)
# image_transport's choice of transports, e.g. raw.enable_pub_plugins
ROS_INFRASTRUCTURE_PARAMETER_SUFFIXES = ('.enable_pub_plugins',)
# image_transport plugins name their parameters <topic>.<plugin>.<setting>, e.g.
# image_raw.compressed.jpeg_quality.
# Simplification: the plugins shipped with ROS 2; a parameter of another plugin is shown as a
# camera setting. Upgrade: ask pluginlib for the installed image_transport plugins.
IMAGE_TRANSPORT_PLUGIN_NAMES = ('compressed', 'compressedDepth', 'theora', 'zstd', 'ffmpeg')
# How long to wait for a node's parameter services and each of their answers.
PARAMETER_SERVICE_TIMEOUT_S = 2.0
TYPE_NAME_BY_PARAMETER_TYPE = {
    ParameterType.PARAMETER_BOOL: 'bool',
    ParameterType.PARAMETER_INTEGER: 'integer',
    ParameterType.PARAMETER_DOUBLE: 'double',
    ParameterType.PARAMETER_STRING: 'string',
    ParameterType.PARAMETER_BYTE_ARRAY: 'byte array',
    ParameterType.PARAMETER_BOOL_ARRAY: 'bool array',
    ParameterType.PARAMETER_INTEGER_ARRAY: 'integer array',
    ParameterType.PARAMETER_DOUBLE_ARRAY: 'double array',
    ParameterType.PARAMETER_STRING_ARRAY: 'string array',
}


class NodeSetting(BaseModel):
    setting_name: str
    # bool, int, float, str, a list of those, or None while the parameter is not set
    setting_value: bool | int | float | str | list | None
    type_name: str
    description: str
    # The allowed range from the driver's descriptor; None without one
    minimum_value: float | None = None
    maximum_value: float | None = None
    step_value: float | None = None
    # The descriptor's free text on allowed values, e.g. the options of a menu; ROS gives it no
    # fixed format, so it is shown as a hint, empty without one.
    additional_constraints: str = ''
    is_read_only: bool
    # What "Reset to default" sets: the camera type's parameters_file value for a camera driver,
    # the node's own value without a profile for a sensor node or app; has_default_value is False
    # when it is not known
    has_default_value: bool = False
    default_value: bool | int | float | str | list | None = None


def get_node_parameter_client(camera_launch_session, full_node_name):
    """
    Return a parameter client for a node of the running launch, waiting for its services.

    The clients are kept in the camera launch session (camera_launch_session.py), one per node:
    rclpy's client cannot be destroyed on its own.
    """
    with camera_launch_session.session_lock:
        parameter_client = camera_launch_session.parameter_client_by_node_name.get(
            full_node_name)
        if parameter_client is None:
            parameter_client = AsyncParameterClient(camera_launch_session.preview_ros_node,
                                                    full_node_name)
            camera_launch_session.parameter_client_by_node_name[full_node_name] = (
                parameter_client)
    # Outside the lock: waiting for the node must not hold up the frames.
    if not parameter_client.wait_for_services(timeout_sec=PARAMETER_SERVICE_TIMEOUT_S):
        raise HTTPException(status_code=503,
                            detail=f'{full_node_name} does not answer yet; it may still be '
                                   f'starting')
    return parameter_client


def convert_setting_value(setting_value, parameter_type):
    """Return the value from the app in the parameter's type; 400 when it does not fit."""
    try:
        if parameter_type == Parameter.Type.BOOL and isinstance(setting_value, bool):
            return setting_value
        if parameter_type == Parameter.Type.INTEGER:
            return _convert_to_integer(setting_value)
        if parameter_type == Parameter.Type.DOUBLE:
            return float(setting_value)
        if parameter_type == Parameter.Type.STRING:
            return str(setting_value)
        if parameter_type == Parameter.Type.INTEGER_ARRAY:
            return [_convert_to_integer(element) for element in setting_value]
        if parameter_type == Parameter.Type.DOUBLE_ARRAY:
            return [float(element) for element in setting_value]
        if parameter_type == Parameter.Type.STRING_ARRAY:
            return [str(element) for element in setting_value]
        if parameter_type == Parameter.Type.BOOL_ARRAY:
            if all(isinstance(element, bool) for element in setting_value):
                return list(setting_value)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400,
                            detail=f'{setting_value!r} does not fit a {parameter_type.name} '
                                   f'setting: {error}') from error
    raise HTTPException(status_code=400,
                        detail=f'{setting_value!r} does not fit a {parameter_type.name} setting')


def _convert_to_integer(value):
    """Accept whole numbers only: silently cutting 2.5 to 2 would set another value than asked."""
    if isinstance(value, bool):
        raise ValueError('a bool is not a number')
    integer_value = int(value)
    if integer_value != value:
        raise ValueError(f'{value} is not a whole number')
    return integer_value


def convert_parameter_value_to_plain_python(parameter_value):
    """Return the parameter value as a plain Python value, which JSON and YAML can hold."""
    setting_value = parameter_value_to_python(parameter_value)
    # Array parameters arrive as array.array or similar
    if not isinstance(setting_value, (bool, int, float, str, type(None))):
        setting_value = list(setting_value)
    return setting_value


def read_node_settings(parameter_client):
    """Return every parameter of the node except ROS's own, sorted by name."""
    all_parameter_names = wait_for_service_answer(
        parameter_client.list_parameters()).result.names
    parameter_names = []
    for parameter_name in all_parameter_names:
        if not _is_ros_infrastructure_parameter(parameter_name):
            parameter_names.append(parameter_name)
    if not parameter_names:
        return []
    descriptors = wait_for_service_answer(
        parameter_client.describe_parameters(parameter_names)).descriptors
    parameter_values = wait_for_service_answer(
        parameter_client.get_parameters(parameter_names)).values
    settings = []
    named_parameters = zip(parameter_names, descriptors, parameter_values)
    for parameter_name, descriptor, parameter_value in named_parameters:
        settings.append(_create_node_setting(parameter_name, descriptor, parameter_value))
    settings.sort(key=lambda node_setting: node_setting.setting_name)
    return settings


def _is_ros_infrastructure_parameter(parameter_name):
    """Tell whether ROS 2 itself added the parameter, rather than the node's own code."""
    if parameter_name in ROS_INFRASTRUCTURE_PARAMETER_NAMES:
        return True
    if parameter_name.startswith(ROS_INFRASTRUCTURE_PARAMETER_PREFIXES):
        return True
    if parameter_name.endswith(ROS_INFRASTRUCTURE_PARAMETER_SUFFIXES):
        return True
    # A plugin's name sits between the topic and the setting, never first or last
    inner_name_parts = parameter_name.split('.')[1:-1]
    for name_part in inner_name_parts:
        if name_part in IMAGE_TRANSPORT_PLUGIN_NAMES:
            return True
    return False


def _create_node_setting(parameter_name, descriptor, parameter_value):
    setting_value = convert_parameter_value_to_plain_python(parameter_value)
    node_setting = NodeSetting(
        setting_name=parameter_name,
        setting_value=setting_value,
        type_name=TYPE_NAME_BY_PARAMETER_TYPE.get(parameter_value.type, 'not set'),
        description=descriptor.description,
        additional_constraints=descriptor.additional_constraints,
        is_read_only=descriptor.read_only)
    if descriptor.integer_range:
        integer_range = descriptor.integer_range[0]
        node_setting.minimum_value = integer_range.from_value
        node_setting.maximum_value = integer_range.to_value
        node_setting.step_value = integer_range.step
    elif descriptor.floating_point_range:
        floating_point_range = descriptor.floating_point_range[0]
        node_setting.minimum_value = floating_point_range.from_value
        node_setting.maximum_value = floating_point_range.to_value
        node_setting.step_value = floating_point_range.step
    return node_setting


def wait_for_service_answer(service_future, timeout_s=PARAMETER_SERVICE_TIMEOUT_S):
    """Wait for a node's service answer; the executor thread completes the future."""
    answer_received_event = threading.Event()
    service_future.add_done_callback(lambda done_future: answer_received_event.set())
    if not answer_received_event.wait(timeout=timeout_s):
        service_future.cancel()
        raise HTTPException(status_code=504, detail='The node did not answer in time')
    return service_future.result()
