# Written by Claude Code
"""
The connected displays and how a profile recognises its projector among them.

The framework's display_id is SDL's display index: surface_selector lists displays through pygame
(SDL), and the rendering manager counts its --display-id the same way. So this module asks SDL
too, through ctypes on the system's SDL 2 library (the one pygame uses), for each display's name,
resolution, refresh rate and position on the desktop. SDL names only the connector (e.g. "DP-1"),
so the projector's make, model and serial come from its EDID, which Linux exposes under
/sys/class/drm/<card>-<connector>/edid.

The index changes when displays are plugged in or out, so a profile also stores the projector's
identity (EDID make, model and serial, and the connector) in par_launch, and the launch files look
the projector up by it (launch_helpers.get_projector_display_id).
Not ROS: displays have no ROS interface, so this part is specific to Linux and SDL. Imports
nothing from launch or rclpy, so the setup wizard's backend uses it too.
"""

import ctypes
import ctypes.util
from dataclasses import dataclass
import glob
import threading

SDL_INIT_VIDEO_FLAG = 0x00000020
SDL_LIBRARY_NAME = 'SDL2'
# Where Linux exposes each connector's EDID, e.g. /sys/class/drm/card1-HDMI-A-1/edid
EDID_PATH_PATTERN = '/sys/class/drm/card*-{connector_name}/edid'
# EDID layout (VESA E-EDID 1.4): manufacturer id at bytes 8-9, then four 18-byte descriptors
EDID_MINIMUM_LENGTH_BYTES = 128
EDID_MANUFACTURER_ID_OFFSET = 8
EDID_DESCRIPTOR_OFFSETS = (54, 72, 90, 108)
EDID_DESCRIPTOR_LENGTH_BYTES = 18
EDID_DESCRIPTOR_TEXT_OFFSET = 5
EDID_DESCRIPTOR_TAG_MODEL_NAME = 0xFC
EDID_DESCRIPTOR_TAG_SERIAL_TEXT = 0xFF

# The projector's identity in par_launch, by the ConnectedDisplay attribute it comes from. The
# EDID values name the device; the connector only tells two identical devices apart.
PROJECTOR_EDID_PARAMETER_NAME_BY_ATTRIBUTE = {
    'manufacturer_id': 'projector_manufacturer_id',
    'model_name': 'projector_model_name',
    'serial_text': 'projector_serial_text',
}
PROJECTOR_CONNECTOR_PARAMETER_NAME = 'projector_connector_name'
PROJECTOR_IDENTITY_PARAMETER_NAMES = (*PROJECTOR_EDID_PARAMETER_NAME_BY_ATTRIBUTE.values(),
                                      PROJECTOR_CONNECTOR_PARAMETER_NAME)
# The display mode the projector was chosen with, in par_launch, by the ConnectedDisplay attribute
# it comes from. A changed mode (e.g. after the desktop's display settings were changed) means the
# projector calibration, measured in projector pixels, may no longer fit.
PROJECTOR_DISPLAY_MODE_PARAMETER_NAME_BY_ATTRIBUTE = {
    'width_px': 'projector_width_px',
    'height_px': 'projector_height_px',
    'refresh_rate_hz': 'projector_refresh_rate_hz',
}

# SDL keeps global state; one caller at a time initialises and quits its video part.
_sdl_lock = threading.Lock()


@dataclass
class ConnectedDisplay:
    # The framework's display_id (par_launch.projector_display_id, --display-id of the rendering
    # manager)
    display_id: int
    # SDL's name, usually the connector plus the size, e.g. 'eDP-1 15"'
    sdl_display_name: str
    # e.g. 'HDMI-A-1'; empty when SDL's name does not start with one
    connector_name: str
    # From the EDID; empty when the display reports none or it cannot be read
    manufacturer_id: str
    model_name: str
    serial_text: str
    width_px: int
    height_px: int
    # None when the driver does not report it
    refresh_rate_hz: int | None
    # Top left corner on the desktop
    position_x_px: int
    position_y_px: int


class _SdlDisplayMode(ctypes.Structure):
    _fields_ = [('pixel_format', ctypes.c_uint32), ('width_px', ctypes.c_int),
                ('height_px', ctypes.c_int), ('refresh_rate_hz', ctypes.c_int),
                ('driver_data', ctypes.c_void_p)]


class _SdlRect(ctypes.Structure):
    _fields_ = [('x_px', ctypes.c_int), ('y_px', ctypes.c_int), ('width_px', ctypes.c_int),
                ('height_px', ctypes.c_int)]


