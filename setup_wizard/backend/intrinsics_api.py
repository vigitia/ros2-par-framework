# Written by Claude Code
"""
Intrinsics API of the setup wizard backend: lens calibration of the previewed camera.

Whether the camera needs a calibration, and the calibration itself, run on the camera the
preview runs (camera_launch_session).

Generic, through ROS conventions only, so it works for any camera driver that follows them:
- Whether a camera needs it comes from one message on its camera_info: none published means
  intrinsics do not apply; an all-zero camera matrix K means uncalibrated; otherwise the
  calibration comes from the calibration file when that file exists, else from the camera itself
  (factory calibration). The file is the one the framework gives the camera at launch
  (profile_cameras.get_camera_intrinsics_file_path), else the one in the driver's camera_info_url
  parameter (camera_info_manager's convention).
- The calibration runs ROS's own camera_calibration library (MonoCalibrator, the code behind
  cameracalibrator) on the camera's frames, without its window: the app shows the detected board,
  the coverage of image position, size and tilt, and the result.
- Saving sends the result to the driver through its set_camera_info; the driver writes its
  calibration file itself. A driver without that service cannot store a calibration.
- A camera whose entry says its calibration comes from the factory publishes it only while it
  runs. While it runs in the wizard, a copy goes into the profile's intrinsics folder
  (factory_camera_info_<camera id>.yaml), so the setup drawing knows its field of view while
  the camera is off.
"""

import datetime
import os
import threading
import time
import urllib.parse

from backend_ros_node import CAMERA_IMAGE_STREAM_NAME
from camera_launch_session import (check_camera_process_runs, get_camera_launch_session,
                                   get_driver_parameter_client, get_preview_topic_name)
from camera_types import read_installed_camera_entry
import cv2
from fastapi import APIRouter, HTTPException, Response
from node_parameters import PARAMETER_SERVICE_TIMEOUT_S, wait_for_service_answer
from par_framework_core.launch_helpers import (CAMERA_ENTRY_INTRINSICS_KEY,
                                               CAMERA_INTRINSICS_SOURCE_FACTORY,
                                               get_unit_intrinsics_file_path)
from profile_cameras import get_camera_intrinsics_file_path
from profile_files import create_profile_launch_context
from pydantic import BaseModel, Field
from rcl_interfaces.msg import ParameterType
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import CameraInfo
from sensor_msgs.srv import SetCameraInfo
import yaml

# The camera's streams this API uses, below its namespace (/cameras/<camera name>/)
CAMERA_INFO_STREAM_NAME = 'camera_info'
SET_CAMERA_INFO_STREAM_NAME = 'set_camera_info'
# Where the camera's intrinsics come from (CameraIntrinsicsState.intrinsics_source)
INTRINSICS_SOURCE_NO_CAMERA_INFO = 'no_camera_info'
INTRINSICS_SOURCE_UNCALIBRATED = 'uncalibrated'
INTRINSICS_SOURCE_CALIBRATION_FILE = 'calibration_file'
INTRINSICS_SOURCE_CAMERA = 'camera'
# camera_info_manager's parameter naming the calibration file, e.g. file:///.../camera_info.yaml
CAMERA_INFO_URL_PARAMETER_NAME = 'camera_info_url'
FILE_URL_SCHEME = 'file'
# How long to wait for one camera_info message from the running camera
CAMERA_INFO_WAIT_TIMEOUT_S = 3.0
# How long the driver may take to write its calibration file
SET_CAMERA_INFO_TIMEOUT_S = 10.0
# The copy of a factory calibration: the unit's intrinsics file name with this prefix. Not the
# name itself, which the launch hands to the driver as its calibration (camera_info_url)
FACTORY_CAMERA_INFO_FILE_NAME_PREFIX = 'factory_'
FACTORY_CAMERA_INFO_HEADER = ('# Factory calibration the camera published, copied by the setup '
                              'wizard while it ran,\n# so the setup drawing knows its field of '
                              'view. Not given to the driver.\n')
# How long the copy waits for the camera's first camera_info (a depth camera starts slowly)
FACTORY_CAMERA_INFO_WAIT_TIMEOUT_S = 30.0

