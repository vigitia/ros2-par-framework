# Written by Claude Code
"""
Image conversion for the setup wizard backend: a sensor_msgs/Image as an OpenCV frame.

8-bit images keep their channels (gray or BGR); depth and 16-bit images are scaled to 8-bit gray,
their valid pixels' range stretched over 0-255, so every feed of a camera can be shown. Used by
the preview (camera_preview_api.py) and the focus measure (focus_api.py).
"""

import cv2
import numpy as np

# 8-bit encodings shown as they are, with their channel count
CHANNEL_COUNT_BY_8_BIT_ENCODING = {'mono8': 1, '8UC1': 1, 'bgr8': 3, 'rgb8': 3, '8UC3': 3,
                                   'bgra8': 4, 'rgba8': 4}
# Encodings of depth and infrared images, scaled to 8 bit for the preview; NumPy type per encoding
NUMPY_TYPE_BY_SCALED_ENCODING = {'mono16': np.uint16, '16UC1': np.uint16, '32FC1': np.float32}
# The share of pixels allowed to be darker or brighter than the scaled range, so a few extreme
# pixels (e.g. reflections in infrared) do not leave the rest of the image black.
SCALED_FEED_CLIPPED_PERCENT = 1.0


def convert_image_message_to_frame(image_message):
    """Return the frame at full size as a uint8 array (gray or BGR); None for other encodings."""
    encoding = image_message.encoding
    if encoding in CHANNEL_COUNT_BY_8_BIT_ENCODING:
        return _read_8_bit_frame(image_message)
    if encoding in NUMPY_TYPE_BY_SCALED_ENCODING:
        return _read_scaled_frame(image_message)
    return None


def _read_8_bit_frame(image_message):
    """Return an 8-bit image as gray or BGR, as OpenCV expects."""
    channel_count = CHANNEL_COUNT_BY_8_BIT_ENCODING[image_message.encoding]
    rows = np.frombuffer(image_message.data, dtype=np.uint8).reshape(image_message.height,
                                                                     image_message.step)
    # step may include padding at the end of each row
    pixel_rows = rows[:, :image_message.width * channel_count]
    if channel_count == 1:
        return pixel_rows
    frame = pixel_rows.reshape(image_message.height, image_message.width, channel_count)
    if image_message.encoding == 'rgb8':
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    if image_message.encoding == 'bgra8':
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    if image_message.encoding == 'rgba8':
        return cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
    return frame


def _read_scaled_frame(image_message):
    """Return a depth or 16-bit image as 8-bit gray, its valid pixels' range stretched to 0-255."""
    numpy_type = np.dtype(NUMPY_TYPE_BY_SCALED_ENCODING[image_message.encoding])
    if image_message.is_bigendian:
        numpy_type = numpy_type.newbyteorder('>')
    bytes_per_pixel = numpy_type.itemsize
    rows = np.frombuffer(image_message.data, dtype=np.uint8).reshape(image_message.height,
                                                                     image_message.step)
    pixel_rows = rows[:, :image_message.width * bytes_per_pixel]
    frame_values = np.ascontiguousarray(pixel_rows).view(numpy_type).astype(np.float32)
    # 0 and NaN mean "no measurement" in depth images; they stay black
    is_valid_pixel = np.isfinite(frame_values) & (frame_values > 0)
    gray_frame = np.zeros(frame_values.shape, dtype=np.uint8)
    if not np.any(is_valid_pixel):
        return gray_frame
    valid_values = frame_values[is_valid_pixel]
    lowest_shown_value = np.percentile(valid_values, SCALED_FEED_CLIPPED_PERCENT)
    highest_shown_value = np.percentile(valid_values, 100 - SCALED_FEED_CLIPPED_PERCENT)
    shown_value_span = max(highest_shown_value - lowest_shown_value, 1e-6)
    scaled_values = (frame_values - lowest_shown_value) / shown_value_span * 255
    gray_frame[is_valid_pixel] = np.clip(scaled_values[is_valid_pixel], 0, 255).astype(np.uint8)
    return gray_frame
