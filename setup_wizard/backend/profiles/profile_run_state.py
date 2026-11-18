# Written by Claude Code
"""
Whether this backend runs a profile as the framework (run_api.py), for the modules that start a
camera launch (camera_launch_session.py) or must not run beside one (node_settings_api.py),
without importing run_api.

A camera launch next to the running framework would fight over the same device, so a start of one
refuses while the other runs. Both starts hold profile_run_lock, so neither can slip in between the
other's check and its start. Lock order: profile_run_lock before any lock of
camera_launch_session.
"""

import threading

profile_run_lock = threading.Lock()
# The launch process of the running profile; None before the first run. Changed under
# profile_run_lock
_profile_run_process = None


def get_profile_run_process():
    """Return the launch process of the latest run, None before the first. Hold the lock."""
    return _profile_run_process


def set_profile_run_process(profile_run_process):
    """Store the launch process of a run that just started. Hold the lock."""
    global _profile_run_process
    _profile_run_process = profile_run_process


def is_profile_running():
    """Tell whether the launch of the latest run still runs. Hold the lock."""
    if _profile_run_process is None:
        return False
    return _profile_run_process.poll() is None
