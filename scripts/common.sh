#!/usr/bin/env bash
# Shared helpers for the scripts in this directory. Not executable on its own.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_ROOT

if [[ -t 1 ]]; then
    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'
else
    C_RESET=''; C_BOLD=''; C_DIM=''; C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''
fi

step() { printf '\n%s==>%s %s%s%s\n' "$C_BLUE" "$C_RESET" "$C_BOLD" "$*" "$C_RESET"; }
info() { printf '    %s\n' "$*"; }
ok()   { printf '    %s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '    %s!%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
hint() { printf '      %s%s%s\n' "$C_DIM" "$*" "$C_RESET" >&2; }
die()  { printf '\n%serror:%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

# Read config/nodes.list and emit "dir<TAB>url<TAB>branch" for each entry,
# with comments and blank lines stripped and a missing branch normalised to "-".
read_nodes_list() {
    local list="${REPO_ROOT}/config/nodes.list"
    [[ -f "$list" ]] || die "missing $list"
    awk '
        { sub(/#.*/, "") }
        NF == 0 { next }
        NF < 2  { printf("nodes.list line %d: expected \"<dir> <url> [branch]\"\n", NR) > "/dev/stderr"; exit 1 }
        { printf "%s\t%s\t%s\n", $1, $2, (NF >= 3 ? $3 : "-") }
    ' "$list"
}

# Co-authored by Claude Code
# Read config/ros_packages.list and emit one rosdep key per line, with comments and
# blank lines stripped. A key ends up in a generated package.xml, so anything that
# is not a plain key fails here instead of producing broken XML.
read_ros_packages_list() {
    local list="${REPO_ROOT}/config/ros_packages.list"
    [[ -f "$list" ]] || die "missing $list"
    awk '
        { sub(/#.*/, "") }
        NF == 0 { next }
        NF > 1 || $1 !~ /^[A-Za-z0-9_.-]+$/ {
            printf("ros_packages.list line %d: expected one rosdep key\n", NR) > "/dev/stderr"; exit 1
        }
        { print $1 }
    ' "$list"
}

# Co-authored by Claude Code
# Write <dir>/par_ros_packages/package.xml, a package that only depends on every key
# of config/ros_packages.list, so that `rosdep install --from-paths <dir>` installs
# them the same way it installs the nodes' dependencies.
write_ros_packages_manifest() {
    local keys key
    keys="$(read_ros_packages_list)" || die "fix config/ros_packages.list"
    mkdir -p "$1/par_ros_packages"
    {
        echo '<?xml version="1.0"?>'
        echo '<!-- Generated from config/ros_packages.list by scripts/common.sh -->'
        echo '<package format="3">'
        echo '  <name>par_ros_packages</name>'
        echo '  <version>0.0.0</version>'
        echo '  <description>Released packages listed in config/ros_packages.list.</description>'
        echo '  <maintainer email="none@example.com">generated</maintainer>'
        # Required by rosdep's manifest parser; the same as par_framework_core's
        echo '  <license>MIT</license>'
        for key in $keys; do echo "  <exec_depend>${key}</exec_depend>"; done
        echo '</package>'
    } > "$1/par_ros_packages/package.xml"
}

# Name of the compose service everything runs in.
SERVICE=ros2

compose() { docker compose --project-directory "$REPO_ROOT" "$@"; }

container_name() {
    # shellcheck disable=SC1091
    [[ -f "${REPO_ROOT}/.env" ]] && source "${REPO_ROOT}/.env"
    echo "${CONTAINER_NAME:-par_framework}"
}

require_container_running() {
    local name; name="$(container_name)"
    if [[ -z "$(docker ps --quiet --filter "name=^${name}$")" ]]; then
        die "container '${name}' is not running -- start it with: docker compose up -d"
    fi
}

# `docker exec -t` requires a real terminal and refuses outright without one, so
# hardcoding -it breaks every non-interactive caller: a background run, CI, or
# simply `./setup.sh > log`. Allocate a TTY only when there actually is one.
docker_exec() {
    require_container_running
    local flags=()
    if [[ -t 0 && -t 1 ]]; then
        flags=(-i -t)
    fi
    docker exec "${flags[@]}" "$(container_name)" "$@"
}

# Run a command inside the container. The entrypoint sources the ROS underlay
# and the workspace overlay, so commands see the same environment a shell does.
in_container() {
    docker_exec /usr/local/bin/entrypoint.sh bash -c "$*"
}
