#!/usr/bin/env python3
# Written by Claude Code
"""
Live preview for focusing a camera: the whole frame next to an enlarged crop of its centre, with a sharpness score.

Turn the focus ring until the score reaches its peak; the peak so far is shown next to it. The score is the
variance of the Laplacian in the centre crop, averaged over a few frames because sensor noise at high gain makes
single frames jump. Put something with fine, high-contrast detail (printed text, a marker sheet) under the centre.
The score only compares focus settings of one scene: it changes with the light and the content, so it has no
absolute "sharp" value.

Needs ROS sourced and a camera publishing on /camera/image_raw (any camera the launch files start):
    ros2 launch par_framework_core par.launch.py camera:=blackfly
    .venv/bin/python scripts/focus_preview.py

Keys: q or Esc quits, r resets the peak (after moving the camera or changing the scene).
"""

from collections import deque

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import Image

CAMERA_IMAGE_TOPIC_NAME = '/camera/image_raw'
WINDOW_NAME = 'Focus preview (q: quit, r: reset peak)'

# Height of both panels on screen; the full frame is scaled to it, the centre crop enlarged to it
PREVIEW_PANEL_HEIGHT_PX = 720
# Side of the square centre crop in camera pixels. Enlarged to PREVIEW_PANEL_HEIGHT_PX, so 240 px shows each
# camera pixel as a 3x3 block, enough to judge single-pixel edges
CENTER_CROP_SIDE_PX = 240
SHARPNESS_AVERAGED_FRAME_COUNT = 5

CHANNEL_COUNT_BY_ENCODING = {'mono8': 1, 'bgr8': 3, 'rgb8': 3, 'bgra8': 4}


def convert_image_message_to_gray(image_message):
    """Return the frame as a 2D uint8 array, or None for an encoding this preview does not read."""
    channel_count = CHANNEL_COUNT_BY_ENCODING.get(image_message.encoding)
    if channel_count is None:
        return None
    rows = np.frombuffer(image_message.data, dtype=np.uint8).reshape(image_message.height, image_message.step)
    # step may include padding at the end of each row
    pixel_rows = rows[:, :image_message.width * channel_count]
    if channel_count == 1:
        return pixel_rows
    frame = pixel_rows.reshape(image_message.height, image_message.width, channel_count)
    if image_message.encoding == 'rgb8':
        return cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    if image_message.encoding == 'bgra8':
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def get_center_crop_bounds(frame_height_px, frame_width_px):
    """Return (top, bottom, left, right) of the centre crop, clipped to frames smaller than the crop."""
    crop_side_px = min(CENTER_CROP_SIDE_PX, frame_height_px, frame_width_px)
    top_px = (frame_height_px - crop_side_px) // 2
    left_px = (frame_width_px - crop_side_px) // 2
    return top_px, top_px + crop_side_px, left_px, left_px + crop_side_px


def compute_sharpness(gray_image):
    """Variance of the Laplacian: high when the image has strong fine edges, i.e. is in focus."""
    laplacian = cv2.Laplacian(gray_image, cv2.CV_64F)
    return float(laplacian.var())


