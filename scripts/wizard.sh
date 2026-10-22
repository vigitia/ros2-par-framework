#!/usr/bin/env bash
# Written by Claude Code
#
# Start the setup wizard on the host (no Docker): projector, camera, calibration, nodes, start.
# Sources ROS, the venv and the workspace in bash, so it also works from fish.
#   ./scripts/wizard.sh

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
cd "$REPO_ROOT"

# .env only exists once setup.sh has run; .env.example carries the same default.
env_file=.env
[[ -f "$env_file" ]] || env_file=.env.example
distro="$(sed -n 's/^ROS_DISTRO=//p' "$env_file")"
ros_setup="/opt/ros/${distro}/setup.bash"
[[ -f "$ros_setup" ]] || die "ROS 2 '${distro}' not found at ${ros_setup} -- install ros-${distro}-desktop"
[[ -f .venv/bin/activate && -f install/setup.bash ]] || die "workspace not built -- run: ./scripts/local_build.sh"

# ROS's setup scripts read unset variables, which set -u would abort on.
set +u
source "$ros_setup"
source .venv/bin/activate
source install/setup.bash
set -u
# Every process of the framework needs the same transport, or they don't connect (README.md)
export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA

have ros2 && ros2 pkg prefix par_setup_wizard >/dev/null 2>&1 \
    || die "par_setup_wizard is not built -- run: ./scripts/local_build.sh par_setup_wizard"
exec ros2 run par_setup_wizard par_setup_wizard "$@"