# Phases of a calibration (IntrinsicsCalibrationProgress.phase)
CALIBRATION_PHASE_COLLECTING = 'collecting'
CALIBRATION_PHASE_CALIBRATING = 'calibrating'
CALIBRATION_PHASE_CALIBRATED = 'calibrated'
CALIBRATION_PHASE_FAILED = 'failed'
# The worker looks for a new frame this often while the latest one has been processed already
CALIBRATION_FRAME_POLL_INTERVAL_S = 0.05
CALIBRATION_THREAD_JOIN_TIMEOUT_S = 5.0
CALIBRATION_JPEG_QUALITY_PERCENT = 80

intrinsics_router = APIRouter()

# The running calibration, None while there is none; replaced under _calibration_session_lock
_calibration_session = None
_calibration_session_lock = threading.Lock()
# Factory calibration files being copied now, so a preview started again meanwhile (e.g. the
# camera's next section) does not start a second copy
_factory_camera_info_paths_being_copied = set()
_factory_camera_info_copy_lock = threading.Lock()


class CameraIntrinsicsState(BaseModel):
    # One of the INTRINSICS_SOURCE_* values
    intrinsics_source: str
    # Whether the driver offers its set_camera_info, i.e. can store a new calibration
    can_store_calibration: bool
    # When the calibration file (the framework's, else the one the driver's camera_info_url names)
    # was last written (ISO 8601, local time); empty when it does not exist
    calibration_file_modified_iso: str
    # The image size the camera_info describes; 0 without camera_info
    image_width_px: int
    image_height_px: int


class IntrinsicsCalibrationStartRequest(BaseModel):
    # Inner corners of the checkerboard (where four squares meet), along its two sides
    board_inner_corner_columns: int = Field(ge=2, le=50)
    board_inner_corner_rows: int = Field(ge=2, le=50)
    # The measured edge length of one square of the printed board; it sets the calibration's scale
    square_size_m: float = Field(gt=0.0, lt=1.0)


class CoverageOfBoardPoses(BaseModel):
    # 'X', 'Y', 'Size' or 'Skew', as cameracalibrator names them
    pose_parameter_name: str
    # 0 to 1: how much of the needed variety the views cover so far
    progress_fraction: float


class IntrinsicsCalibrationProgress(BaseModel):
    # One of the CALIBRATION_PHASE_* values
    phase: str
    sample_count: int
    coverage: list[CoverageOfBoardPoses]
    # Enough views to calibrate (cameracalibrator's "good enough")
    is_good_enough: bool
    # After calibrating: how far the board's undistorted corners are from straight lines, in
    # pixels, for the board in the latest frame; None without a board in view
    linear_error_px: float | None = None
    # After calibrating: focal lengths and principal point in pixels, distortion coefficients
    focal_length_x_px: float | None = None
    focal_length_y_px: float | None = None
    principal_point_x_px: float | None = None
    principal_point_y_px: float | None = None
    distortion_coefficients: list[float] = []
    # Why the calibration failed; empty otherwise
    error_text: str = ''


class IntrinsicsSaveResponse(BaseModel):
    # The driver's answer, e.g. where it wrote the file
    status_message: str


class _IntrinsicsCalibrationSession:
    """One calibration on the camera of one preview, fed with its frames by a worker thread."""

    def __init__(self, preview_id, mono_calibrator):
        self.preview_id = preview_id
        # Only the worker and the calibration thread use the calibrator, under this lock
        self.mono_calibrator = mono_calibrator
        self.calibrator_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.worker_thread = None
        # What the endpoints read, copied out of the calibrator under this lock, so they never wait
        # for a frame being processed or for the calibration
        self.result_lock = threading.Lock()
        self.phase = CALIBRATION_PHASE_COLLECTING
        self.sample_count = 0
        self.coverage = []
        self.is_good_enough = False
        self.linear_error_px = None
        self.annotated_frame = None
        self.error_text = ''


@intrinsics_router.get('/api/intrinsics/camera-state')
def get_camera_intrinsics_state() -> CameraIntrinsicsState:
    """Tell where the previewed camera's intrinsics come from; 503 while it is still starting."""
    return _read_camera_intrinsics_state(get_camera_launch_session())


