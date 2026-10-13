# Written by Claude Code
"""
Coordinate conversions of the PAR framework, free of ROS plumbing.

camera pixels --pixels_to_table--> table (metres, z = 0 of world) --table_to_projector-->
projector pixels, and back with projector_to_table. Above the table: a depth image
--depth_to_table--> table frame points --project_to_table--> the table points lit by the same
projector pixels, given the projector's optical centre (found with intersect_rays).
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


def pixel_rays(k, d, width, height, stride=1):
    """
    Return the ray direction (x, y, 1) in the optical frame of every stride-th camera pixel.

    The result has the shape (rows, columns, 3) of image[::stride, ::stride], so it lines up with
    a depth image sampled the same way. Undistorting is slow, so compute it once per camera_info.
    """
    u, v = np.meshgrid(np.arange(0, width, stride), np.arange(0, height, stride))
    pixels = np.column_stack([u.ravel(), v.ravel()]).astype(np.float64).reshape(-1, 1, 2)
    normalized = cv2.undistortPoints(pixels, k, d).reshape(u.shape + (2,))
    return np.concatenate([normalized, np.ones(u.shape + (1,))], axis=2)


def depth_to_table(depth_m, rays, rotation, translation):
    """
    Return the points of a depth image as an Nx3 array in the table frame, in metres.

    depth_m is the depth along the optical axis, sampled like rays (see pixel_rays); rotation and
    translation are the pose of the optical frame in the table frame. Pixels without depth (0 or
    not finite) are dropped.
    """
    valid = np.isfinite(depth_m) & (depth_m > 0)
    points = rays[valid] * depth_m[valid][:, None]
    return points @ rotation.T + translation


def project_to_table(points, center):
    """
    Project Nx3 table-frame points along rays from center onto z = 0 and return them as Nx2.

    With center the projector's optical centre, a point above the table maps to the table point
    lit by the same projector pixel, so table_to_projector then gives that pixel. Points at or
    above the centre's height are lit by no pixel and are dropped. center None projects straight
    down instead, which is only right directly below the projector.
    """
    points = np.asarray(points, np.float64).reshape(-1, 3)
    if center is None:
        return points[:, :2]
    center = np.asarray(center, np.float64)
    points = points[points[:, 2] < center[2]]
    # Along the ray center + s * (point - center), z reaches 0 at s = c_z / (c_z - p_z)
    s = center[2] / (center[2] - points[:, 2])
    return (center + s[:, None] * (points - center))[:, :2]


def intersect_rays(origins, directions):
    """
    Return the point closest to all rays and the RMS distance of the rays from it.

    origins and directions are Nx3, one ray per row; the directions need not be normalised.
    Returns (None, inf) if the rays do not pin down one point, e.g. when they are all parallel.
    """
    origins = np.asarray(origins, np.float64).reshape(-1, 3)
    directions = np.asarray(directions, np.float64).reshape(-1, 3)
    directions = directions / np.linalg.norm(directions, axis=1, keepdims=True)
    # (I - d d^T) removes the part along the ray: what is left is the offset perpendicular to it.
    # The sum of the squared perpendicular offsets is smallest where sum(P) c = sum(P o)
    perpendicular = np.eye(3) - directions[:, :, None] * directions[:, None, :]
    a = perpendicular.sum(axis=0)
    if len(origins) < 2 or np.linalg.matrix_rank(a) < 3:
        return None, np.inf
    point = np.linalg.solve(a, (perpendicular @ origins[:, :, None]).sum(axis=0).ravel())
    offsets = (perpendicular @ (point - origins)[:, :, None])[:, :, 0]
    return point, float(np.sqrt(np.mean(np.sum(offsets ** 2, axis=1))))
