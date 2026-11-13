# Written by Claude Code
"""
Extrinsics API of the setup wizard backend: camera pose and projector calibration of a profile.

Runs the framework's calibration launch files unchanged, as the preview's camera process
(camera_launch_session.start_camera_launch): each starts the camera itself, so the app shows its
live image through the preview endpoints, stops a run with the preview's stop, and the preview's
watchdog ends a run nobody watches any more.

A run has succeeded when its result file is newer than the run's start. The launch's exit code
says nothing: `ros2 launch` exits with 0 also when the calibrator node failed. A failed run
reports the error lines of the launch's output as they are, without parsing them.

What the pose and projector calibration measure is unchanged (quick path): height and tilt of the
camera, the rotation about the vertical and the position along the table from the placeholder;
the homography from the table to the projector, optionally the projector centre.
"""

import datetime
import math
import os
import threading
import time

from ament_index_python.resources import has_resource
from backend_shared_helpers import read_yaml_file
from camera_launch_session import (create_profile_preview_camera, get_camera_launch_session,
                                   read_camera_process_log_lines, start_camera_launch)
from fastapi import APIRouter, HTTPException
from par_framework_core.launch_helpers import (CAMERA_ENTRY_STREAMS_KEY,
                                               get_extrinsics_relative_path,
                                               get_invalid_pose_keys, get_path_in_config_folder,
                                               POSE_ROTATION_KEYS, read_camera_entry,
                                               read_published_camera_pose)
from profile_files import create_profile_launch_context
import projector_blackout_api
from pydantic import BaseModel, Field
import yaml

# What a run calibrates (ExtrinsicsCalibrationStartRequest.calibration_kind)
CALIBRATION_KIND_POSE_BOARD = 'pose_board'
CALIBRATION_KIND_POSE_DEPTH = 'pose_depth'
CALIBRATION_KIND_PROJECTION_MAPPING = 'projection_mapping'
CALIBRATION_KIND_PROJECTOR_CENTER = 'projector_center'
CALIBRATION_KINDS = (CALIBRATION_KIND_POSE_BOARD, CALIBRATION_KIND_POSE_DEPTH,
                     CALIBRATION_KIND_PROJECTION_MAPPING, CALIBRATION_KIND_PROJECTOR_CENTER)
POSE_BOARD_LAUNCH_FILE_NAME = 'camera_pose_calibration_sheet.launch.py'
PROJECTION_LAUNCH_FILE_NAME = 'projection_calibration.launch.py'
# Measures the pose with the camera's depth, for every camera whose entry offers
# DEPTH_REGISTERED_STREAM_NAME; the projector centre needs that stream too
POSE_DEPTH_LAUNCH_FILE_NAME = 'camera_pose_calibration_depth.launch.py'
DEPTH_REGISTERED_STREAM_NAME = 'depth_registered/image_raw'

# Packages the calibration launch files start, with the repository that brings them
CALIBRATION_REPOSITORY_BY_PACKAGE = {
    'camera_pose_calibrator': 'ros2-par-framework-calibration',
    'surface_selector': 'ros2-par-framework-calibration',
    'projection_calibration_server': 'ros2-par-framework-calibration',
    'fiducials_detector': 'ros2-par-framework-fiducials',
}
PACKAGES_NEEDED_BY_CALIBRATION_KIND = {
    CALIBRATION_KIND_POSE_BOARD: ('camera_pose_calibrator',),
    CALIBRATION_KIND_POSE_DEPTH: ('camera_pose_calibrator',),
    CALIBRATION_KIND_PROJECTION_MAPPING: ('surface_selector', 'projection_calibration_server',
                                          'fiducials_detector'),
    CALIBRATION_KIND_PROJECTOR_CENTER: ('surface_selector', 'projection_calibration_server',
                                        'fiducials_detector'),
}

# Phases of a run (ExtrinsicsCalibrationProgress.phase)
RUN_PHASE_RUNNING = 'running'
RUN_PHASE_STORED = 'stored'
RUN_PHASE_FAILED = 'failed'
# Ended by a stop request, by a newer preview or by the preview's watchdog
RUN_PHASE_STOPPED = 'stopped'

# Keys of a pose file that are the pose and its time; every other key is a quality figure of the
# method that measured it (e.g. board_reprojection_error_px, table_rms_mm)
POSE_FILE_MEASURED_KEY = 'measured'
POSE_FILE_HEIGHT_KEY = 'translation.z'
MAPPING_FILE_PROJECTOR_CENTER_KEY = 'projector_center'
LOG_ERROR_MARKERS = ('[ERROR]', 'Traceback', 'Error:')
LOG_ERROR_LINE_COUNT = 8

