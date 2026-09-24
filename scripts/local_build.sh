#!/usr/bin/env bash
# Written by Claude Code
#
# Clone every node from config/nodes.list and build the workspace on the host,
# without Docker -- the scripted form of "Testing nodes locally without Docker"
# in README.md. Needs ROS 2 on the host, in the distro set in .env. Safe to re-run.
#   ./scripts/local_build.sh                 # everything
#   ./scripts/local_build.sh logitech_brio   # rebuild one package

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
cd "$REPO_ROOT"

"${REPO_ROOT}/scripts/sync_nodes.sh" --clone-only

# .env only exists once setup.sh has run; .env.example carries the same default.
env_file=.env
[[ -f "$env_file" ]] || env_file=.env.example
distro="$(sed -n 's/^ROS_DISTRO=//p' "$env_file")"
ros_setup="/opt/ros/${distro}/setup.bash"
[[ -f "$ros_setup" ]] || die "ROS 2 '${distro}' not found at ${ros_setup} -- install ros-${distro}-desktop, or use ./setup.sh for Docker"

# ROS's setup scripts read unset variables, which set -u would abort on.
set +u; source "$ros_setup"; set -u

have rosdep || die "rosdep not found -- sudo apt install python3-rosdep && sudo rosdep init && rosdep update"
have colcon || die "colcon not found -- sudo apt install python3-colcon-common-extensions"

step "Installing apt dependencies (rosdep)"
rosdep install --from-paths src packages --ignore-src -y

step "Installing PyPI dependencies into .venv"
if [[ ! -d .venv ]]; then
    # --system-site-packages keeps rclpy, cv_bridge and colcon from apt importable.
    python3 -m venv --system-site-packages .venv
    touch .venv/COLCON_IGNORE
fi
# One pip install for all nodes, like the image, so conflicting pins fail here too.
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