def _read_camera_intrinsics_state(preview_session):
    """Return where the running camera's intrinsics come from (CameraIntrinsicsState)."""
    # Raises 503 until the driver node is up, so a starting camera is not taken for one
    # without camera_info.
    driver_node_name, parameter_client = get_driver_parameter_client(preview_session)
    preview_ros_node = preview_session.preview_ros_node
    with preview_session.session_lock:
        preview_camera = preview_session.preview_camera
        profile_name = preview_session.profile_name
        camera_info_topic_name = get_preview_topic_name(preview_session, CAMERA_INFO_STREAM_NAME)
        set_camera_info_service_name = get_preview_topic_name(preview_session,
                                                              SET_CAMERA_INFO_STREAM_NAME)
    can_store_calibration = _has_service(preview_ros_node, set_camera_info_service_name)
    # The file the framework gave the camera, else the one the driver names under the usual
    # parameter: drivers spell that parameter differently (e.g. camerainfo_url), the framework's
    # file is known whatever the spelling
    calibration_file_path = None
    if profile_name is not None and preview_camera.is_profile_camera:
        calibration_file_path = get_camera_intrinsics_file_path(profile_name,
                                                                preview_camera.camera_name)
    if calibration_file_path is None:
        calibration_file_path = _read_calibration_file_path(parameter_client)
    calibration_file_modified_iso = ''
    if calibration_file_path and os.path.isfile(calibration_file_path):
        modified_time_s = os.path.getmtime(calibration_file_path)
        calibration_file_modified_iso = datetime.datetime.fromtimestamp(
            modified_time_s).isoformat(timespec='seconds')

    if preview_ros_node.count_publishers(camera_info_topic_name) == 0:
        return CameraIntrinsicsState(
            intrinsics_source=INTRINSICS_SOURCE_NO_CAMERA_INFO,
            can_store_calibration=can_store_calibration,
            calibration_file_modified_iso=calibration_file_modified_iso,
            image_width_px=0, image_height_px=0)
    camera_info_message = _receive_one_camera_info(preview_ros_node, camera_info_topic_name)
    if camera_info_message is None:
        raise HTTPException(status_code=503,
                            detail=f'{driver_node_name} has sent no camera_info yet')

    # Only the camera entry tells a factory calibration apart: some drivers publish a filled-in
    # camera matrix while uncalibrated
    camera_entry = read_installed_camera_entry(preview_camera.camera_type)
    if camera_entry[CAMERA_ENTRY_INTRINSICS_KEY] == CAMERA_INTRINSICS_SOURCE_FACTORY:
        intrinsics_source = INTRINSICS_SOURCE_CAMERA
    elif calibration_file_modified_iso:
        # The file counts, not the live camera_info: some drivers publish a calibration they
        # stored through set_camera_info only after a restart
        intrinsics_source = INTRINSICS_SOURCE_CALIBRATION_FILE
    else:
        intrinsics_source = INTRINSICS_SOURCE_UNCALIBRATED
    return CameraIntrinsicsState(
        intrinsics_source=intrinsics_source,
        can_store_calibration=can_store_calibration,
        calibration_file_modified_iso=calibration_file_modified_iso,
        image_width_px=camera_info_message.width,
        image_height_px=camera_info_message.height)


@intrinsics_router.post('/api/intrinsics/calibration/start')
def start_intrinsics_calibration(request: IntrinsicsCalibrationStartRequest) -> None:
    """Start collecting board views from the previewed camera, ending an earlier calibration."""
    chessboard_info_class, patterns_class, mono_calibrator_class = _import_camera_calibration()
    preview_session = get_camera_launch_session()
    _check_calibration_may_replace_intrinsics(_read_camera_intrinsics_state(preview_session))
    with preview_session.session_lock:
        check_camera_process_runs(preview_session)
        preview_id = preview_session.running_preview_id
        image_topic_name = get_preview_topic_name(preview_session, CAMERA_IMAGE_STREAM_NAME)
        preview_session.preview_ros_node.subscribe_to_feed(image_topic_name)
    chessboard_info = chessboard_info_class(
        'chessboard', request.board_inner_corner_columns, request.board_inner_corner_rows,
        request.square_size_m)
    mono_calibrator = mono_calibrator_class([chessboard_info], pattern=patterns_class.Chessboard)

    global _calibration_session
    with _calibration_session_lock:
        _stop_calibration_session(_calibration_session)
        calibration_session = _IntrinsicsCalibrationSession(preview_id, mono_calibrator)
        calibration_session.worker_thread = threading.Thread(
            target=_feed_frames_to_calibrator,
            args=(calibration_session, preview_session, image_topic_name),
            daemon=True)
        calibration_session.worker_thread.start()
        _calibration_session = calibration_session


