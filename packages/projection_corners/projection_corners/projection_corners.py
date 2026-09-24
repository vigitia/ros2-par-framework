# Written by Claude Code
"""Load, save and check the projection corners file, free of ROS plumbing."""

import os

import yaml

# Order around the projected image, as in the file and the message
CORNERS = ('top_left', 'top_right', 'bottom_right', 'bottom_left')

FILE_HEADER = ('# Corners of the projected image in pixels of the raw camera image, written by\n'
               '# projection_corners_node when surface_selector stores a new selection.\n')


def load(path):
    """Return the corners stored at path as a dict, or None if the file does not exist yet."""
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def save(path, corners):
    """Write the corners dict to path."""
    with open(path, 'w') as f:
        f.write(FILE_HEADER)
        yaml.safe_dump(corners, f, sort_keys=False, default_flow_style=None)


def validate(corners):
    """Return why the corners are unusable, or None if they are fine."""
    width, height = corners['image_width'], corners['image_height']
    if width <= 0 or height <= 0:
        return f'image size {width}x{height} is empty'
    points = [corners[name] for name in CORNERS]
    for name, (x, y) in zip(CORNERS, points):
        if not (0 <= x < width and 0 <= y < height):
            return f'{name} ({x}, {y}) lies outside the {width}x{height} image'
    # Shoelace formula: zero area means the corners coincide or lie on one line
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))
    if area == 0:
        return 'the corners enclose no area'
    return None
