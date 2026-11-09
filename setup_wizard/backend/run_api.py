# Written by Claude Code
"""
Run API of the setup wizard backend: starts and stops a profile as the framework, like
`ros2 launch par_framework_core par.launch.py profile:=<name>` in a terminal.

One run at a time. The launch runs as a subprocess in its own process group, so stopping reaches
every node it started. Its output goes to a log file, of which the state shows the last error
lines when the run ends on its own.
"""

import atexit
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading

import camera_preview_api
from fastapi import APIRouter, HTTPException
import profiles_api
from pydantic import BaseModel

RUN_LAUNCH_FILE_NAME = 'par.launch.py'
RUN_LOG_PATH = os.path.join(tempfile.gettempdir(), 'par_setup_wizard_run.log')
RUN_PROCESS_STOP_TIMEOUT_S = 15.0
RUN_LOG_TAIL_LINE_COUNT = 12
# The framework's large camera images need this transport, as in the repository's README
FASTDDS_TRANSPORTS_ENVIRONMENT_NAME = 'FASTDDS_BUILTIN_TRANSPORTS'
FASTDDS_TRANSPORTS_VALUE = 'LARGE_DATA'
ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

# What the state reports: no run yet or stopped by the user, running, or ended on its own
RUN_PHASE_IDLE = 'idle'
RUN_PHASE_RUNNING = 'running'
RUN_PHASE_ENDED = 'ended'

run_router = APIRouter()
_run_lock = threading.Lock()
_run_process = None
_run_profile_name = None
_was_run_stopped_by_user = False


class RunStartRequest(BaseModel):
    profile_name: str


class RunState(BaseModel):
    # One of the RUN_PHASE_* values
    phase: str
    profile_name: str | None = None
    # For ended: the last lines of the launch's output, as they are
    log_lines: list[str] = []


@run_router.post('/api/run/start')
def start_run(request: RunStartRequest) -> RunState:
    """Start the profile as the framework; stops a camera preview first, which holds the camera."""
    global _run_process, _run_profile_name, _was_run_stopped_by_user
    profiles_api.check_profile_exists(request.profile_name)
    ros2_executable_path = shutil.which('ros2')
    if ros2_executable_path is None:
        raise HTTPException(status_code=500,
                            detail='ros2 not found: start the backend in a bash with ROS and the '
                                   'workspace sourced')
    with _run_lock:
        if _run_process is not None and _run_process.poll() is None:
            raise HTTPException(status_code=409, detail='A profile is running already')
        camera_preview_api.stop_camera_preview(
            camera_preview_api.CameraPreviewStopRequest(preview_id=None))
        launch_environment = dict(os.environ)
        launch_environment.setdefault(FASTDDS_TRANSPORTS_ENVIRONMENT_NAME,
                                      FASTDDS_TRANSPORTS_VALUE)
        launch_command = [ros2_executable_path, 'launch', 'par_framework_core',
                          RUN_LAUNCH_FILE_NAME, f'profile:={request.profile_name}']
        with open(RUN_LOG_PATH, 'w') as run_log_file:
            _run_process = subprocess.Popen(launch_command, stdout=run_log_file,
                                            stderr=subprocess.STDOUT, start_new_session=True,
                                            env=launch_environment)
        _run_profile_name = request.profile_name
        _was_run_stopped_by_user = False
        return _read_run_state()


@run_router.get('/api/run/state')
def get_run_state() -> RunState:
    """Tell whether a profile runs, and after an end on its own why."""
    with _run_lock:
        return _read_run_state()


@run_router.post('/api/run/stop')
def stop_run() -> RunState:
    """Stop the running profile: SIGINT like Ctrl+C, then SIGTERM, then SIGKILL."""
    with _run_lock:
        _stop_run_process()
        return _read_run_state()


def _read_run_state() -> RunState:
    """Return the state; hold the lock."""
    if _run_process is None:
        return RunState(phase=RUN_PHASE_IDLE)
    if _run_process.poll() is None:
        return RunState(phase=RUN_PHASE_RUNNING, profile_name=_run_profile_name)
    if _was_run_stopped_by_user:
        return RunState(phase=RUN_PHASE_IDLE, profile_name=_run_profile_name)
    return RunState(phase=RUN_PHASE_ENDED, profile_name=_run_profile_name,
                    log_lines=_read_run_log_tail())


def _stop_run_process() -> None:
    """End the launch and the nodes it started; hold the lock."""
    global _was_run_stopped_by_user
    if _run_process is None or _run_process.poll() is not None:
        return
    _was_run_stopped_by_user = True
    for stop_signal in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(_run_process.pid, stop_signal)
        except ProcessLookupError:
            return
        try:
            _run_process.wait(timeout=RUN_PROCESS_STOP_TIMEOUT_S)
            return
        except subprocess.TimeoutExpired:
            continue


def _read_run_log_tail() -> list[str]:
    try:
        with open(RUN_LOG_PATH) as run_log_file:
            log_lines = run_log_file.read().splitlines()
    except OSError:
        return []
    cleaned_lines = [ANSI_ESCAPE_PATTERN.sub('', log_line) for log_line in log_lines]
    return cleaned_lines[-RUN_LOG_TAIL_LINE_COUNT:]


def _stop_run_at_exit() -> None:
    """Do not leave the framework running when the backend ends."""
    with _run_lock:
        _stop_run_process()


atexit.register(_stop_run_at_exit)
