#!/usr/bin/env bash
# Written by Claude Code
#
# Builds the framework on the host, as described in README.md. Safe to re-run; that is also how node
# updates are pulled. Needs ROS 2 installed on the host, in the distro of ROS_DISTRO (scripts/common.sh).
#   ./scripts/local_build.sh                 # everything
#   ./scripts/local_build.sh logitech_brio   # rebuild one package
#
# Steps:
#   1. clone or update the node repositories of config/nodes.list into src/ (scripts/sync_nodes.sh)
#   2. install their apt dependencies with rosdep
#   3. install their PyPI dependencies and the setup wizard backend's into .venv
#   4. build the workspace with colcon
#   5. build the node repositories' Rust programs with cargo (full builds only)

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
cd "$REPO_ROOT"

# 1. Node repositories
"${REPO_ROOT}/scripts/sync_nodes.sh"

ros_setup="/opt/ros/${ROS_DISTRO}/setup.bash"
if [[ ! -f "$ros_setup" ]]; then
    die "ROS 2 '${ROS_DISTRO}' not found at ${ros_setup} -- install ros-${ROS_DISTRO}-desktop"
fi

# ROS's setup script reads variables that may be unset, which set -u would stop at. So -u is switched
# off while it runs.
set +u
source "$ros_setup"
set -u

if ! command_exists rosdep; then
    die "rosdep not found -- sudo apt install python3-rosdep && sudo rosdep init && rosdep update"
fi
if ! command_exists colcon; then
    die "colcon not found -- sudo apt install python3-colcon-common-extensions"
fi

# 2. apt dependencies
step "Installing apt dependencies (rosdep)"
# The released packages of config/ros_packages.list, as a package.xml rosdep can read. It goes into a
# temporary directory outside the workspace, so colcon never builds it; `trap ... EXIT` deletes the
# directory when the script ends, also after an error.
ros_packages_dir="$(mktemp -d)"
trap 'rm -rf "$ros_packages_dir"' EXIT
write_ros_packages_manifest "$ros_packages_dir"
# --ignore-src: packages that are in the workspace are built, not installed.
# --skip-keys K4A: the Azure Kinect SDK has no rosdep rule; install it by hand, see README.md.
rosdep install --from-paths src packages "$ros_packages_dir" --ignore-src -y --skip-keys K4A

# 3. PyPI dependencies
step "Installing PyPI dependencies into .venv"
if [[ ! -d .venv ]]; then
    # --system-site-packages keeps rclpy, cv_bridge and colcon from apt importable.
    python3 -m venv --system-site-packages .venv
    # Tells colcon not to look for packages inside the venv
    touch .venv/COLCON_IGNORE
fi

# One pip install for all nodes, so conflicting pins fail instead of one node silently overwriting
# another's. nullglob makes a pattern without matches expand to nothing instead of staying as literal text.
shopt -s nullglob
pip_args=()
for requirements_file in src/*/requirements.txt packages/*/requirements.txt setup_wizard/backend/requirements.txt; do
    pip_args+=(-r "$requirements_file")
done
if (( ${#pip_args[@]} > 0 )); then
    .venv/bin/python -m pip install "${pip_args[@]}"
fi

# 4. Build. Through the venv's python, so node executables run with the venv's packages.
step "Building the workspace"
build_args=(--symlink-install --base-paths src packages)
if (( $# > 0 )); then
    build_args+=(--packages-select "$@")
fi
.venv/bin/python -m colcon build "${build_args[@]}"

# 5. Rust programs, e.g. the rendering manager (a Wayland compositor): colcon builds only their ROS
# packages, cargo the programs themselves, in release mode as the launch files start them. Only in a
# full build, so rebuilding one package stays quick; cargo skips what has not changed.
if (( $# == 0 )); then
    for cargo_manifest_path in src/*/Cargo.toml; do
        if [[ ! -f "$cargo_manifest_path" ]]; then
            continue
        fi
        if ! command_exists cargo; then
            die "cargo not found, needed for ${cargo_manifest_path} -- sudo apt install cargo"
        fi
        step "Building ${cargo_manifest_path%/Cargo.toml} with cargo"
        cargo build --release --manifest-path "$cargo_manifest_path"
    done
fi

ok "workspace built"
info "in each new bash terminal:"
info "  source ${ros_setup} && source .venv/bin/activate && source install/setup.bash"
info "  export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA"
