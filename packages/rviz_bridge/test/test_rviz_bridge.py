# Written by Claude Code
"""Check the pixel-to-table projection against a camera with known geometry."""

import numpy as np

from rviz_bridge.rviz_bridge import pixels_to_table, rotation_matrix

K = np.array([[1000.0, 0.0, 960.0], [0.0, 1000.0, 540.0], [0.0, 0.0, 1.0]])
NO_DISTORTION = np.zeros(5)
# Optical frame 1 m above the table, looking straight down: roll 180 deg, so optical x -> world
# x, optical y -> world -y, optical z (viewing direction) -> world -z
LOOKING_DOWN = rotation_matrix(1.0, 0.0, 0.0, 0.0)
ONE_METRE_UP = np.array([0.0, 0.0, 1.0])


def test_rotation_matrix():
    assert np.allclose(LOOKING_DOWN, np.diag([1.0, -1.0, -1.0]))
    assert np.allclose(rotation_matrix(0.0, 0.0, 0.0, 1.0), np.eye(3))


def test_pixels_land_on_the_table():
    # Principal point -> straight below the camera; fx pixels right -> 1 m in optical x;
    # fy pixels down -> 1 m in optical y, which points to world -y
    pixels = [(960, 540), (1960, 540), (960, 1540)]
    hits = pixels_to_table(pixels, K, NO_DISTORTION, LOOKING_DOWN, ONE_METRE_UP)
    assert np.allclose(hits, [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, -1.0, 0.0]])


def test_rays_away_from_the_table_are_dropped():
    looking_up = np.eye(3)
    assert len(pixels_to_table([(960, 540)], K, NO_DISTORTION, looking_up, ONE_METRE_UP)) == 0