extrinsics_router = APIRouter()

# The latest run, None before the first; replaced under _extrinsics_run_lock
_extrinsics_run = None
_extrinsics_run_lock = threading.Lock()


class CameraPoseSummary(BaseModel):
    # False while the profile uses the placeholder pose of par_setup.yaml
    is_measured: bool
    # Why the stored file cannot be used, e.g. missing keys; empty otherwise
    pose_file_error_text: str = ''
    # When it was measured, as the file says (ISO 8601 or a hand-written note)
    measured_text: str = ''
    height_above_table_m: float | None = None
    # Angle between the camera's viewing direction (x of its body frame, REP 103) and straight down
    tilt_from_vertical_deg: float | None = None
    # The measuring method's own figures from the file, e.g. board_reprojection_error_px
    quality_figures: dict[str, float | int | str] = {}


class ProjectionMappingSummary(BaseModel):
    is_calibrated: bool
    measured_text: str = ''
    reprojection_error_px: float | None = None
    projector_width_px: int | None = None
    projector_height_px: int | None = None
    has_projector_center: bool = False
    # Measured before the current camera pose: the homography was fitted on the old table plane
    is_older_than_camera_pose: bool = False
    # Why the stored file cannot be used, e.g. it is no valid YAML or lacks the homography; empty
    # otherwise
    mapping_file_error_text: str = ''


class ExtrinsicsState(BaseModel):
    camera_pose: CameraPoseSummary
    projection_mapping: ProjectionMappingSummary
    # The calibration kinds this camera offers now, a subset of CALIBRATION_KINDS
    available_calibration_kinds: list[str]
    # What is not installed for a kind, e.g. 'surface_selector (add ros2-par-framework-calibration
    # to config/nodes.list and run ./scripts/local_build.sh)'; kinds without missing packages are
    # left out
    missing_package_text_by_calibration_kind: dict[str, str]


class ExtrinsicsCalibrationStartRequest(BaseModel):
    profile_name: str
    camera_name: str
    # One of CALIBRATION_KINDS
    calibration_kind: str
    # Only for pose_board: the checkerboard lying on the table, as for the intrinsics
    board_inner_corner_columns: int | None = Field(default=None, ge=2, le=50)
    board_inner_corner_rows: int | None = Field(default=None, ge=2, le=50)
    square_size_m: float | None = Field(default=None, gt=0.0, lt=1.0)


class ExtrinsicsCalibrationStartResponse(BaseModel):
    # The run's camera is the preview with this id: its frames, and stop with this id
    preview_id: int


class ExtrinsicsCalibrationProgress(BaseModel):
    # One of the RUN_PHASE_* values
    phase: str
    calibration_kind: str
    # For failed and stopped: the error lines of the launch's output, as they are
    log_lines: list[str] = []


class _ExtrinsicsRun:
    """One calibration launch, started as the camera of one preview."""

    def __init__(self, preview_id, launch_process, calibration_kind, result_file_path,
                 start_time_s):
        self.preview_id = preview_id
        self.launch_process = launch_process
        self.calibration_kind = calibration_kind
        self.result_file_path = result_file_path
        # time.time(), compared with the result file's modification time
        self.start_time_s = start_time_s
        # The progress once the launch has ended, kept: the preview's watchdog later stops the
        # ended launch too, which would make a failed run look stopped
        self.final_progress = None


@extrinsics_router.get('/api/extrinsics/state')
def get_extrinsics_state(profile_name: str, camera_name: str) -> ExtrinsicsState:
    """Return the profile's camera pose and projector calibration for the camera."""
    preview_camera = create_profile_preview_camera(profile_name, camera_name)
    camera_pose_summary = _read_camera_pose_summary(
        create_profile_launch_context(profile_name), camera_name)
    projection_mapping_summary = _read_projection_mapping_summary(
        _get_extrinsics_file_path(profile_name, 'projection_mapping', camera_name),
        camera_pose_summary)

    available_calibration_kinds = [CALIBRATION_KIND_POSE_BOARD]
    publishes_depth = _does_camera_offer_depth(preview_camera.camera_type)
    if publishes_depth:
        available_calibration_kinds.append(CALIBRATION_KIND_POSE_DEPTH)
    available_calibration_kinds.append(CALIBRATION_KIND_PROJECTION_MAPPING)
    # The centre adds to a stored homography and locates the markers with depth
    if publishes_depth and projection_mapping_summary.is_calibrated:
        available_calibration_kinds.append(CALIBRATION_KIND_PROJECTOR_CENTER)

    missing_package_text_by_calibration_kind = {}
    for calibration_kind in available_calibration_kinds:
        missing_package_text = _get_missing_package_text(calibration_kind)
        if missing_package_text:
            missing_package_text_by_calibration_kind[calibration_kind] = missing_package_text
    return ExtrinsicsState(
        camera_pose=camera_pose_summary,
        projection_mapping=projection_mapping_summary,
        available_calibration_kinds=available_calibration_kinds,
        missing_package_text_by_calibration_kind=missing_package_text_by_calibration_kind)


