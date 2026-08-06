#!/usr/bin/env bash
# colcon build inside the running container. Pass package names to build a subset:
#   ./scripts/build_workspace.sh                 # everything
#   ./scripts/build_workspace.sh logitech_brio   # one package

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

step "Building the ROS workspace"

args=(--symlink-install)
if (( $# > 0 )); then
    args+=(--packages-select "$@")
    info "packages: $*"
fi

in_container "cd \$ROS_WS && colcon build ${args[*]}"
ok "workspace built"
