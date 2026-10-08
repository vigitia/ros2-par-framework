#!/usr/bin/env bash
# Launch a framework configuration in the running container.
#
#   ./scripts/launch.sh              # par.launch.py (camera + nodes from par_setup.yaml's par_launch)
#   ./scripts/launch.sh calibration  # calibration.launch.py (surface selection)
#
# Anything after the name is passed through to ros2 launch as arguments, e.g.
#   ./scripts/launch.sh par camera:=kinect rviz:=true
#   ./scripts/launch.sh calibration display_id:=1
# (Default changed from the retired par_framework.launch.py with the help of Claude Code.)

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

target="${1:-par}"
shift || true

docker_exec /usr/local/bin/entrypoint.sh \
    ros2 launch par_framework_core "${target}.launch.py" "$@"