@extrinsics_router.post('/api/extrinsics/run/start')
def start_extrinsics_calibration(
        request: ExtrinsicsCalibrationStartRequest) -> ExtrinsicsCalibrationStartResponse:
    """Start a calibration launch on the profile's camera, ending the preview that runs now."""
    preview_camera = create_profile_preview_camera(request.profile_name, request.camera_name)
    if request.calibration_kind not in CALIBRATION_KINDS:
        raise HTTPException(status_code=400,
                            detail=f'Unknown calibration_kind {request.calibration_kind!r}: use '
                                   f'one of {", ".join(CALIBRATION_KINDS)}')
    missing_package_text = _get_missing_package_text(request.calibration_kind)
    if missing_package_text:
        raise HTTPException(status_code=409, detail=f'Not installed: {missing_package_text}')
    launch_file_name, launch_arguments, result_file_prefix = _get_calibration_launch(
        request, preview_camera)
    result_file_path = _get_extrinsics_file_path(request.profile_name, result_file_prefix,
                                                 request.camera_name)

    if request.calibration_kind in (CALIBRATION_KIND_PROJECTION_MAPPING,
                                    CALIBRATION_KIND_PROJECTOR_CENTER):
        # The calibration shows its markers on the projector; a black window would cover them
        projector_blackout_api.stop_projector_blackout_for_projection()
    start_time_s = time.time()
    preview_id = start_camera_launch(preview_camera, request.profile_name, launch_file_name,
                                     launch_arguments)
    preview_session = get_camera_launch_session()
    with preview_session.session_lock:
        if preview_session.running_preview_id != preview_id:
            raise HTTPException(status_code=409,
                                detail='Another camera preview started meanwhile; start the '
                                       'calibration again')
        launch_process = preview_session.camera_process

    global _extrinsics_run
    with _extrinsics_run_lock:
        _extrinsics_run = _ExtrinsicsRun(preview_id, launch_process, request.calibration_kind,
                                         result_file_path, start_time_s)
    return ExtrinsicsCalibrationStartResponse(preview_id=preview_id)


@extrinsics_router.get('/api/extrinsics/run/progress')
def get_extrinsics_calibration_progress() -> ExtrinsicsCalibrationProgress:
    """Return whether the latest run still runs, stored its result, failed or was stopped."""
    with _extrinsics_run_lock:
        extrinsics_run = _extrinsics_run
    if extrinsics_run is None:
        raise HTTPException(status_code=409, detail='No extrinsic calibration has run')
    if extrinsics_run.launch_process.poll() is None:
        # Asking for the progress counts as watching, also while no frames are fetched
        _record_preview_request(extrinsics_run.preview_id)
        return ExtrinsicsCalibrationProgress(phase=RUN_PHASE_RUNNING,
                                             calibration_kind=extrinsics_run.calibration_kind)
    with _extrinsics_run_lock:
        if extrinsics_run.final_progress is None:
            extrinsics_run.final_progress = _read_final_progress(extrinsics_run)
        return extrinsics_run.final_progress


def _read_final_progress(extrinsics_run):
    """Return the progress of a run whose launch has ended."""
    if _is_file_newer_than(extrinsics_run.result_file_path, extrinsics_run.start_time_s):
        if not _has_run_stored_its_result(extrinsics_run):
            return ExtrinsicsCalibrationProgress(
                phase=RUN_PHASE_FAILED, calibration_kind=extrinsics_run.calibration_kind,
                log_lines=['The mapping was stored without a projector centre.',
                           *_read_launch_error_lines()])
        return ExtrinsicsCalibrationProgress(phase=RUN_PHASE_STORED,
                                             calibration_kind=extrinsics_run.calibration_kind)
    preview_session = get_camera_launch_session()
    with preview_session.session_lock:
        # A stop clears the running preview id before it ends the launch; a launch that ended
        # by itself keeps it
        was_stopped = preview_session.running_preview_id != extrinsics_run.preview_id
    phase = RUN_PHASE_FAILED
    if was_stopped:
        phase = RUN_PHASE_STOPPED
    return ExtrinsicsCalibrationProgress(phase=phase,
                                         calibration_kind=extrinsics_run.calibration_kind,
                                         log_lines=_read_launch_error_lines())


