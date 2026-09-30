# Written by Claude Code
"""Measure a camera's pose from the table plane in a depth image, free of ROS plumbing."""

from datetime import datetime

import cv2
import numpy as np
import yaml

FILE_HEADER = ('# Pose of the camera body frame in world (the table plane is z = 0), measured by\n'
               '# camera_pose_calibrator from the clear table in a depth image. As\n'
               '# camera_pose_<camera>.yaml next to par_setup.yaml, the launch files use it\n'
               '# instead of the placeholder there; delete it to go back.\n')
# Every SAMPLE_STEP_PX-th pixel in both directions: about 32 000 points in a 1080p image, plenty
# for a plane and cheap to keep for many frames
SAMPLE_STEP_PX = 8
# Trimmed fit: after each fit, only points this close to the plane are kept for the next one. The
# table is by far the largest surface, so a cube, a hand or the floor beyond the table edge drop
# out step by step.
TABLE_BANDS_M = (0.05, 0.02, 0.01)
# The trimmed fit starts from the plane through 3 random points that the most points lie on
# (RANSAC), not from a plane through all points: a wide depth camera also sees the floor around the
# table, which tilts a plane through everything so far that it matches neither. 200 tries miss a
# table covering half the image with a chance of 1e-11.
RANSAC_ITERATIONS = 200
RANSAC_BAND_M = 0.02
# A measurement is refused when more of the image than this is above the table (nearer to the
# camera): the table is not clear, or the plane found is the floor with the table above it. What is
# below the table, the floor around it, does not count: a wide depth camera sees a lot of it.
MAX_ABOVE_FRACTION = 0.1
# Also refused when less of the image than this is table, too little to measure the tilt from, or
# the table is not flat within this RMS: the depth is unusable
MIN_TABLE_FRACTION = 0.25
MAX_TABLE_RMS_M = 0.01


def sample_grid(height, width):
    """Return the pixel columns and rows (u, v) that are sampled, as flat arrays."""
    v, u = np.mgrid[0:height:SAMPLE_STEP_PX, 0:width:SAMPLE_STEP_PX]
    return u.ravel(), v.ravel()


def points_from_depth(u, v, z, k, d):
    """Return the Nx3 points of pixels (u, v) with depth z > 0, in the optical frame, in metres."""
    valid = z > 0
    pixels = np.column_stack([u[valid], v[valid]]).astype(np.float64).reshape(-1, 1, 2)
    # Distortion removed: each pixel becomes the direction (x, y, 1) of its ray. The depth is the
    # distance along the optical axis (z), as the Azure Kinect measures it.
    normalized = cv2.undistortPoints(pixels, k, d).reshape(-1, 2)
    return np.column_stack([normalized * z[valid, None], z[valid]])


def fit_table_plane(points):
    """
    Return (normal, centroid, table fraction, RMS in metres, fraction above) of the dominant plane.

    The normal points towards the camera (the origin), so the table is below the camera along it.
    The fractions are shares of the points: those on the plane, and those above it.
    """
    table = np.ones(len(points), bool)
    most = 0
    # Seeded: the same depth image gives the same pose
    for a, b, c in points[np.random.default_rng(0).choice(len(points), (RANSAC_ITERATIONS, 3))]:
        normal = np.cross(b - a, c - a)
        length = np.linalg.norm(normal)
        if length < 1e-12:
            continue
        on_plane = np.abs((points - a) @ (normal / length)) <= RANSAC_BAND_M
        if on_plane.sum() > most:
            table, most = on_plane, on_plane.sum()
    for band in TABLE_BANDS_M:
        centroid = points[table].mean(axis=0)
        # The direction of least spread is the normal. full_matrices=False: the default also
        # computes an N x N matrix, 8 GB for the 32 000 points of a full depth image.
        normal = np.linalg.svd(points[table] - centroid, full_matrices=False)[2][2]
        table = np.abs((points - centroid) @ normal) <= band
    centroid = points[table].mean(axis=0)
    normal = np.linalg.svd(points[table] - centroid, full_matrices=False)[2][2]
    if normal @ -centroid < 0:
        normal = -normal
    rms = np.sqrt(np.mean(((points[table] - centroid) @ normal) ** 2))
    above = np.mean((points - centroid) @ normal > TABLE_BANDS_M[-1])
    return normal, centroid, table.mean(), rms, above


def matrix_from_quaternion(q):
    """Return the rotation matrix of the quaternion (x, y, z, w)."""
    x, y, z, w = np.asarray(q, np.float64) / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def quaternion_from_matrix(rotation):
    """Return the quaternion (x, y, z, w) of a rotation matrix."""
    rvec = cv2.Rodrigues(np.asarray(rotation, np.float64))[0].ravel()
    angle = np.linalg.norm(rvec)
    if angle < 1e-12:
        return np.array([0.0, 0.0, 0.0, 1.0])
    return np.concatenate([rvec / angle * np.sin(angle / 2), [np.cos(angle / 2)]])


def camera_pose(normal, point, x_hint):
    """
    Return (translation, quaternion x y z w) of the camera frame in the table frame.

    normal, point: the table plane in the camera frame, normal towards the camera. x_hint: the
    direction in the camera frame that the table frame's x axis follows, projected into the plane.
    The rotation about the vertical is not measurable from a plane, so it is kept from there.
    The camera ends up straight above the table frame's origin.
    """
    x = x_hint - (x_hint @ normal) * normal
    if np.linalg.norm(x) < 1e-6:
        raise ValueError('x_hint is perpendicular to the table, it gives no direction in it')
    x /= np.linalg.norm(x)
    # Rows: the table frame's axes in camera coordinates, so it maps camera to table coordinates
    rotation = np.array([x, np.cross(normal, x), normal])
    return np.array([0.0, 0.0, -normal @ point]), quaternion_from_matrix(rotation)


def save(path, translation, quaternion, table_fraction, table_rms_m):
    """Write the pose to path, with the keys of par_setup.yaml's camera poses."""
    pose = {f'translation.{axis}': float(value) for axis, value in zip('xyz', translation)}
    pose.update({f'rotation.{axis}': float(value) for axis, value in zip('xyzw', quaternion)})
    pose.update({'measured': datetime.now().isoformat(timespec='seconds'),
                 'table_fraction': round(float(table_fraction), 3),
                 'table_rms_mm': round(1000 * float(table_rms_m), 2)})
    with open(path, 'w') as f:
        f.write(FILE_HEADER)
        yaml.safe_dump(pose, f, sort_keys=False)
