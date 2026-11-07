# Written by Claude Code
"""
Displays API of the setup wizard backend: the connected displays, to pick the projector from.

The framework's display_id is SDL's display index: surface_selector lists displays through pygame
(SDL), and the rendering manager counts its --display-id the same way. So this module asks SDL
too, through ctypes on the system's SDL 2 library (the one pygame uses), for each display's name,
resolution, refresh rate and position on the desktop. SDL names only the connector (e.g. "DP-1"),
so the projector's make, model and serial come from its EDID, which Linux exposes under
/sys/class/drm/<card>-<connector>/edid.
Not ROS: displays have no ROS interface, so this part is specific to Linux and SDL.
"""

import ctypes
import ctypes.util
import glob
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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

# SDL keeps global state; one request at a time initialises and quits its video part.
_sdl_lock = threading.Lock()

displays_router = APIRouter()


class _SdlDisplayMode(ctypes.Structure):
    _fields_ = [('pixel_format', ctypes.c_uint32), ('width_px', ctypes.c_int),
                ('height_px', ctypes.c_int), ('refresh_rate_hz', ctypes.c_int),
                ('driver_data', ctypes.c_void_p)]


class _SdlRect(ctypes.Structure):
    _fields_ = [('x_px', ctypes.c_int), ('y_px', ctypes.c_int), ('width_px', ctypes.c_int),
                ('height_px', ctypes.c_int)]


class ConnectedDisplay(BaseModel):
    # The framework's display_id (par_setup.yaml, --display-id of the rendering manager)
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


class DisplayListResponse(BaseModel):
    displays: list[ConnectedDisplay]


@displays_router.get('/api/displays')
def get_display_list() -> DisplayListResponse:
    """List the connected displays in the framework's display_id order."""
    sdl_library = _load_sdl_library()
    with _sdl_lock:
        # Initialised per request, so displays plugged in since the last request show up
        if sdl_library.SDL_InitSubSystem(SDL_INIT_VIDEO_FLAG) != 0:
            raise HTTPException(status_code=500,
                                detail=f'SDL could not open the displays: '
                                       f'{sdl_library.SDL_GetError().decode(errors="replace")}. '
                                       f'Is the backend started inside the desktop session?')
        try:
            displays = _read_displays(sdl_library)
        finally:
            sdl_library.SDL_QuitSubSystem(SDL_INIT_VIDEO_FLAG)
    return DisplayListResponse(displays=displays)


def _load_sdl_library():
    sdl_library_path = ctypes.util.find_library(SDL_LIBRARY_NAME)
    if sdl_library_path is None:
        raise HTTPException(status_code=500,
                            detail='The SDL 2 library is missing: sudo apt install libsdl2-2.0-0')
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
    manufacturer_bits = (edid_bytes[EDID_MANUFACTURER_ID_OFFSET] << 8) | edid_bytes[
        EDID_MANUFACTURER_ID_OFFSET + 1]
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
        descriptor_bytes = edid_bytes[descriptor_offset:
                                      descriptor_offset + EDID_DESCRIPTOR_LENGTH_BYTES]
        # A display descriptor starts with three zero bytes, then its tag
        if descriptor_bytes[0:3] != b'\x00\x00\x00' or descriptor_bytes[3] != descriptor_tag:
            continue
        text_bytes = descriptor_bytes[EDID_DESCRIPTOR_TEXT_OFFSET:]
        # The text ends at a line feed, padded with spaces
        text = text_bytes.split(b'\n')[0].decode('ascii', errors='replace')
        return text.strip()
    return ''
