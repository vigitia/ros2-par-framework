# Written by Claude Code
"""Check saving, loading and validating the projection corners file."""

from projection_corners.projection_corners import load, save, validate

CORNERS = {
    'frame_id': 'brio_optical_frame',
    'image_width': 1920,
    'image_height': 1080,
    'top_left': [412.0, 233.0],
    'top_right': [1530.0, 241.0],
    'bottom_right': [1544.0, 872.0],
    'bottom_left': [398.0, 860.0],
}


def test_missing_file_means_no_corners(tmp_path):
    assert load(str(tmp_path / 'projection_corners.yaml')) is None


def test_save_and_load_round_trip(tmp_path):
    path = str(tmp_path / 'projection_corners.yaml')
    save(path, CORNERS)
    assert load(path) == CORNERS


def test_validate():
    assert validate(CORNERS) is None
    assert 'outside' in validate({**CORNERS, 'top_right': [1920.0, 241.0]})
    assert 'no area' in validate({**CORNERS, **{name: [5.0, 5.0] for name in
                                                ('top_left', 'top_right', 'bottom_right',
                                                 'bottom_left')}})
    assert 'empty' in validate({**CORNERS, 'image_width': 0})