@intrinsics_router.get('/api/intrinsics/calibration/progress')
def get_intrinsics_calibration_progress() -> IntrinsicsCalibrationProgress:
    """Return the coverage so far, and the result once calibrated."""
    calibration_session = _get_calibration_session()
    _record_preview_request()
    with calibration_session.result_lock:
        calibration_progress = IntrinsicsCalibrationProgress(
            phase=calibration_session.phase,
            sample_count=calibration_session.sample_count,
            coverage=list(calibration_session.coverage),
            is_good_enough=calibration_session.is_good_enough,
            linear_error_px=calibration_session.linear_error_px,
            error_text=calibration_session.error_text)
        phase = calibration_session.phase
    if phase == CALIBRATION_PHASE_CALIBRATED:
        # Calibrated: the calibrator is no longer written to, except by handle_msg's display part
        with calibration_session.calibrator_lock:
            camera_matrix = calibration_session.mono_calibrator.intrinsics
            distortion = calibration_session.mono_calibrator.distortion
            calibration_progress.focal_length_x_px = float(camera_matrix[0, 0])
            calibration_progress.focal_length_y_px = float(camera_matrix[1, 1])
            calibration_progress.principal_point_x_px = float(camera_matrix[0, 2])
            calibration_progress.principal_point_y_px = float(camera_matrix[1, 2])
            calibration_progress.distortion_coefficients = [float(coefficient)
                                                            for coefficient in distortion.flat]
    return calibration_progress


@intrinsics_router.get('/api/intrinsics/calibration/frame')
def get_intrinsics_calibration_frame() -> Response:
    """Return the latest frame with the detected board drawn in (rectified once calibrated)."""
    calibration_session = _get_calibration_session()
    _record_preview_request()
    with calibration_session.result_lock:
        annotated_frame = calibration_session.annotated_frame
    if annotated_frame is None:
        return Response(status_code=204)
    jpeg_quality = [cv2.IMWRITE_JPEG_QUALITY, CALIBRATION_JPEG_QUALITY_PERCENT]
    is_encoded, jpeg_bytes = cv2.imencode('.jpg', annotated_frame, jpeg_quality)
    if not is_encoded:
        raise HTTPException(status_code=500, detail='Could not encode the frame as JPEG')
    return Response(content=jpeg_bytes.tobytes(), media_type='image/jpeg')


@intrinsics_router.post('/api/intrinsics/calibration/calibrate')
def calibrate_intrinsics() -> None:
    """Compute the calibration from the collected views, in the background (see progress)."""
    calibration_session = _get_calibration_session()
    with calibration_session.result_lock:
        if calibration_session.phase != CALIBRATION_PHASE_COLLECTING:
            raise HTTPException(status_code=409,
                                detail=f'The calibration is {calibration_session.phase}')
        if not calibration_session.is_good_enough:
            raise HTTPException(status_code=409,
                                detail='Not enough different views of the board yet')
        calibration_session.phase = CALIBRATION_PHASE_CALIBRATING
    # Can take long with many views of large images, so the request does not wait for it
    threading.Thread(target=_run_calibration, args=(calibration_session,), daemon=True).start()


