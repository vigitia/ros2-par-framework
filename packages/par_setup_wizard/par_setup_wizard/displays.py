# Written by Claude Code
"""
The displays as pygame/SDL counts them, which is what display_id means, run as a subprocess.

    python3 -m par_setup_wizard.displays list            # JSON: name, position, size by index
    python3 -m par_setup_wizard.displays number <index>  # the index, big, on that display
    python3 -m par_setup_wizard.displays grid <index>    # a test grid, fullscreen on that display

number and grid run until the process is ended. A process of their own keeps pygame's display
out of the wizard, where it would compete with Qt for the window system.
"""

import ctypes
import json
import sys

import cv2
import numpy as np
import pygame
from surface_selector.display_info import get_connected_monitors, get_resolution_of_monitor_by_id
from surface_selector.show_white_fullscreen import display_image

GRID_STEP_PX = 100


class _Rect(ctypes.Structure):
    _fields_ = [('x', ctypes.c_int), ('y', ctypes.c_int), ('w', ctypes.c_int), ('h', ctypes.c_int)]


def list_displays():
    """Return [{name, x, y, width, height}] by SDL index, the index display_id means."""
    pygame.display.init()
    # pygame has no display names or positions, the SDL it loaded has: found in this process's
    # memory map, so it is the very library (and display order) pygame uses
    with open('/proc/self/maps') as maps:
        library = next((line.split()[-1] for line in maps if 'libSDL2' in line), None)
    if library is None:
        # Sizes only, as pygame reports them
        return [{'name': '', 'x': None, 'y': None, 'width': w, 'height': h}
                for w, h in (monitor.resolution for monitor in get_connected_monitors())]
    sdl = ctypes.CDLL(library)
    sdl.SDL_GetDisplayName.restype = ctypes.c_char_p
    displays = []
    for index in range(sdl.SDL_GetNumVideoDisplays()):
        bounds = _Rect()
        sdl.SDL_GetDisplayBounds(index, ctypes.byref(bounds))
        name = (sdl.SDL_GetDisplayName(index) or b'').decode(errors='replace')
        displays.append({'name': name, 'x': bounds.x, 'y': bounds.y,
                         'width': bounds.w, 'height': bounds.h})
    return displays


def number_image(width, height, index):
    """Return a black image with index in white, as large as it fits."""
    image = np.zeros((height, width), np.uint8)
    text = str(index)
    scale = height / 40
    thickness = max(1, int(scale * 2))
    (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale,
                                                   thickness)
    origin = ((width - text_width) // 2, (height + text_height) // 2)
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, 255, thickness)
    return image


def grid_image(width, height):
    """Return a white grid on black: lines every GRID_STEP_PX, the border, and the centre cross."""
    image = np.zeros((height, width), np.uint8)
    image[::GRID_STEP_PX, :] = 255
    image[:, ::GRID_STEP_PX] = 255
    cv2.rectangle(image, (0, 0), (width - 1, height - 1), 255, 3)
    cv2.line(image, (width // 2, 0), (width // 2, height - 1), 255, 5)
    cv2.line(image, (0, height // 2), (width - 1, height // 2), 255, 5)
    return image


def main():
    mode = sys.argv[1]
    if mode == 'list':
        print(json.dumps(list_displays()))
        return
    index = int(sys.argv[2])
    width, height = get_resolution_of_monitor_by_id(index)
    image = number_image(width, height, index) if mode == 'number' else grid_image(width, height)
    try:
        display_image(index, image)
    except KeyboardInterrupt:
        # The wizard ends this process with SIGINT: the normal end, no traceback
        pass


if __name__ == '__main__':
    main()
