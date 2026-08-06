#!/usr/bin/env bash
# Sources the ROS underlay and, if it has been built, the workspace overlay --
# so `docker exec <container> ros2 topic list` works without a login shell.
set -e

source "/opt/ros/${ROS_DISTRO}/setup.bash"
if [ -f "${ROS_WS}/install/local_setup.bash" ]; then
    source "${ROS_WS}/install/local_setup.bash"
fi

exec "$@"