@intrinsics_router.post('/api/intrinsics/calibration/save')
def save_intrinsics_calibration() -> IntrinsicsSaveResponse:
    """Send the calibration to the driver, which stores it in its calibration file."""
    calibration_session = _get_calibration_session()
    with calibration_session.result_lock:
        if calibration_session.phase != CALIBRATION_PHASE_CALIBRATED:
            raise HTTPException(status_code=409, detail='Nothing calibrated yet')
    preview_session = get_camera_launch_session()
    # Checked again right before writing: nothing may replace a camera's own calibration
    _check_calibration_may_replace_intrinsics(_read_camera_intrinsics_state(preview_session))
    with calibration_session.calibrator_lock:
        camera_info_message = calibration_session.mono_calibrator.as_message()
    preview_ros_node = preview_session.preview_ros_node
    with preview_session.session_lock:
        set_camera_info_service_name = get_preview_topic_name(preview_session,
                                                              SET_CAMERA_INFO_STREAM_NAME)
    set_camera_info_client = preview_ros_node.create_client(SetCameraInfo,
                                                            set_camera_info_service_name)
    try:
        if not set_camera_info_client.wait_for_service(
                timeout_sec=PARAMETER_SERVICE_TIMEOUT_S):
            raise HTTPException(status_code=409,
                                detail=f'The camera offers no {set_camera_info_service_name}, '
                                       f'so it cannot store a calibration')
        set_camera_info_request = SetCameraInfo.Request(camera_info=camera_info_message)
        set_camera_info_answer = wait_for_service_answer(
            set_camera_info_client.call_async(set_camera_info_request),
            timeout_s=SET_CAMERA_INFO_TIMEOUT_S)
    finally:
        preview_ros_node.destroy_client(set_camera_info_client)
    if not set_camera_info_answer.success:
        raise HTTPException(status_code=409,
                            detail=f'The driver did not store the calibration: '
                                   f'{set_camera_info_answer.status_message}')
    return IntrinsicsSaveResponse(status_message=set_camera_info_answer.status_message)


@intrinsics_router.post('/api/intrinsics/calibration/stop')
def stop_intrinsics_calibration() -> None:
    """End the calibration and forget its views; the camera keeps running."""
    global _calibration_session
    with _calibration_session_lock:
        _stop_calibration_session(_calibration_session)
        _calibration_session = None


def _check_calibration_may_replace_intrinsics(camera_intrinsics_state):
    """Raise 409 unless a new calibration may be stored for this camera."""
    # A camera that brings its own calibration (e.g. measured in the factory) keeps it: a file
    # stored through set_camera_info would replace it for good in the driver's eyes.
    intrinsics_source = camera_intrinsics_state.intrinsics_source
    if intrinsics_source == INTRINSICS_SOURCE_CAMERA:
        raise HTTPException(status_code=409,
                            detail='The camera brings its own calibration, which is never '
                                   'replaced from here')
    if intrinsics_source == INTRINSICS_SOURCE_NO_CAMERA_INFO:
        raise HTTPException(status_code=409,
                            detail='The camera publishes no camera_info, so there is nothing to '
                                   'calibrate')
    if not camera_intrinsics_state.can_store_calibration:
        raise HTTPException(status_code=409,
                            detail=f'The camera offers no {SET_CAMERA_INFO_STREAM_NAME}, so it '
                                   f'cannot store a calibration')


def _import_camera_calibration():
    """Return ChessboardInfo, Patterns and MonoCalibrator, naming the package when missing."""
    try:
        from camera_calibration.calibrator import ChessboardInfo, Patterns
        from camera_calibration.mono_calibrator import MonoCalibrator
    except ImportError as error:
        ros_distro = os.environ.get('ROS_DISTRO', '<distro>')
        raise HTTPException(status_code=500,
                            detail=f'The ROS package camera_calibration is missing ({error}): '
                                   f'sudo apt install ros-{ros_distro}-camera-calibration'
                            ) from error
    return ChessboardInfo, Patterns, MonoCalibrator


def _has_service(preview_ros_node, wanted_service_name):
    for service_name, _ in preview_ros_node.get_service_names_and_types():
        if service_name == wanted_service_name:
            return True
    return False


def _read_calibration_file_path(parameter_client):
    """Return the local file the driver's camera_info_url names; '' without a file URL."""
    parameter_values = wait_for_service_answer(
        parameter_client.get_parameters([CAMERA_INFO_URL_PARAMETER_NAME])).values
    if not parameter_values or parameter_values[0].type != ParameterType.PARAMETER_STRING:
        return ''
    # Simplification: only file:// URLs; camera_info_manager also knows package:// URLs, which
    # would need the package's share folder. Upgrade: resolve them with ament_index_python.
    parsed_url = urllib.parse.urlparse(parameter_values[0].string_value)
    if parsed_url.scheme != FILE_URL_SCHEME:
        return ''
    return urllib.parse.unquote(parsed_url.path)


