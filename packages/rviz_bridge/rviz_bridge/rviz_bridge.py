# Written by Claude Code
"""Project image pixels onto the table plane, free of ROS plumbing."""

import cv2
import numpy as np


def rotation_matrix(x, y, z, w):
    """Return the 3x3 rotation matrix of the unit quaternion (x, y, z, w)."""
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def pixels_to_table(pixels, k, d, rotation, translation):
    """
    Project pixels of the raw camera image onto the plane z = 0 of the table frame.

    k and d are the camera matrix and distortion coefficients, rotation and translation the
    pose of the optical frame in the table frame. Returns the hits as an Nx3 array in metres,
    dropping pixels whose ray misses the table.
    """
    points = np.asarray(pixels, np.float64).reshape(-1, 1, 2)
    # Distortion removed: each pixel becomes the direction (x, y, 1) of its ray in the optical
    # frame
    normalized = cv2.undistortPoints(points, k, d).reshape(-1, 2)
    rays = np.column_stack([normalized, np.ones(len(normalized))]) @ rotation.T
    # Every ray starts at the camera: translation.z + s * ray.z = 0
    with np.errstate(divide='ignore'):
        s = -translation[2] / rays[:, 2]
    hits = translation + s[:, None] * rays
    # s <= 0: the ray points away from the table; not finite: it runs parallel to it
    return hits[np.isfinite(s) & (s > 0)]
