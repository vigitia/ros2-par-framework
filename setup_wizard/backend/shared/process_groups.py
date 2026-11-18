# Written by Claude Code
"""
Stop a child process started in its own process group (subprocess.Popen(start_new_session=True)).

Launches and helper windows start further processes (ros2 launch starts the nodes), so they are
stopped as a group: each signal goes to the whole group, and the next, harder signal follows only
when the group's leader has not ended within the timeout.
"""

import os
import signal
import subprocess

# Like Ctrl+C first, so ros2 launch shuts its nodes down cleanly, then ever harder
LAUNCH_STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGKILL)


def stop_process_group(process: subprocess.Popen, stop_signals: tuple[int, ...],
                       timeout_per_signal_s: float) -> None:
    """Send stop_signals to the process's group in turn until the process has ended."""
    if process.poll() is not None:
        return
    for stop_signal in stop_signals:
        try:
            os.killpg(process.pid, stop_signal)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=timeout_per_signal_s)
            return
        except subprocess.TimeoutExpired:
            continue