def _receive_one_camera_info(preview_ros_node, camera_info_topic_name):
    """Return one camera_info message of the running camera, None after the timeout."""
    camera_info_received_event = threading.Event()
    received_messages = []

    def keep_camera_info(camera_info_message):
        received_messages.append(camera_info_message)
        camera_info_received_event.set()

    # BEST_EFFORT receives from reliable and best-effort publishers alike
    camera_info_qos = QoSProfile(depth=1, history=QoSHistoryPolicy.KEEP_LAST,
                                 reliability=QoSReliabilityPolicy.BEST_EFFORT)
    camera_info_subscription = preview_ros_node.create_subscription(
        CameraInfo, camera_info_topic_name, keep_camera_info, camera_info_qos)
    try:
        camera_info_received_event.wait(timeout=CAMERA_INFO_WAIT_TIMEOUT_S)
    finally:
        preview_ros_node.destroy_subscription(camera_info_subscription)
    if not received_messages:
        return None
    return received_messages[0]


def _get_calibration_session():
    calibration_session = _calibration_session
    if calibration_session is None:
        raise HTTPException(status_code=409, detail='No intrinsic calibration is running')
    return calibration_session


def _record_preview_request():
    """Count a calibration request as watching the preview, so the watchdog keeps the camera."""
    preview_session = get_camera_launch_session()
    with preview_session.session_lock:
        preview_session.record_preview_request()


def _stop_calibration_session(calibration_session):
    if calibration_session is None:
        return
    calibration_session.stop_event.set()
    if calibration_session.worker_thread is not None:
        calibration_session.worker_thread.join(timeout=CALIBRATION_THREAD_JOIN_TIMEOUT_S)


def _set_calibration_failed(calibration_session, error_text):
    with calibration_session.result_lock:
        calibration_session.phase = CALIBRATION_PHASE_FAILED
        calibration_session.error_text = error_text


def _feed_frames_to_calibrator(calibration_session, preview_session, image_topic_name):
    """Hand every new frame to the calibrator and keep what the endpoints show."""
    last_image_message = None
    while not calibration_session.stop_event.is_set():
        if preview_session.running_preview_id != calibration_session.preview_id:
            _set_calibration_failed(calibration_session, 'The camera stopped')
            return
        image_message = preview_session.preview_ros_node.get_latest_image_message(
            image_topic_name)
        with calibration_session.result_lock:
            is_calibrating = calibration_session.phase == CALIBRATION_PHASE_CALIBRATING
        if image_message is None or image_message is last_image_message or is_calibrating:
            calibration_session.stop_event.wait(timeout=CALIBRATION_FRAME_POLL_INTERVAL_S)
            continue
        last_image_message = image_message
        try:
            with calibration_session.calibrator_lock:
                mono_drawable = calibration_session.mono_calibrator.handle_msg(image_message)
                sample_count = len(calibration_session.mono_calibrator.db)
                is_good_enough = bool(calibration_session.mono_calibrator.goodenough)
        except Exception as error:
            # e.g. an encoding cv_bridge cannot turn into gray; the calibration cannot go on
            _set_calibration_failed(calibration_session, f'Cannot process the frames: {error}')
            return
        _keep_calibration_results(calibration_session, mono_drawable, sample_count, is_good_enough)


def _keep_calibration_results(calibration_session, mono_drawable, sample_count, is_good_enough):
    coverage = []
    # params: (name, lowest, highest, progress) per pose parameter; None before the first view
    if mono_drawable.params is not None:
        for pose_parameter_name, _, _, progress_fraction in mono_drawable.params:
            coverage.append(CoverageOfBoardPoses(pose_parameter_name=pose_parameter_name,
                                                 progress_fraction=float(progress_fraction)))
    linear_error_px = None
    if mono_drawable.linear_error >= 0:
        linear_error_px = float(mono_drawable.linear_error)
    with calibration_session.result_lock:
        calibration_session.annotated_frame = mono_drawable.scrib
        calibration_session.coverage = coverage
        calibration_session.sample_count = sample_count
        calibration_session.is_good_enough = is_good_enough
        calibration_session.linear_error_px = linear_error_px