def create_full_frame_panel(gray_frame, crop_bounds):
    """Scale the whole frame to the panel height and mark the centre crop and the optical axis' pixel."""
    frame_height_px, frame_width_px = gray_frame.shape
    scale = PREVIEW_PANEL_HEIGHT_PX / frame_height_px
    panel_width_px = round(frame_width_px * scale)
    scaled_frame = cv2.resize(gray_frame, (panel_width_px, PREVIEW_PANEL_HEIGHT_PX), interpolation=cv2.INTER_AREA)
    panel = cv2.cvtColor(scaled_frame, cv2.COLOR_GRAY2BGR)

    top_px, bottom_px, left_px, right_px = crop_bounds
    crop_top_left = (round(left_px * scale), round(top_px * scale))
    crop_bottom_right = (round(right_px * scale), round(bottom_px * scale))
    cv2.rectangle(panel, crop_top_left, crop_bottom_right, (0, 255, 0), 1)

    # Crosshair through the image centre, to see where the camera points on the table
    center_x_px = panel_width_px // 2
    center_y_px = PREVIEW_PANEL_HEIGHT_PX // 2
    cv2.line(panel, (center_x_px, 0), (center_x_px, PREVIEW_PANEL_HEIGHT_PX), (0, 200, 255), 1)
    cv2.line(panel, (0, center_y_px), (panel_width_px, center_y_px), (0, 200, 255), 1)

    size_text = f'{frame_width_px}x{frame_height_px}'
    cv2.putText(panel, size_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    return panel


def create_center_crop_panel(center_crop, sharpness, peak_sharpness):
    """Enlarge the centre crop without smoothing, so single camera pixels stay visible, and print the scores."""
    # Stretch the crop's own brightness range for display only (the score uses the raw pixels), so a dim frame,
    # e.g. behind an infrared filter, still shows its edges
    stretched_crop = cv2.normalize(center_crop, None, 0, 255, cv2.NORM_MINMAX)
    enlarged_crop = cv2.resize(stretched_crop, (PREVIEW_PANEL_HEIGHT_PX, PREVIEW_PANEL_HEIGHT_PX),
                               interpolation=cv2.INTER_NEAREST)
    panel = cv2.cvtColor(enlarged_crop, cv2.COLOR_GRAY2BGR)

    sharpness_fraction_of_peak = 0.0
    if peak_sharpness > 0.0:
        sharpness_fraction_of_peak = sharpness / peak_sharpness
    score_text = f'sharpness {sharpness:8.1f}   peak {peak_sharpness:8.1f}   ({sharpness_fraction_of_peak:4.0%})'
    cv2.putText(panel, score_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # Bar of the current score relative to the peak: full width means as sharp as the best setting so far
    bar_width_px = round((PREVIEW_PANEL_HEIGHT_PX - 20) * min(sharpness_fraction_of_peak, 1.0))
    cv2.rectangle(panel, (10, 45), (10 + bar_width_px, 60), (0, 255, 0), -1)
    return panel


class FocusPreviewNode(Node):
    """Shows the newest camera frame and the centre crop's sharpness."""

    def __init__(self):
        super().__init__('focus_preview')
        # Frames are published BEST_EFFORT; a reliable subscriber would receive nothing
        frame_qos = QoSProfile(depth=1, reliability=QoSReliabilityPolicy.BEST_EFFORT)
        self.create_subscription(Image, CAMERA_IMAGE_TOPIC_NAME, self._on_image_received, frame_qos)
        self.newest_gray_frame = None
        self.recent_sharpness_values = deque(maxlen=SHARPNESS_AVERAGED_FRAME_COUNT)
        self.peak_sharpness = 0.0
        self._has_warned_about_encoding = False
        self.get_logger().info(f'Waiting for frames on {CAMERA_IMAGE_TOPIC_NAME}')

    def _on_image_received(self, image_message):
        gray_frame = convert_image_message_to_gray(image_message)
        if gray_frame is None:
            if not self._has_warned_about_encoding:
                self.get_logger().error(f'Encoding {image_message.encoding} is not supported; '
                                        f'supported: {", ".join(CHANNEL_COUNT_BY_ENCODING)}')
                self._has_warned_about_encoding = True
            return
        self.newest_gray_frame = gray_frame

    def reset_peak_sharpness(self):
        self.peak_sharpness = 0.0
        self.recent_sharpness_values.clear()

    def create_preview_image(self):
        """Return the side-by-side preview of a frame received since the last call, or None if none arrived."""
        gray_frame = self.newest_gray_frame
        if gray_frame is None:
            return None
        # Each frame enters the sharpness average once
        self.newest_gray_frame = None
        crop_bounds = get_center_crop_bounds(*gray_frame.shape)
        top_px, bottom_px, left_px, right_px = crop_bounds
        center_crop = gray_frame[top_px:bottom_px, left_px:right_px]

        self.recent_sharpness_values.append(compute_sharpness(center_crop))
        sharpness = sum(self.recent_sharpness_values) / len(self.recent_sharpness_values)
        self.peak_sharpness = max(self.peak_sharpness, sharpness)

        full_frame_panel = create_full_frame_panel(gray_frame, crop_bounds)
        center_crop_panel = create_center_crop_panel(center_crop, sharpness, self.peak_sharpness)
        return np.hstack([full_frame_panel, center_crop_panel])


def main():
    rclpy.init()
    node = FocusPreviewNode()
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.01)
            preview_image = node.create_preview_image()
            if preview_image is not None:
                cv2.imshow(WINDOW_NAME, preview_image)
            pressed_key = cv2.waitKey(1) & 0xFF
            if pressed_key in (ord('q'), 27):
                break
            if pressed_key == ord('r'):
                node.reset_peak_sharpness()
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
