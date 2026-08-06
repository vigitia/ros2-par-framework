#!/usr/bin/env bash
# Launch a framework configuration in the running container.
#
#   ./scripts/launch.sh              # par_framework.launch.py (camera + pipeline)
#   ./scripts/launch.sh calibration  # calibration.launch.py (surface selection)
#
# Anything after the name is passed through to ros2 launch as arguments, e.g.
#   ./scripts/launch.sh calibration display_id:=1

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

target="${1:-par_framework}"
shift || true

docker_exec /usr/local/bin/entrypoint.sh \
    ros2 launch par_framework_bringup "${target}.launch.py" "$@"
