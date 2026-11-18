# Written by Claude Code
"""
Helpers several API modules of the setup wizard backend share: YAML files, the ros2 command, the
log files of the processes the backend starts and the connected displays.
"""

import re
import shutil

from fastapi import HTTPException
from par_framework_core.connected_displays import ConnectedDisplay, read_connected_displays
import yaml

# Terminal control sequences (colours, cursor moves) that ROS nodes write with emulate_tty, e.g.
# \x1b[31m; removed so the app shows the log lines as plain text
ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
# What a log tail says when the process wrote nothing (yet)
EMPTY_LOG_TEXT = '(no output)'


def read_yaml_file(file_path):
    """Return the content of a YAML file; raises OSError or yaml.YAMLError when unreadable."""
    with open(file_path) as yaml_file:
        return yaml.safe_load(yaml_file)


def get_ros2_executable_path():
    """Return the path of the ros2 command; HTTP 500 naming the fix when it is not found."""
    ros2_executable_path = shutil.which('ros2')
    if ros2_executable_path is None:
        raise HTTPException(status_code=500,
                            detail='ros2 not found: start the backend in a bash with ROS and the '
                                   'workspace sourced')
    return ros2_executable_path


def read_log_lines(log_file_path):
    """Return a process's log file line by line, without colour codes; [] when unreadable."""
    try:
        with open(log_file_path) as log_file:
            raw_log_lines = log_file.read().splitlines()
    except OSError:
        return []
    log_lines = []
    for raw_log_line in raw_log_lines:
        log_lines.append(ANSI_ESCAPE_PATTERN.sub('', raw_log_line))
    return log_lines


def read_log_tail_text(log_file_path, line_count, line_separator='\n'):
    """Return the last line_count lines of a log file as one text; EMPTY_LOG_TEXT without any."""
    log_lines = read_log_lines(log_file_path)
    if not log_lines:
        return EMPTY_LOG_TEXT
    return line_separator.join(log_lines[-line_count:])


def read_connected_displays_or_raise() -> list[ConnectedDisplay]:
    """Return the connected displays in display_id order; HTTP 500 when they cannot be read."""
    try:
        return read_connected_displays()
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
