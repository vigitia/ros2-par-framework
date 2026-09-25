#!/usr/bin/env bash
# colcon build inside the running container. Pass package names to build a subset:
#   ./scripts/build_workspace.sh                 # everything
#   ./scripts/build_workspace.sh logitech_brio   # one package

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

step "Building the ROS workspace"

# The image has no Azure Kinect SDK (see docker/Dockerfile), so its driver cannot build here and
# would stop colcon; the Kinect is used with ./scripts/local_build.sh on the host.
args=(--symlink-install --packages-skip azure_kinect_ros_driver)
if (( $# > 0 )); then
    args+=(--packages-select "$@")
    info "packages: $*"
fi

in_container "cd \$ROS_WS && colcon build ${args[*]}"
ok "workspace built"
