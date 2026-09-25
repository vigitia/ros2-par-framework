# Written by Claude Code
"""Load, save and check the table-to-projector mapping file, free of ROS plumbing."""

import math
import os

import numpy as np
import yaml

FILE_HEADER = ('# Homography from the table plane (x, y in metres) to projector pixels,\n'
               '# written by projection_mapping_node when projection_calibrator stores a new\n'
               '# calibration.\n')
# Below this, the homography cannot be inverted reliably (projector_to_table needs it)
MIN_ABS_DETERMINANT = 1e-12


def load(path):
    """Return the mapping stored at path as a dict, or None if the file does not exist yet."""
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def save(path, mapping):
    """Write the mapping dict to path."""
    with open(path, 'w') as f:
        f.write(FILE_HEADER)
        yaml.safe_dump(mapping, f, sort_keys=False, default_flow_style=None)


def validate(mapping):
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
