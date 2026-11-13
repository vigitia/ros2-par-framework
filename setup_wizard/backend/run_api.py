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
import subprocess
import tempfile

from backend_shared_helpers import get_ros2_executable_path, read_log_lines
from camera_launch_session import stop_camera_launch
from fastapi import APIRouter, HTTPException
from process_groups import LAUNCH_STOP_SIGNALS, stop_process_group
from profile_files import check_profile_exists
from profile_run_state import (get_profile_run_process, is_profile_running, profile_run_lock,
                               set_profile_run_process)
from pydantic import BaseModel

RUN_LAUNCH_FILE_NAME = 'par.launch.py'
RUN_LOG_PATH = os.path.join(tempfile.gettempdir(), 'par_setup_wizard_run.log')
RUN_PROCESS_STOP_TIMEOUT_S = 15.0
RUN_LOG_TAIL_LINE_COUNT = 12

# What the state reports: no run yet or stopped by the user, running, or ended on its own
RUN_PHASE_IDLE = 'idle'
RUN_PHASE_RUNNING = 'running'
RUN_PHASE_ENDED = 'ended'

run_router = APIRouter()
# The run's process is in profile_run_state, which camera_launch_session checks too; these are
# changed under its profile_run_lock as well
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
    global _run_profile_name, _was_run_stopped_by_user
    check_profile_exists(request.profile_name)
    ros2_executable_path = get_ros2_executable_path()
    with profile_run_lock:
        if is_profile_running():
            raise HTTPException(status_code=409, detail='A profile is running already')
        stop_camera_launch(only_preview_id=None)
        launch_command = [ros2_executable_path, 'launch', 'par_framework_core',
                          RUN_LAUNCH_FILE_NAME, f'profile:={request.profile_name}']
        with open(RUN_LOG_PATH, 'w') as run_log_file:
            set_profile_run_process(subprocess.Popen(
                launch_command, stdout=run_log_file, stderr=subprocess.STDOUT,
                start_new_session=True))
        _run_profile_name = request.profile_name
        _was_run_stopped_by_user = False
        return _read_run_state()


@run_router.get('/api/run/state')
def get_run_state() -> RunState:
    """Tell whether a profile runs, and after an end on its own why."""
    with profile_run_lock:
        return _read_run_state()


@run_router.post('/api/run/stop')
def stop_run() -> RunState:
    """Stop the running profile: SIGINT like Ctrl+C, then SIGTERM, then SIGKILL."""
    with profile_run_lock:
        _stop_run_process()
        return _read_run_state()


def _read_run_state() -> RunState:
    """Return the state; hold profile_run_lock."""
    if get_profile_run_process() is None:
        return RunState(phase=RUN_PHASE_IDLE)
    if is_profile_running():
        return RunState(phase=RUN_PHASE_RUNNING, profile_name=_run_profile_name)
    if _was_run_stopped_by_user:
        return RunState(phase=RUN_PHASE_IDLE, profile_name=_run_profile_name)
    return RunState(phase=RUN_PHASE_ENDED, profile_name=_run_profile_name,
                    log_lines=_read_run_log_tail())


def _stop_run_process() -> None:
    """End the launch and the nodes it started; hold profile_run_lock."""
    global _was_run_stopped_by_user
    if not is_profile_running():
        return
    _was_run_stopped_by_user = True
    stop_process_group(get_profile_run_process(), LAUNCH_STOP_SIGNALS, RUN_PROCESS_STOP_TIMEOUT_S)


def _read_run_log_tail() -> list[str]:
    return read_log_lines(RUN_LOG_PATH)[-RUN_LOG_TAIL_LINE_COUNT:]


def _stop_run_at_exit() -> None:
    """Do not leave the framework running when the backend ends."""
    with profile_run_lock:
        _stop_run_process()


atexit.register(_stop_run_at_exit)
