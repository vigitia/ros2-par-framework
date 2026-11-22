
"""Generate checkerboard.png for camera calibration"""

from pathlib import Path

import cv2
import numpy as np

# 9 x 7 squares give 8 x 6 inner corners, i.e. cameracalibrator --size 8x6
COLS = 9
ROWS = 7
SQUARE_SIZE_PX = 120
# White border around the checkerboard. The outside squares might otherwise not be detected.
MARGIN_PX = 60

BLACK = 0
WHITE = 255


# Co-authored by Claude Code
def main():
    """Render the board, check OpenCV detects it, and write it next to this script."""
    # One value per square. Neighbouring squares differ by one in row + column, so colouring the
    # odd sums white alternates the colours; the top left square is black.
    row_index, col_index = np.indices((ROWS, COLS))
    is_white = (row_index + col_index) % 2 == 1
    board = np.where(is_white, WHITE, BLACK).astype(np.uint8)

    # Enlarge every square to SQUARE_SIZE_PX x SQUARE_SIZE_PX pixels: np.kron replaces each value
    # of board by a block of that size, filled with the value.
    square_block = np.ones((SQUARE_SIZE_PX, SQUARE_SIZE_PX), np.uint8)
    img = np.kron(board, square_block)

    img = cv2.copyMakeBorder(img, top=MARGIN_PX, bottom=MARGIN_PX, left=MARGIN_PX, right=MARGIN_PX,
                             borderType=cv2.BORDER_CONSTANT, value=[WHITE])

    # ROS 2 package cameracalibrator looks for the inner corners, so a board OpenCV cannot detect is useless
    inner_corners = (COLS - 1, ROWS - 1)
    found, _ = cv2.findChessboardCorners(img, inner_corners)
    if not found:
        raise RuntimeError('[generate_checkerboard]: OpenCV does not detect the generated board')

    out_path = Path(__file__).with_name('checkerboard.png')
    cv2.imwrite(str(out_path), img)


if __name__ == '__main__':
    main()
