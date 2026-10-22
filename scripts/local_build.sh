#!/usr/bin/env bash
# Written by Claude Code
#
# Clones every node from config/nodes.list and builds the workspace on the host, as described in
# README.md. Needs ROS 2 installed on the host, in the distro of ROS_DISTRO (scripts/common.sh). Safe to
# re-run.
#   ./scripts/local_build.sh                 # everything
#   ./scripts/local_build.sh logitech_brio   # rebuild one package

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
cd "$REPO_ROOT"

"${REPO_ROOT}/scripts/sync_nodes.sh"

ros_setup="/opt/ros/${ROS_DISTRO}/setup.bash"
[[ -f "$ros_setup" ]] || die "ROS 2 '${ROS_DISTRO}' not found at ${ros_setup} -- install ros-${ROS_DISTRO}-desktop"

# ROS's setup scripts read unset variables, which set -u would abort on.
set +u; source "$ros_setup"; set -u

have rosdep || die "rosdep not found -- sudo apt install python3-rosdep && sudo rosdep init && rosdep update"
have colcon || die "colcon not found -- sudo apt install python3-colcon-common-extensions"

step "Installing apt dependencies (rosdep)"
# The released packages of config/ros_packages.list, as a package.xml rosdep can read. Outside the
# workspace, so colcon never builds it.
ros_packages_dir="$(mktemp -d)"
trap 'rm -rf "$ros_packages_dir"' EXIT
write_ros_packages_manifest "$ros_packages_dir"
# K4A (the Azure Kinect SDK) has no rosdep rule: install it by hand, see README.md
rosdep install --from-paths src packages "$ros_packages_dir" --ignore-src -y --skip-keys K4A

step "Installing PyPI dependencies into .venv"
if [[ ! -d .venv ]]; then
    # --system-site-packages keeps rclpy, cv_bridge and colcon from apt importable.
    python3 -m venv --system-site-packages .venv
    touch .venv/COLCON_IGNORE
fi
# One pip install for all nodes, so conflicting pins fail instead of one node silently overwriting another's.
shopt -s nullglob
pip_args=()
for req in src/*/requirements.txt packages/*/requirements.txt; do pip_args+=(-r "$req"); done
if (( ${#pip_args[@]} > 0 )); then
    .venv/bin/python -m pip install "${pip_args[@]}"
fi

# Built through the venv's python, so node executables run with the venv's packages.
step "Building the workspace"
build_args=(--symlink-install --base-paths src packages)
(( $# > 0 )) && build_args+=(--packages-select "$@")
.venv/bin/python -m colcon build "${build_args[@]}"

ok "workspace built"
info "in each new bash terminal:"
info "  source ${ros_setup} && source .venv/bin/activate && source install/setup.bash"
info "  export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA"
