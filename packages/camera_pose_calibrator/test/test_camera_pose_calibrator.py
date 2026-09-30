# Written by Claude Code
from camera_pose_calibrator.camera_pose_calibrator import (camera_pose, fit_table_plane,
                                                           matrix_from_quaternion,
                                                           MAX_ABOVE_FRACTION,
                                                           points_from_depth,
                                                           quaternion_from_matrix, sample_grid)
import numpy as np

K = np.array([[900.0, 0.0, 960.0], [0.0, 900.0, 540.0], [0.0, 0.0, 1.0]])
NO_DISTORTION = np.zeros(5)
# Looking straight down: camera x = table x, camera y = table -y, camera z = table -z
STRAIGHT_DOWN = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]])


def tilt(degrees):
    """Rotation about the camera's x axis."""
    a = np.radians(degrees)
    return np.array([[1.0, 0.0, 0.0], [0.0, np.cos(a), -np.sin(a)], [0.0, np.sin(a), np.cos(a)]])


def depth_of_table(camera_to_table, height):
    """Depth image of the plane z = 0 seen from a camera at height with this rotation."""
    u, v = np.meshgrid(np.arange(1920), np.arange(1080))
    rays = np.stack([(u - K[0, 2]) / K[0, 0], (v - K[1, 2]) / K[1, 1], np.ones(u.shape)], -1)
    # Ray s * r in camera coordinates reaches table height 0 where height + s * (R r)_z = 0
    return (-height / (rays @ camera_to_table.T)[..., 2]).astype(np.float32)


def plane(depth):
    u, v = sample_grid(*depth.shape)
    return fit_table_plane(points_from_depth(u, v, depth[v, u], K, NO_DISTORTION))


def measure(depth, x_hint):
    normal, point, fraction, rms, _ = plane(depth)
    translation, quaternion = camera_pose(normal, point, x_hint)
    return translation, matrix_from_quaternion(quaternion), fraction, rms


def test_height_and_tilt_are_measured():
    camera_to_table = STRAIGHT_DOWN @ tilt(2.5)
    translation, rotation, fraction, rms = measure(depth_of_table(camera_to_table, 0.93),
                                                   camera_to_table[0])
    np.testing.assert_allclose(translation, [0.0, 0.0, 0.93], atol=1e-4)
    np.testing.assert_allclose(rotation, camera_to_table, atol=1e-4)
    assert fraction > 0.99 and rms < 1e-4


def test_clutter_on_the_table_is_ignored():
    camera_to_table = STRAIGHT_DOWN @ tilt(2.5)
    depth = depth_of_table(camera_to_table, 0.93)
    depth[400:560, 800:960] -= 0.076    # a cube
    depth[700:900, 1200:1400] -= 0.25   # a hand above the table
    translation, rotation, fraction, _ = measure(depth, camera_to_table[0])
    np.testing.assert_allclose(translation, [0.0, 0.0, 0.93], atol=1e-3)
    np.testing.assert_allclose(rotation, camera_to_table, atol=1e-3)
    assert 0.9 < fraction < 0.99


def test_floor_beside_the_table_is_ignored():
    # A wide depth camera also sees the floor beyond the table edge: a plane through all points
    # is tilted so far that it matches neither
    camera_to_table = STRAIGHT_DOWN @ tilt(8.0)
    depth = depth_of_table(camera_to_table, 0.93)
    depth[650:] = depth_of_table(camera_to_table, 0.93 + 0.75)[650:]
    translation, rotation, fraction, rms = measure(depth, camera_to_table[0])
    np.testing.assert_allclose(translation, [0.0, 0.0, 0.93], atol=1e-3)
    np.testing.assert_allclose(rotation, camera_to_table, atol=1e-3)
    assert 0.55 < fraction < 0.65 and rms < 1e-3


def test_only_what_is_above_the_table_counts_against_it():
    camera_to_table = STRAIGHT_DOWN @ tilt(8.0)
    table = depth_of_table(camera_to_table, 0.93)
    floor = depth_of_table(camera_to_table, 0.93 + 0.75)
    # Floor beside the table is below it: the table is clear
    depth = table.copy()
    depth[650:] = floor[650:]
    assert plane(depth)[4] < 0.01
    # A cube and a hand, 3 % of the image: still clear enough
    depth[400:560, 800:960] -= 0.076
    depth[100:300, 1200:1400] -= 0.25
    assert 0.02 < plane(depth)[4] < MAX_ABOVE_FRACTION
    # More floor than table: the plane found is the floor, and the table is above it
    depth = table.copy()
    depth[400:] = floor[400:]
    assert plane(depth)[4] > MAX_ABOVE_FRACTION


def test_rotation_about_the_vertical_follows_the_hint():
    # The table plane cannot tell where world x points: that direction comes from the hint
    camera_to_table = STRAIGHT_DOWN @ tilt(2.5)
    depth = depth_of_table(camera_to_table, 0.93)
    for hint in (camera_to_table[0], camera_to_table[1]):
        _, rotation, _, _ = measure(depth, hint)
        np.testing.assert_allclose(rotation[0], hint, atol=1e-3)


def test_quaternion_round_trip():
    camera_to_table = STRAIGHT_DOWN @ tilt(2.5)
    np.testing.assert_allclose(matrix_from_quaternion(quaternion_from_matrix(camera_to_table)),
                               camera_to_table, atol=1e-9)
    # The placeholder in par_setup.yaml, straight down around camera_base's y axis
    placeholder = matrix_from_quaternion((0.0, 0.7071068, 0.0, 0.7071068))
    np.testing.assert_allclose(placeholder @ [1.0, 0.0, 0.0], [0.0, 0.0, -1.0], atol=1e-6)
