#!/usr/bin/env bash
#
# One-shot bootstrap for the PAR framework on a fresh computer:
#
#   ./setup.sh
#
# Checks prerequisites, writes .env for this machine, clones every node repo
# listed in config/nodes.list, builds the container image, starts it and builds
# the ROS workspace. Safe to re-run -- it updates instead of redoing.

source "$(dirname "${BASH_SOURCE[0]}")/scripts/common.sh"

SKIP_CLONE=0
NO_CACHE=0
SKIP_BUILD=0

usage() {
    cat <<'EOF'
Usage: ./setup.sh [options]

  --skip-clone      leave src/ as it is (no fetch, no clone)
  --no-cache        rebuild the container image from scratch
  --skip-build      set up and start the container, but do not colcon build
  -h, --help        show this help
EOF
}

while (( $# > 0 )); do
    case "$1" in
        --skip-clone) SKIP_CLONE=1 ;;
        --no-cache)   NO_CACHE=1 ;;
        --skip-build) SKIP_BUILD=1 ;;
        -h|--help)    usage; exit 0 ;;
        *)            usage; die "unknown option: $1" ;;
    esac
    shift
done

printf '%s%sPAR framework setup%s  (%s)\n' "$C_BOLD" "$C_BLUE" "$C_RESET" "$REPO_ROOT"

# 1 -- can this machine do it at all?
bash "${REPO_ROOT}/scripts/preflight.sh"

# 2 -- machine-local configuration.
step "Configuring this machine"
ENV_FILE="${REPO_ROOT}/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "${REPO_ROOT}/.env.example" "$ENV_FILE"
    ok "created .env from .env.example"
else
    ok ".env already exists -- keeping your settings"
fi

# X11 forwarding needs a real authority file: if the variable is unset, docker
# would happily create a *directory* at the mount path and the GUI would fail
# with a confusing error much later.
xauth_file="${XAUTHORITY:-$HOME/.Xauthority}"
[[ -f "$xauth_file" ]] || { touch "$xauth_file"; info "created empty $xauth_file"; }

set_env_var() {
    local key="$1" value="$2"
    if grep -q "^${key}=" "$ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}
set_env_var DISPLAY "${DISPLAY}"
set_env_var XAUTHORITY "${xauth_file}"
ok "DISPLAY=${DISPLAY}, XAUTHORITY=${xauth_file}"

# The container runs as root on the host's X server, which rejects it by default.
if have xhost; then
    xhost +local:root >/dev/null 2>&1 && ok "granted local root access to your X server (xhost +local:root)"
    hint "this resets on logout; setup.sh re-applies it, or run it yourself"
else
    warn "xhost not found -- if GUI windows fail to open, install x11-xserver-utils"
fi

# 3 -- node repositories.
if (( SKIP_CLONE )); then
    step "Skipping node sync (--skip-clone)"
else
    bash "${REPO_ROOT}/scripts/sync_nodes.sh"
fi
[[ -d "${REPO_ROOT}/docker/deps" ]] || die "docker/deps/ is missing -- run without --skip-clone once"

# 4 -- container image. Slow the first time, cached afterwards unless a node
# changed its declared dependencies.
step "Building the container image"
build_args=()
(( NO_CACHE )) && build_args+=(--no-cache)
compose build "${build_args[@]}" "$SERVICE"
ok "image built"

# 5 -- start it. Recreate so volume and env changes take effect.
step "Starting the container"
compose up -d --force-recreate "$SERVICE"
ok "container '$(container_name)' is running"

# 6 -- workspace.
if (( SKIP_BUILD )); then
    step "Skipping colcon build (--skip-build)"
else
    bash "${REPO_ROOT}/scripts/build_workspace.sh"
fi

cat <<EOF

$(printf '%s%sSetup complete.%s' "$C_BOLD" "$C_GREEN" "$C_RESET")

  ./scripts/shell.sh                 shell inside the container
  ./scripts/launch.sh calibration    mark the projection surface (do this first)
  ./scripts/launch.sh                run the framework
  ./scripts/build_workspace.sh       rebuild after editing node code

  Node source is in src/ -- each directory is its own git repo, edit it there.
  Per-setup values (camera id, projector display) live in
  par-framework-core/config/par_setup.yaml.

EOF
