# Written by Claude Code
"""
Coordinate conversions of the PAR framework, free of ROS plumbing.

camera pixels --pixels_to_table--> table (metres, z = 0 of world) --table_to_projector-->
projector pixels, and back with projector_to_table.
"""

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


def apply_homography(h, points):
    """Map Nx2 points through the 3x3 homography h and return them as an Nx2 array."""
    points = np.asarray(points, np.float64).reshape(-1, 1, 2)
    if len(points) == 0:
        return np.empty((0, 2))
    return cv2.perspectiveTransform(points, np.asarray(h, np.float64)).reshape(-1, 2)


def homography_from_msg(msg):
    """Return the table-to-projector homography of a ProjectionMapping message as 3x3 array."""
    return np.reshape(msg.homography, (3, 3))


def table_to_projector(h, points):
    """Map Nx2 table points (x, y in metres) to projector pixels with the homography h."""
    return apply_homography(h, points)


def projector_to_table(h, points):
    """Map Nx2 projector pixels to table points (x, y in metres), the inverse of h."""
    return apply_homography(np.linalg.inv(h), points)
