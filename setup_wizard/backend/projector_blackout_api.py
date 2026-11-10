# Written by Claude Code
"""
Projector blackout API of the setup wizard backend: a black fullscreen window on the projector.

While a calibration step that does not need the projector runs (lens calibration, camera pose),
the projector shows black, so its light does not disturb the camera image (e.g. glare on the
checkerboard). The window is projector_blackout_window.py in its own process, on the display the
app names (the framework's display_id). A display that is not connected (projector unplugged) is
reported, not an error.

The app keeps the blackout by asking again every few seconds; a watchdog ends the window once
nobody asked for a while, however the app left the step (screen closed, app quit or crashed).
Every request names its holder (one per screen), so a stop arriving after another screen took
over the blackout does not end it.
"""

from contextlib import asynccontextmanager
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time

import displays_api
from fastapi import APIRouter
from process_groups import stop_process_group
from pydantic import BaseModel, Field

BLACKOUT_WINDOW_SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           'projector_blackout_window.py')
# The window's output, read back when it ends by itself (e.g. SDL cannot open the display)
BLACKOUT_WINDOW_LOG_PATH = os.path.join(tempfile.gettempdir(),
                                        'par_setup_wizard_projector_blackout.log')
BLACKOUT_WINDOW_LOG_TAIL_LINE_COUNT = 4
# The app asks every 2 s; after this long without a request nobody holds the blackout
BLACKOUT_UNHELD_TIMEOUT_S = 6.0
WATCHDOG_CHECK_INTERVAL_S = 1.0
BLACKOUT_WINDOW_STOP_TIMEOUT_S = 5.0
WATCHDOG_THREAD_JOIN_TIMEOUT_S = 5.0


class ProjectorBlackoutKeepRequest(BaseModel):
    # The framework's display_id of the projector (SDL's display index)
    display_id: int = Field(ge=0)
    # Chosen by the screen that holds the blackout, the same in all its requests
    holder_id: str = Field(min_length=1, max_length=100)


class ProjectorBlackoutStopRequest(BaseModel):
    # Stop only while this holder holds the blackout
    holder_id: str = Field(min_length=1, max_length=100)


class ProjectorBlackoutState(BaseModel):
    is_shown: bool
    # Why it is not shown, e.g. the display is not connected; empty while shown
    reason_text: str = ''


class _ProjectorBlackoutSession:
    """The black window's process and who holds it, changed under session_lock."""

    def __init__(self):
        self.session_lock = threading.Lock()
        self.window_process = None
        self.display_id = None
        self.holder_id = None
        # time.monotonic() of the latest keep request, read by the watchdog
        self.last_keep_monotonic_s = 0.0


_blackout_session = _ProjectorBlackoutSession()


@asynccontextmanager
async def _run_blackout_watchdog(app):
    """End the black window when nobody holds it any longer, and when the backend stops."""
    watchdog_stop_event = threading.Event()
    watchdog_thread = threading.Thread(target=_stop_unheld_blackout,
                                       args=(watchdog_stop_event,), daemon=True)
    watchdog_thread.start()
    try:
        yield
    finally:
        watchdog_stop_event.set()
        watchdog_thread.join(timeout=WATCHDOG_THREAD_JOIN_TIMEOUT_S)
        with _blackout_session.session_lock:
            _stop_blackout_window()


projector_blackout_router = APIRouter(lifespan=_run_blackout_watchdog)


@projector_blackout_router.post('/api/projector-blackout/keep')
def keep_projector_blackout(request: ProjectorBlackoutKeepRequest) -> ProjectorBlackoutState:
    """Show black on the display, or keep showing it; ask again every few seconds."""
    with _blackout_session.session_lock:
        _blackout_session.holder_id = request.holder_id
        _blackout_session.last_keep_monotonic_s = time.monotonic()
        window_process = _blackout_session.window_process
        if window_process is not None and _blackout_session.display_id == request.display_id:
            if window_process.poll() is None:
                return ProjectorBlackoutState(is_shown=True)
            # Ended by itself: report why, and do not open it again and again
            return ProjectorBlackoutState(is_shown=False,
                                          reason_text=f'The black window ended: '
                                                      f'{_read_window_log_tail()}')
        _stop_blackout_window()
        if not _is_display_connected(request.display_id):
            return ProjectorBlackoutState(is_shown=False,
                                          reason_text=f'Display {request.display_id} is not '
                                                      f'connected')
        with open(BLACKOUT_WINDOW_LOG_PATH, 'w') as window_log_file:
            _blackout_session.window_process = subprocess.Popen(
                [sys.executable, BLACKOUT_WINDOW_SCRIPT_PATH, str(request.display_id)],
                stdout=window_log_file, stderr=subprocess.STDOUT, start_new_session=True)
        _blackout_session.display_id = request.display_id
        return ProjectorBlackoutState(is_shown=True)


@projector_blackout_router.post('/api/projector-blackout/stop')
def stop_projector_blackout(request: ProjectorBlackoutStopRequest) -> None:
    """End the black window, unless another holder has taken it over meanwhile."""
    with _blackout_session.session_lock:
        if request.holder_id != _blackout_session.holder_id:
            return
        _stop_blackout_window()


def stop_projector_blackout_for_projection():
    """End the black window whoever holds it, e.g. before a calibration that projects."""
    with _blackout_session.session_lock:
        _stop_blackout_window()


def _stop_unheld_blackout(watchdog_stop_event):
    # Checks until the backend shuts down; wait() returns True as soon as the event is set
    while not watchdog_stop_event.wait(timeout=WATCHDOG_CHECK_INTERVAL_S):
        with _blackout_session.session_lock:
            if _blackout_session.window_process is None:
                continue
            unheld_duration_s = time.monotonic() - _blackout_session.last_keep_monotonic_s
            if unheld_duration_s > BLACKOUT_UNHELD_TIMEOUT_S:
                _stop_blackout_window()


def _stop_blackout_window():
    """End the window's process: SIGTERM, then SIGKILL. Hold the session lock."""
    window_process = _blackout_session.window_process
    _blackout_session.window_process = None
    _blackout_session.display_id = None
    if window_process is None:
        return
    stop_process_group(window_process, (signal.SIGTERM, signal.SIGKILL),
                       BLACKOUT_WINDOW_STOP_TIMEOUT_S)


def _is_display_connected(display_id):
    for connected_display in displays_api.get_display_list().displays:
        if connected_display.display_id == display_id:
            return True
    return False


def _read_window_log_tail():
    try:
        with open(BLACKOUT_WINDOW_LOG_PATH) as window_log_file:
            log_lines = window_log_file.read().splitlines()
    except OSError:
        return '(no output)'
    if not log_lines:
        return '(no output)'
    return ' '.join(log_lines[-BLACKOUT_WINDOW_LOG_TAIL_LINE_COUNT:])
