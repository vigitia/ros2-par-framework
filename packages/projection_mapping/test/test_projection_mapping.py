# Written by Claude Code
"""Check saving, loading and validating the projection mapping file."""

from datetime import datetime, timedelta

from projection_mapping.projection_mapping import load, save, validate

MAPPING = {
    'frame_id': 'world',
    'projector_width': 1920,
    'projector_height': 1080,
    'homography': [[-1200.0, 0.0, 960.0], [0.0, 1200.0, 540.0], [0.0, 0.0, 1.0]],
    'reprojection_error': 0.4,
}


def test_missing_file_means_no_mapping(tmp_path):
    assert load(str(tmp_path / 'projection_mapping.yaml')) is None


def test_save_and_load_round_trip(tmp_path):
    path = str(tmp_path / 'projection_mapping.yaml')
    save(path, MAPPING)
    loaded = load(path)
    # The time it was stored, to the second
    assert abs(datetime.fromisoformat(loaded.pop('measured')) - datetime.now()) < timedelta(
        seconds=5)
    assert loaded == MAPPING


def test_validate():
    assert validate(MAPPING) is None
    assert 'frame_id' in validate({**MAPPING, 'frame_id': ''})
    assert 'empty' in validate({**MAPPING, 'projector_width': 0})
    assert 'finite' in validate({**MAPPING, 'homography': [[float('nan'), 0, 0], [0, 1, 0],
                                                           [0, 0, 1]]})
    assert 'singular' in validate({**MAPPING, 'homography': [[1, 2, 3], [2, 4, 6], [0, 0, 1]]})