def read_connected_displays():
    """
    Return the connected displays in the framework's display_id order.

    Raises RuntimeError naming the cause when SDL is missing or cannot open the displays.
    """
    sdl_library = _load_sdl_library()
    with _sdl_lock:
        # Initialised per call, so displays plugged in since the last call show up
        if sdl_library.SDL_InitSubSystem(SDL_INIT_VIDEO_FLAG) != 0:
            sdl_error_text = sdl_library.SDL_GetError().decode(errors='replace')
            raise RuntimeError(f'[connected_displays]: SDL could not open the displays: '
                               f'{sdl_error_text}. Is this started inside the desktop session?')
        try:
            return _read_displays(sdl_library)
        finally:
            sdl_library.SDL_QuitSubSystem(SDL_INIT_VIDEO_FLAG)


def get_display_title_text(connected_display):
    """Return the model when the display reports one, e.g. 'EPS EB-680', otherwise SDL's name."""
    if connected_display.model_name:
        return f'{connected_display.manufacturer_id} {connected_display.model_name}'.strip()
    return connected_display.sdl_display_name


def get_projector_identity(connected_display):
    """Return the par_launch values that recognise this display: {parameter name: text}."""
    projector_identity = {}
    for attribute_name, parameter_name in PROJECTOR_EDID_PARAMETER_NAME_BY_ATTRIBUTE.items():
        projector_identity[parameter_name] = getattr(connected_display, attribute_name)
    projector_identity[PROJECTOR_CONNECTOR_PARAMETER_NAME] = connected_display.connector_name
    return projector_identity


def get_projector_display_mode(connected_display):
    """Return the display's mode as par_launch stores it: {parameter name: number or None}."""
    projector_display_mode = {}
    for attribute_name, parameter_name in (
            PROJECTOR_DISPLAY_MODE_PARAMETER_NAME_BY_ATTRIBUTE.items()):
        projector_display_mode[parameter_name] = getattr(connected_display, attribute_name)
    return projector_display_mode


def get_display_mode_text(width_px, height_px, refresh_rate_hz):
    """Return a mode as people write it, e.g. '1920 × 1080 at 60 Hz'."""
    display_mode_text = f'{width_px} × {height_px}'
    if refresh_rate_hz:
        display_mode_text = f'{display_mode_text} at {refresh_rate_hz} Hz'
    return display_mode_text


def get_projector_identity_title_text(projector_identity):
    """Return a short name for a stored identity, e.g. 'EPS EB-680', or its connector."""
    manufacturer_id = projector_identity.get('projector_manufacturer_id', '')
    model_name = projector_identity.get('projector_model_name', '')
    title_text = f'{manufacturer_id} {model_name}'.strip()
    if title_text:
        return title_text
    return projector_identity.get(PROJECTOR_CONNECTOR_PARAMETER_NAME, '')


def find_projector_display_ids(connected_displays, projector_identity):
    """
    Return the display_ids of the displays that match a stored projector identity.

    A display matches when its EDID make, model and serial equal the stored ones. When that
    leaves several (identical projectors without a serial), the stored connector decides. Without
    stored EDID values, the connector alone identifies the projector. One id = found, none = not
    connected, several = ambiguous.
    """
    stored_edid_values = []
    for parameter_name in PROJECTOR_EDID_PARAMETER_NAME_BY_ATTRIBUTE.values():
        stored_edid_values.append(projector_identity.get(parameter_name, ''))
    stored_connector_name = projector_identity.get(PROJECTOR_CONNECTOR_PARAMETER_NAME, '')
    has_stored_edid_values = any(stored_edid_values)

    matching_displays = []
    for connected_display in connected_displays:
        if has_stored_edid_values:
            display_edid_values = []
            for attribute_name in PROJECTOR_EDID_PARAMETER_NAME_BY_ATTRIBUTE:
                display_edid_values.append(getattr(connected_display, attribute_name))
            is_matching = display_edid_values == stored_edid_values
        else:
            is_matching = connected_display.connector_name == stored_connector_name
        if is_matching:
            matching_displays.append(connected_display)

    if len(matching_displays) > 1 and stored_connector_name:
        displays_on_stored_connector = []
        for matching_display in matching_displays:
            if matching_display.connector_name == stored_connector_name:
                displays_on_stored_connector.append(matching_display)
        if displays_on_stored_connector:
            matching_displays = displays_on_stored_connector

    matching_display_ids = []
    for matching_display in matching_displays:
        matching_display_ids.append(matching_display.display_id)
    return matching_display_ids


def _load_sdl_library():
    sdl_library_path = ctypes.util.find_library(SDL_LIBRARY_NAME)
    if sdl_library_path is None:
        raise RuntimeError('[connected_displays]: the SDL 2 library is missing: '
                           'sudo apt install libsdl2-2.0-0')
    sdl_library = ctypes.CDLL(sdl_library_path)
    sdl_library.SDL_GetDisplayName.restype = ctypes.c_char_p
    sdl_library.SDL_GetError.restype = ctypes.c_char_p
    return sdl_library


