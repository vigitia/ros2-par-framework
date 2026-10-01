# Written by Claude Code
"""Generate checkerboard.png for camera calibration (camera_calibration cameracalibrator)."""

from pathlib import Path

import cv2
import numpy as np

COLS, ROWS = 9, 7  # squares -> 8x6 inner corners, i.e. cameracalibrator --size 8x6
SQUARE = 120  # px
MARGIN = 60  # px, white border so the outer squares have contrast


def main():
    """Render the board, check OpenCV detects it, and write it next to this script."""
    board = (np.indices((ROWS, COLS)).sum(axis=0) % 2 * 255).astype(np.uint8)
    img = np.kron(board, np.ones((SQUARE, SQUARE), np.uint8))
    img = cv2.copyMakeBorder(img, MARGIN, MARGIN, MARGIN, MARGIN,
                             cv2.BORDER_CONSTANT, value=255)

    found, _ = cv2.findChessboardCorners(img, (COLS - 1, ROWS - 1))
    assert found, 'OpenCV does not detect the generated board'

    out = Path(__file__).with_name('checkerboard.png')
    cv2.imwrite(str(out), img)
    print(f'[generate_checkerboard]: wrote {out} ({img.shape[1]}x{img.shape[0]} px)')


if __name__ == '__main__':
    main()