def _get_calibration_launch(request, preview_camera):
    """
    Return the launch file, its arguments and the result file's prefix (e.g. camera_pose).

    The camera:= argument is added by camera_launch_session.start_camera_launch.
    """
    if request.calibration_kind == CALIBRATION_KIND_POSE_BOARD:
        board_values = (request.board_inner_corner_columns, request.board_inner_corner_rows,
                        request.square_size_m)
        if None in board_values:
            raise HTTPException(status_code=400,
                                detail='pose_board needs board_inner_corner_columns, '
                                       'board_inner_corner_rows and square_size_m')
        square_size_mm = request.square_size_m * 1000.0
        launch_arguments = [f'square_size_mm:={square_size_mm}',
                            f'board_columns:={request.board_inner_corner_columns}',
                            f'board_rows:={request.board_inner_corner_rows}']
        return POSE_BOARD_LAUNCH_FILE_NAME, launch_arguments, 'camera_pose'
    if request.calibration_kind == CALIBRATION_KIND_POSE_DEPTH:
        if not _does_camera_offer_depth(preview_camera.camera_type):
            raise HTTPException(status_code=409,
                                detail=f'{preview_camera.camera_name} has no depth; use '
                                       f'{CALIBRATION_KIND_POSE_BOARD}')
        return POSE_DEPTH_LAUNCH_FILE_NAME, [], 'camera_pose'
    is_projector_center_run = request.calibration_kind == CALIBRATION_KIND_PROJECTOR_CENTER
    launch_arguments = [f'projector_center:={str(is_projector_center_run).lower()}']
    return PROJECTION_LAUNCH_FILE_NAME, launch_arguments, 'projection_mapping'


def _has_run_stored_its_result(extrinsics_run):
    """Return False when a projector centre run wrote its file without the centre."""
    if extrinsics_run.calibration_kind != CALIBRATION_KIND_PROJECTOR_CENTER:
        return True
    mapping = read_yaml_file(extrinsics_run.result_file_path)
    return isinstance(mapping, dict) and MAPPING_FILE_PROJECTOR_CENTER_KEY in mapping


def _read_camera_pose_summary(profile_launch_context, camera_name):
    """Return the measured pose of the camera the launch publishes, with its quality figures."""
    try:
        camera_pose, pose_file_path, is_pose_measured = read_published_camera_pose(
            profile_launch_context, camera_name)
    except (OSError, yaml.YAMLError) as error:
        return CameraPoseSummary(is_measured=False, pose_file_error_text=str(error))
    if not is_pose_measured:
        return CameraPoseSummary(is_measured=False)
    if not isinstance(camera_pose, dict):
        return CameraPoseSummary(is_measured=False,
                                 pose_file_error_text=f'{pose_file_path} holds no keys')
    invalid_pose_keys = get_invalid_pose_keys(camera_pose)
    if invalid_pose_keys:
        return CameraPoseSummary(is_measured=False,
                                 pose_file_error_text=f'{pose_file_path}: missing or not a '
                                                      f'number: {", ".join(invalid_pose_keys)}')
    pose_key_names = {POSE_FILE_HEIGHT_KEY, POSE_FILE_MEASURED_KEY, 'translation.x',
                      'translation.y', *POSE_ROTATION_KEYS}
    quality_figures = {}
    for key_name, key_value in camera_pose.items():
        if key_name in pose_key_names:
            continue
        if isinstance(key_value, (bool, list, dict)) or key_value is None:
            continue
        quality_figures[key_name] = key_value
    rotation_quaternion = [float(camera_pose[key]) for key in POSE_ROTATION_KEYS]
    return CameraPoseSummary(
        is_measured=True,
        measured_text=str(camera_pose.get(POSE_FILE_MEASURED_KEY, '')),
        height_above_table_m=float(camera_pose[POSE_FILE_HEIGHT_KEY]),
        tilt_from_vertical_deg=_compute_tilt_from_vertical_deg(rotation_quaternion),
        quality_figures=quality_figures)


