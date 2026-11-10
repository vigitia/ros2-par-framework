# Written by Claude Code
"""
Show a black fullscreen window on one display until the process is ended.

Started by projector_blackout_api, so the projector's light does not disturb camera images while
calibration steps run that do not need the projector (e.g. capturing a checkerboard). Uses
pygame's fullscreen on an SDL display index, the framework's display_id, as surface_selector's
calibration windows do.

    python projector_blackout_window.py <display_id>
"""

import os
import sys

import pygame

COLOR_BLACK = (0, 0, 0)
# The image never changes; redrawing now and then is enough for a compositor that asks for it
REDRAW_INTERVAL_MS = 100


def main():
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print('[projector_blackout_window]: usage: projector_blackout_window.py <display_id>',
              file=sys.stderr)
        sys.exit(2)
    display_id = int(sys.argv[1])
    # Without it, SDL minimizes a fullscreen window as soon as another window gets the focus,
    # e.g. when the user clicks back into the setup wizard
    os.environ.setdefault('SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS', '0')
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN, display=display_id)
    pygame.display.set_caption('PAR setup wizard: projector black')
    pygame.mouse.set_visible(False)
    # Runs until projector_blackout_api ends the process (SIGTERM, SIGKILL)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
        screen.fill(COLOR_BLACK)
        pygame.display.flip()
        pygame.time.wait(REDRAW_INTERVAL_MS)


if __name__ == '__main__':
    main()