def _read_displays(sdl_library):
    displays = []
    display_count = sdl_library.SDL_GetNumVideoDisplays()
    for display_id in range(display_count):
        display_mode = _SdlDisplayMode()
        display_bounds = _SdlRect()
        sdl_library.SDL_GetCurrentDisplayMode(display_id, ctypes.byref(display_mode))
        sdl_library.SDL_GetDisplayBounds(display_id, ctypes.byref(display_bounds))
        sdl_display_name_bytes = sdl_library.SDL_GetDisplayName(display_id) or b''
        sdl_display_name = sdl_display_name_bytes.decode(errors='replace')
        connector_name = _get_connector_name(sdl_display_name)
        manufacturer_id, model_name, serial_text = _read_edid_identity(connector_name)
        refresh_rate_hz = display_mode.refresh_rate_hz
        if refresh_rate_hz <= 0:
            refresh_rate_hz = None
        displays.append(ConnectedDisplay(
            display_id=display_id, sdl_display_name=sdl_display_name,
            connector_name=connector_name, manufacturer_id=manufacturer_id,
            model_name=model_name, serial_text=serial_text,
            width_px=display_mode.width_px, height_px=display_mode.height_px,
            refresh_rate_hz=refresh_rate_hz,
            position_x_px=display_bounds.x_px, position_y_px=display_bounds.y_px))
    return displays


def _get_connector_name(sdl_display_name):
    """Return the connector at the start of SDL's name ('DP-1 27"' -> 'DP-1'), or ''."""
    name_parts = sdl_display_name.split()
    if not name_parts:
        return ''
    first_name_part = name_parts[0]
    # Connector names look like 'eDP-1' or 'HDMI-A-1': letters, a dash, a number at the end
    if '-' not in first_name_part or not first_name_part[-1].isdigit():
        return ''
    return first_name_part


def _read_edid_identity(connector_name):
    """Return (manufacturer id, model name, serial text) from the connector's EDID, or ''."""
    if not connector_name:
        return '', '', ''
    edid_paths = glob.glob(EDID_PATH_PATTERN.format(connector_name=connector_name))
    if not edid_paths:
        return '', '', ''
    try:
        with open(edid_paths[0], 'rb') as edid_file:
            edid_bytes = edid_file.read()
    except OSError:
        return '', '', ''
    # Empty while nothing is plugged in; also guards against a truncated file
    if len(edid_bytes) < EDID_MINIMUM_LENGTH_BYTES:
        return '', '', ''
    manufacturer_id = _decode_edid_manufacturer_id(edid_bytes)
    model_name = _read_edid_descriptor_text(edid_bytes, EDID_DESCRIPTOR_TAG_MODEL_NAME)
    serial_text = _read_edid_descriptor_text(edid_bytes, EDID_DESCRIPTOR_TAG_SERIAL_TEXT)
    return manufacturer_id, model_name, serial_text


def _decode_edid_manufacturer_id(edid_bytes):
    """Return the three-letter manufacturer id (e.g. 'EPS'), five bits per letter, 1 = 'A'."""
    high_byte = edid_bytes[EDID_MANUFACTURER_ID_OFFSET]
    low_byte = edid_bytes[EDID_MANUFACTURER_ID_OFFSET + 1]
    manufacturer_bits = (high_byte << 8) | low_byte
    letters = []
    for letter_shift in (10, 5, 0):
        letter_number = (manufacturer_bits >> letter_shift) & 0x1F
        if not 1 <= letter_number <= 26:
            return ''
        letters.append(chr(ord('A') + letter_number - 1))
    return ''.join(letters)


def _read_edid_descriptor_text(edid_bytes, descriptor_tag):
    """Return the text of the first display descriptor with descriptor_tag, '' without one."""
    for descriptor_offset in EDID_DESCRIPTOR_OFFSETS:
        descriptor_end_offset = descriptor_offset + EDID_DESCRIPTOR_LENGTH_BYTES
        descriptor_bytes = edid_bytes[descriptor_offset:descriptor_end_offset]
        # A display descriptor starts with three zero bytes, then its tag
        if descriptor_bytes[0:3] != b'\x00\x00\x00' or descriptor_bytes[3] != descriptor_tag:
            continue
        text_bytes = descriptor_bytes[EDID_DESCRIPTOR_TEXT_OFFSET:]
        # The text ends at a line feed, padded with spaces
        text = text_bytes.split(b'\n')[0].decode('ascii', errors='replace')
        return text.strip()
    return ''