def _compute_tilt_from_vertical_deg(rotation_quaternion):
    """Return the angle between the body frame's x axis (its viewing direction) and down."""
    quaternion_x, quaternion_y, quaternion_z, quaternion_w = rotation_quaternion
    quaternion_norm = math.sqrt(quaternion_x ** 2 + quaternion_y ** 2 + quaternion_z ** 2
                                + quaternion_w ** 2)
    if quaternion_norm == 0.0:
        return None
    quaternion_x /= quaternion_norm
    quaternion_y /= quaternion_norm
    quaternion_z /= quaternion_norm
    quaternion_w /= quaternion_norm
    # The world z component of the rotated x axis: the third row of the rotation matrix's first
    # column
    x_axis_world_z = 2.0 * (quaternion_x * quaternion_z - quaternion_w * quaternion_y)
    downward_cosine = max(-1.0, min(1.0, -x_axis_world_z))
    return math.degrees(math.acos(downward_cosine))


def _read_projection_mapping_summary(mapping_file_path, camera_pose_summary):
    if not os.path.exists(mapping_file_path):
        return ProjectionMappingSummary(is_calibrated=False)
    try:
        mapping = read_yaml_file(mapping_file_path)
    except (OSError, yaml.YAMLError) as error:
        return ProjectionMappingSummary(is_calibrated=False, mapping_file_error_text=str(error))
    if not isinstance(mapping, dict) or 'homography' not in mapping:
        return ProjectionMappingSummary(is_calibrated=False,
                                        mapping_file_error_text=f'{mapping_file_path} holds no '
                                                                f'homography')
    measured_text = str(mapping.get('measured', ''))
    return ProjectionMappingSummary(
        is_calibrated=True,
        measured_text=measured_text,
        reprojection_error_px=_get_optional_float(mapping, 'reprojection_error'),
        projector_width_px=_get_optional_int(mapping, 'projector_width'),
        projector_height_px=_get_optional_int(mapping, 'projector_height'),
        has_projector_center=MAPPING_FILE_PROJECTOR_CENTER_KEY in mapping,
        is_older_than_camera_pose=_is_measured_before(measured_text,
                                                      camera_pose_summary.measured_text))


def _is_measured_before(earlier_measured_text, later_measured_text):
    """Compare two 'measured' times; False when either is no ISO time (e.g. 'by hand')."""
    try:
        earlier_time = datetime.datetime.fromisoformat(earlier_measured_text)
        later_time = datetime.datetime.fromisoformat(later_measured_text)
    except ValueError:
        return False
    return earlier_time < later_time


def _get_optional_float(mapping, key_name):
    key_value = mapping.get(key_name)
    if isinstance(key_value, (int, float)) and not isinstance(key_value, bool):
        return float(key_value)
    return None


def _get_optional_int(mapping, key_name):
    key_value = mapping.get(key_name)
    if isinstance(key_value, int) and not isinstance(key_value, bool):
        return key_value
    return None


def _get_extrinsics_file_path(profile_name, file_prefix, camera_name):
    """Return the path of the named camera's calibration file in the profile."""
    profile_launch_context = create_profile_launch_context(profile_name)
    return get_path_in_config_folder(
        get_extrinsics_relative_path(profile_launch_context, file_prefix, camera_name))


# Written by Claude Code
def _does_camera_offer_depth(camera_type):
    """Return whether the camera type's entry offers depth registered to its colour image."""
    return DEPTH_REGISTERED_STREAM_NAME in read_camera_entry(camera_type)[CAMERA_ENTRY_STREAMS_KEY]


def _get_missing_package_text(calibration_kind):
    """Return which packages the kind needs that are not installed; '' when all are."""
    missing_package_texts = []
    for package_name in PACKAGES_NEEDED_BY_CALIBRATION_KIND[calibration_kind]:
        if has_resource('packages', package_name):
            continue
        repository_name = CALIBRATION_REPOSITORY_BY_PACKAGE[package_name]
        missing_package_texts.append(f'{package_name} (add {repository_name} to '
                                     f'config/nodes.list and run ./scripts/local_build.sh)')
    return ', '.join(missing_package_texts)


def _is_file_newer_than(file_path, start_time_s):
    try:
        return os.path.getmtime(file_path) >= start_time_s
    except OSError:
        return False


def _record_preview_request(preview_id):
    """Count a request as watching the run's preview, so the watchdog keeps its launch running."""
    preview_session = get_camera_launch_session()
    with preview_session.session_lock:
        preview_session.record_preview_request(preview_id)


def _read_launch_error_lines():
    """Return the error lines of the run's output, else its last lines, without colour codes."""
    log_lines = read_camera_process_log_lines()
    error_lines = []
    for log_line in log_lines:
        for log_error_marker in LOG_ERROR_MARKERS:
            if log_error_marker in log_line:
                error_lines.append(log_line)
                break
    if error_lines:
        return error_lines[-LOG_ERROR_LINE_COUNT:]
    return log_lines[-LOG_ERROR_LINE_COUNT:]