def _run_calibration(calibration_session):
    try:
        with calibration_session.calibrator_lock:
            calibration_session.mono_calibrator.do_calibration()
    except Exception as error:
        _set_calibration_failed(calibration_session, f'The calibration failed: {error}')
        return
    with calibration_session.result_lock:
        calibration_session.phase = CALIBRATION_PHASE_CALIBRATED


def get_factory_camera_info_file_path(profile_launch_context, camera_type, serial):
    """Return where the copy of a unit's factory calibration lives in the profile."""
    calibration_file_path = get_unit_intrinsics_file_path(profile_launch_context, camera_type,
                                                          serial)
    intrinsics_folder_path, calibration_file_name = os.path.split(calibration_file_path)
    return os.path.join(intrinsics_folder_path,
                        FACTORY_CAMERA_INFO_FILE_NAME_PREFIX + calibration_file_name)


def start_copying_factory_camera_info(profile_name, preview_camera):
    """
    Copy the running camera's factory calibration into the profile, in the background.

    Only for a profile's camera whose entry says factory, and only while no copy exists yet.
    """
    if profile_name is None or not preview_camera.is_profile_camera:
        return
    camera_entry = read_installed_camera_entry(preview_camera.camera_type)
    if camera_entry[CAMERA_ENTRY_INTRINSICS_KEY] != CAMERA_INTRINSICS_SOURCE_FACTORY:
        return
    factory_camera_info_path = get_factory_camera_info_file_path(
        create_profile_launch_context(profile_name), preview_camera.camera_type,
        preview_camera.serial)
    if os.path.exists(factory_camera_info_path):
        return
    with _factory_camera_info_copy_lock:
        if factory_camera_info_path in _factory_camera_info_paths_being_copied:
            return
        _factory_camera_info_paths_being_copied.add(factory_camera_info_path)
    preview_session = get_camera_launch_session()
    with preview_session.session_lock:
        camera_process = preview_session.camera_process
    copy_thread = threading.Thread(target=_copy_factory_camera_info,
                                   args=(preview_session, camera_process,
                                         factory_camera_info_path),
                                   daemon=True)
    copy_thread.start()


def _copy_factory_camera_info(preview_session, camera_process, factory_camera_info_path):
    """Wait for the camera's camera_info while its process runs, then write it to the file."""
    try:
        deadline_monotonic_s = time.monotonic() + FACTORY_CAMERA_INFO_WAIT_TIMEOUT_S
        while time.monotonic() < deadline_monotonic_s:
            with preview_session.session_lock:
                # Another camera or a calibration launch replaced it: its info is not this one's
                if preview_session.camera_process is not camera_process:
                    return
                camera_info_topic_name = get_preview_topic_name(preview_session,
                                                                CAMERA_INFO_STREAM_NAME)
            camera_info_message = _receive_one_camera_info(preview_session.preview_ros_node,
                                                           camera_info_topic_name)
            if camera_info_message is None:
                continue
            # An all-zero camera matrix: the camera knows no calibration after all
            if camera_info_message.k[0] == 0.0:
                return
            _write_camera_info_file(factory_camera_info_path, camera_info_message)
            return
    finally:
        with _factory_camera_info_copy_lock:
            _factory_camera_info_paths_being_copied.discard(factory_camera_info_path)


def _write_camera_info_file(file_path, camera_info_message):
    """Write the message in camera_calibration's YAML format, the one calibration files use."""
    distortion_values = [float(value) for value in camera_info_message.d]
    camera_info_document = {
        'image_width': int(camera_info_message.width),
        'image_height': int(camera_info_message.height),
        'camera_name': camera_info_message.header.frame_id,
        'camera_matrix': {'rows': 3, 'cols': 3,
                          'data': [float(value) for value in camera_info_message.k]},
        'distortion_model': camera_info_message.distortion_model,
        'distortion_coefficients': {'rows': 1, 'cols': len(distortion_values),
                                    'data': distortion_values},
        'rectification_matrix': {'rows': 3, 'cols': 3,
                                 'data': [float(value) for value in camera_info_message.r]},
        'projection_matrix': {'rows': 3, 'cols': 4,
                              'data': [float(value) for value in camera_info_message.p]},
    }
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as camera_info_file:
        camera_info_file.write(FACTORY_CAMERA_INFO_HEADER)
        yaml.safe_dump(camera_info_document, camera_info_file, sort_keys=False)
