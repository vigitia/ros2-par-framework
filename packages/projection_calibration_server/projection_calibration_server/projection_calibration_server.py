# Written by Claude Code
"""Load, save and check the projection calibration files, free of ROS plumbing."""

from datetime import datetime
import math
import os

import numpy as np
import yaml

# Order around the projected image, as in the file and the message
CORNERS = ('top_left', 'top_right', 'bottom_right', 'bottom_left')

CORNERS_HEADER = ('# Corners of the projected image in pixels of the raw camera image,\n'
                  '# written by projection_calibration_server_node when surface_selector\n'
                  '# stores a new selection.\n')
MAPPING_HEADER = ('# Homography from the table plane (x, y in metres) to projector pixels,\n'
                  '# written by projection_calibration_server_node when projection_calibrator\n'
                  '# stores a new calibration.\n')
# Below this, the homography cannot be inverted reliably (projector_to_table needs it)
MIN_ABS_DETERMINANT = 1e-12


def load(path):
    """
    Return the calibration stored at path as a dict, or None if the file does not exist yet.

    Raises ValueError if the file holds no key-value pairs, e.g. when it is empty or not YAML.
    """
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f'not valid YAML: {e}') from e
    if not isinstance(data, dict):
        raise ValueError('the file is empty or holds no key-value pairs')
    return data


def save(path, header, data):
    """Write the calibration dict to path, below the header comment."""
    with open(path, 'w') as f:
        f.write(header)
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=None)


def save_corners(path, corners):
    """Write the corners dict to path."""
    save(path, CORNERS_HEADER, corners)


def save_mapping(path, mapping):
    """Write the mapping dict to path, with the time it was stored as 'measured'."""
    # Same key and format as camera_pose_calibrator's pose file
    save(path, MAPPING_HEADER,
         {**mapping, 'measured': datetime.now().isoformat(timespec='seconds')})


def validate_corners(corners):
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


def validate_mapping(mapping):
    """Return why the mapping is unusable, or None if it is fine."""
    if not mapping['frame_id']:
        return 'frame_id is empty'
    width, height = mapping['projector_width'], mapping['projector_height']
    if width <= 0 or height <= 0:
        return f'projector size {width}x{height} is empty'
    values = [value for row in mapping['homography'] for value in row]
    if len(values) != 9 or not all(math.isfinite(value) for value in values):
        return 'the homography needs 9 finite values'
    if abs(np.linalg.det(np.reshape(values, (3, 3)))) < MIN_ABS_DETERMINANT:
        return 'the homography is singular'
    return None
