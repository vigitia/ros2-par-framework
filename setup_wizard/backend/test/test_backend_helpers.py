# Written by Claude Code
"""
Plain pytest tests of backend helpers that need no ROS node and no hardware.

Run from a bash with ROS and the workspace sourced (the modules import rclpy and
par_framework_core):
    .venv/bin/python -m pytest setup_wizard/backend/test
"""

from calibration import extrinsics_api
from cameras import cameras_api
from fastapi import HTTPException
from par_framework_core import connected_displays
from profiles import profile_files
import pytest
from rclpy.parameter import Parameter
from shared import node_parameters


@pytest.mark.parametrize('section_name, full_node_name, does_match', [
    ('/cameras/overhead/webcam_node', '/cameras/overhead/webcam_node', True),
    # Parameter files may leave out the leading slash
    ('cameras/overhead/webcam_node', '/cameras/overhead/webcam_node', True),
    ('/cameras/*/webcam_node', '/cameras/overhead/webcam_node', True),
    # * is exactly one name part
    ('/cameras/*/webcam_node', '/cameras/a/b/webcam_node', False),
    ('/**/webcam_node', '/cameras/overhead/webcam_node', True),
    # ** may also stand for no name part
    ('/**/webcam_node', '/webcam_node', True),
    ('/cameras/side/webcam_node', '/cameras/overhead/webcam_node', False),
    # A dot is no wildcard
    ('/cameras/over.ead/webcam_node', '/cameras/overhead/webcam_node', False),
])
def test_does_node_section_match(section_name, full_node_name, does_match):
    assert profile_files._does_node_section_match(section_name, full_node_name) is does_match


@pytest.mark.parametrize('setting_value, parameter_type, expected_value', [
    (True, Parameter.Type.BOOL, True),
    (5, Parameter.Type.INTEGER, 5),
    (5.0, Parameter.Type.INTEGER, 5),
    (5, Parameter.Type.DOUBLE, 5.0),
    (12, Parameter.Type.STRING, '12'),
    ([1, 2.0], Parameter.Type.INTEGER_ARRAY, [1, 2]),
    ([True, False], Parameter.Type.BOOL_ARRAY, [True, False]),
])
def test_convert_setting_value_accepts_fitting_values(setting_value, parameter_type,
                                                      expected_value):
    converted_value = node_parameters.convert_setting_value(setting_value, parameter_type)
    assert converted_value == expected_value
    assert type(converted_value) is type(expected_value)


@pytest.mark.parametrize('setting_value, parameter_type', [
    # Cutting 2.5 to 2 would set another value than asked
    (2.5, Parameter.Type.INTEGER),
    (True, Parameter.Type.INTEGER),
    ('on', Parameter.Type.BOOL),
    ('abc', Parameter.Type.DOUBLE),
    ([True, 1], Parameter.Type.BOOL_ARRAY),
])
def test_convert_setting_value_refuses_unfitting_values(setting_value, parameter_type):
    with pytest.raises(HTTPException) as raised_error:
        node_parameters.convert_setting_value(setting_value, parameter_type)
    assert raised_error.value.status_code == 400


@pytest.mark.parametrize('rotation_quaternion, expected_tilt_deg', [
    # The body frame's x axis pointing straight down: a rotation of 90 deg about y
    ([0.0, 0.7071068, 0.0, 0.7071068], 0.0),
    # Not rotated: x points along the surface
    ([0.0, 0.0, 0.0, 1.0], 90.0),
    # Not normalised: the same direction as the first case
    ([0.0, 2.0, 0.0, 2.0], 0.0),
])
def test_compute_tilt_from_vertical_deg(rotation_quaternion, expected_tilt_deg):
    tilt_deg = extrinsics_api._compute_tilt_from_vertical_deg(rotation_quaternion)
    assert tilt_deg == pytest.approx(expected_tilt_deg, abs=1e-3)


def test_compute_tilt_from_vertical_deg_without_rotation():
    assert extrinsics_api._compute_tilt_from_vertical_deg([0.0, 0.0, 0.0, 0.0]) is None


def test_read_v4l_by_id_serials(tmp_path, monkeypatch):
    v4l_by_id_entry_names = [
        'usb-046d_Logitech_BRIO_ABC123-video-index0',
        'usb-046d_Logitech_BRIO_0042-video-index0',
        # Another stream of the same unit, not its capture device
        'usb-046d_Logitech_BRIO_ABC123-video-index1',
        # Another camera model
        'usb-other_Camera_XYZ-video-index0',
        # A serial that file names do not accept
        'usb-046d_Logitech_BRIO_bad.serial-video-index0',
    ]
    for entry_name in v4l_by_id_entry_names:
        (tmp_path / entry_name).touch()
    monkeypatch.setattr(cameras_api, 'V4L_BY_ID_FOLDER_PATH', str(tmp_path))
    serials = cameras_api._read_v4l_by_id_serials('usb-046d_Logitech_BRIO')
    assert serials == ['0042', 'ABC123']


@pytest.mark.parametrize('parameter_name, is_infrastructure', [
    ('use_sim_time', True),
    ('start_type_description_service', True),
    ('qos_overrides./cameras/overhead/image_raw.publisher.depth', True),
    ('image_raw.enable_pub_plugins', True),
    ('image_raw.compressed.jpeg_quality', True),
    ('exposure_time', False),
    # A plugin's name is never the first or last part of its parameters
    ('compressed', False),
    ('image_raw.compressed', False),
])
def test_is_ros_infrastructure_parameter(parameter_name, is_infrastructure):
    assert node_parameters._is_ros_infrastructure_parameter(
        parameter_name) is is_infrastructure


@pytest.fixture
def drm_connector_folder_path(tmp_path, monkeypatch):
    """Return a fake /sys/class/drm with one HDMI-A-1 and one eDP-1 connector."""
    (tmp_path / 'card1-HDMI-A-1').mkdir()
    (tmp_path / 'card1-eDP-1').mkdir()
    monkeypatch.setattr(connected_displays, 'DRM_CONNECTOR_PATH_PATTERN',
                        str(tmp_path / 'card*-{connector_name}'))
    return tmp_path


def test_find_drm_connector_path_by_kernel_name(drm_connector_folder_path):
    connector_path = connected_displays._find_drm_connector_path('eDP-1')
    assert connector_path == str(drm_connector_folder_path / 'card1-eDP-1')


def test_find_drm_connector_path_by_desktop_hdmi_name(drm_connector_folder_path):
    # X11 and GNOME say HDMI-1 where the kernel says HDMI-A-1
    connector_path = connected_displays._find_drm_connector_path('HDMI-1')
    assert connector_path == str(drm_connector_folder_path / 'card1-HDMI-A-1')


def test_find_drm_connector_path_without_connector(drm_connector_folder_path):
    assert connected_displays._find_drm_connector_path('DP-3') == ''
    assert connected_displays._find_drm_connector_path('') == ''
