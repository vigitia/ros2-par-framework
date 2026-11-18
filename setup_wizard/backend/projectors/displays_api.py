# Written by Claude Code
"""
Displays API of the setup wizard backend: the connected displays, to pick the projector from.

Reads them with par_framework_core.connected_displays, the same code the launch files use to find
a profile's projector, so the wizard and a launch always count displays alike.
"""

from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel
from shared.backend_helpers import read_connected_displays_or_raise

displays_router = APIRouter()


class ConnectedDisplay(BaseModel):
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
    # The display's real mode; SDL's size when it cannot be read
    width_px: int
    height_px: int
    # None when the driver does not report it
    refresh_rate_hz: int | None
    # What apps get for a fullscreen window on it; differs from width_px and height_px when the
    # desktop scales the display
    sdl_width_px: int
    sdl_height_px: int
    # Top left corner on the desktop
    position_x_px: int
    position_y_px: int


class DisplayListResponse(BaseModel):
    displays: list[ConnectedDisplay]


@displays_router.get('/api/displays')
def get_display_list() -> DisplayListResponse:
    """List the connected displays in the framework's display_id order."""
    displays = []
    for connected_display in read_connected_displays_or_raise():
        displays.append(ConnectedDisplay(**asdict(connected_display)))
    return DisplayListResponse(displays=displays)
