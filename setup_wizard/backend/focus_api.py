# Written by Claude Code
"""
Focus API of the setup wizard backend: a sharpness score of the previewed camera's image.

For focusing a camera, by turning its lens ring or through a focus setting: the user changes the
focus until the score peaks. The same measure as scripts/focus_preview.py: the variance of the
Laplacian in a square crop at the image centre, averaged over the last few frames because sensor
noise at high gain makes single frames jump. The score only compares focus settings of one scene:
it changes with the light and the content, so it has no absolute "sharp" value.

Generic: it reads the neutral /camera/image_raw of the camera the preview runs
(camera_preview_api), so it works for every camera. The app also gets the crop itself at full
resolution and losslessly, so single-pixel edges can be judged by eye.
"""

from collections import deque
import threading
import time

import camera_preview_api
import cv2
from fastapi import APIRouter, HTTPException, Response
from par_framework_core.launch_helpers import DEFAULT_TOPIC_NAME_CAMERA_IMAGE
from pydantic import BaseModel

# Side of the square centre crop in camera pixels, as in scripts/focus_preview.py: small enough
# that the app can show it enlarged, each camera pixel as a block
CENTER_CROP_SIDE_PX = 240
SHARPNESS_AVERAGED_FRAME_COUNT = 5

focus_router = APIRouter()


class FocusMeasurementState:
    """The sharpness of the frames measured so far, for one preview."""

    def __init__(self):
        self.lock = threading.Lock()
        # A new preview (another camera, a restart) starts a new measurement
        self.preview_id = None
        # The last measured message: each frame enters the average once, however often the app asks
        self.measured_image_message = None
        self.recent_sharpness_values = deque(maxlen=SHARPNESS_AVERAGED_FRAME_COUNT)
        self.peak_sharpness = None
        self.center_crop = None

    def reset(self, preview_id):
        self.preview_id = preview_id
        self.measured_image_message = None
        self.recent_sharpness_values.clear()
        self.peak_sharpness = None
        self.center_crop = None


_focus_measurement_state = FocusMeasurementState()


class FocusState(BaseModel):
    # Averaged over the last frames; None until the first frame was measured
    sharpness: float | None = None
    # Highest sharpness since the preview started or the peak was reset
    peak_sharpness: float | None = None
    frame_width_px: int | None = None
    frame_height_px: int | None = None
    # The measured crop in frame pixels, for drawing it onto the preview
    crop_left_px: int | None = None
    crop_top_px: int | None = None
    crop_side_px: int | None = None


@focus_router.get('/api/focus/state')
def get_focus_state() -> FocusState:
    """Measure the newest frame of the preview and return the averaged sharpness and its peak."""
    image_message, preview_id = _get_newest_camera_image_message()
    state = _focus_measurement_state
    with state.lock:
        if state.preview_id != preview_id:
            state.reset(preview_id)
        if image_message is None:
            return FocusState()
        if image_message is not state.measured_image_message:
            _measure_frame(state, image_message)
        if state.center_crop is None:
            return FocusState()
        sharpness = sum(state.recent_sharpness_values) / len(state.recent_sharpness_values)
        crop_left_px, crop_top_px, crop_side_px = get_center_crop_bounds(image_message.width,
                                                                         image_message.height)
        return FocusState(sharpness=sharpness, peak_sharpness=state.peak_sharpness,
                          frame_width_px=image_message.width,
                          frame_height_px=image_message.height,
                          crop_left_px=crop_left_px, crop_top_px=crop_top_px,
                          crop_side_px=crop_side_px)


@focus_router.post('/api/focus/reset-peak')
def reset_focus_peak() -> None:
    """Forget the peak, e.g. after the camera or the scene under it moved."""
    state = _focus_measurement_state
    with state.lock:
        state.recent_sharpness_values.clear()
        state.peak_sharpness = None
        # Measured again at the next request, so the average is never left empty
        state.measured_image_message = None


@focus_router.get('/api/focus/center-crop')
def get_focus_center_crop() -> Response:
    """Return the last measured centre crop as PNG at full resolution; 204 before the first."""
    state = _focus_measurement_state
    with state.lock:
        center_crop = state.center_crop
    if center_crop is None:
        return Response(status_code=204)
    # PNG, not JPEG: JPEG's compression would blur exactly the fine edges the user judges
    is_encoded, png_bytes = cv2.imencode('.png', center_crop)
    if not is_encoded:
        raise HTTPException(status_code=500, detail='Could not encode the crop as PNG')
    return Response(content=png_bytes.tobytes(), media_type='image/png')


def get_center_crop_bounds(frame_width_px, frame_height_px):
    """Return (left, top, side) of the centre crop, smaller for frames smaller than the crop."""
    crop_side_px = min(CENTER_CROP_SIDE_PX, frame_width_px, frame_height_px)
    crop_left_px = (frame_width_px - crop_side_px) // 2
    crop_top_px = (frame_height_px - crop_side_px) // 2
    return crop_left_px, crop_top_px, crop_side_px


def compute_sharpness(gray_image):
    """Variance of the Laplacian: high when the image has strong fine edges, i.e. is in focus."""
    # Simplification: the same two lines as in scripts/focus_preview.py, which is a standalone
    # script outside any importable package. Upgrade: move both into a shared module once a
    # third user needs them
    laplacian = cv2.Laplacian(gray_image, cv2.CV_64F)
    return float(laplacian.var())


def _get_newest_camera_image_message():
    """Return the newest /camera/image_raw message of the preview (None before one) and its id."""
    session = camera_preview_api.get_camera_preview_session()
    with session.session_lock:
        camera_preview_api.check_camera_process_runs(session)
        # Measuring counts as watching, so the watchdog keeps the camera running
        session.last_preview_request_monotonic_s = time.monotonic()
        session.frame_receiver.subscribe_to_feed(DEFAULT_TOPIC_NAME_CAMERA_IMAGE)
        preview_id = session.running_preview_id
    image_message = session.frame_receiver.get_latest_image_message(
        DEFAULT_TOPIC_NAME_CAMERA_IMAGE)
    return image_message, preview_id


def _measure_frame(state, image_message):
    """Add the frame's centre crop sharpness to the average and raise the peak if needed."""
    frame = camera_preview_api.convert_image_message_to_frame(image_message)
    if frame is None:
        raise HTTPException(status_code=409,
                            detail=f'{DEFAULT_TOPIC_NAME_CAMERA_IMAGE} has the encoding '
                                   f'{image_message.encoding!r}, which the focus measure cannot '
                                   f'read')
    crop_left_px, crop_top_px, crop_side_px = get_center_crop_bounds(image_message.width,
                                                                     image_message.height)
    center_crop = frame[crop_top_px:crop_top_px + crop_side_px,
                        crop_left_px:crop_left_px + crop_side_px]
    gray_center_crop = center_crop
    if center_crop.ndim == 3:
        gray_center_crop = cv2.cvtColor(center_crop, cv2.COLOR_BGR2GRAY)
    state.measured_image_message = image_message
    state.center_crop = center_crop
    state.recent_sharpness_values.append(compute_sharpness(gray_center_crop))
    sharpness = sum(state.recent_sharpness_values) / len(state.recent_sharpness_values)
    if state.peak_sharpness is None or sharpness > state.peak_sharpness:
        state.peak_sharpness = sharpness
