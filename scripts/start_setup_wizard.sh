#!/usr/bin/env bash
# Written by Claude Code
#
# Starts the setup wizard on this machine, also on a fresh clone with nothing built yet:
#   1. checks that ROS 2 is installed and that GitHub accepts this machine's SSH key (for git@ URLs)
#   2. builds the workspace with local_build.sh when the backend's packages are not built yet
#   3. builds the wizard app when its bundle is missing (installs Flutter's Linux build tools)
#   4. adds the wizard to the application menu (a .desktop file in ~/.local/share/applications that runs
#      this script and gives the app's window its icon)
#   5. starts the backend unless one already answers, then the app; closing the app stops the
#      backend this script started
#   ./scripts/start_setup_wizard.sh

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
cd "$REPO_ROOT"

SETUP_WIZARD_APP_FOLDER_PATH="${REPO_ROOT}/setup_wizard/app"
SETUP_WIZARD_APP_EXECUTABLE_PATH="${SETUP_WIZARD_APP_FOLDER_PATH}/build/linux/x64/release/bundle/par_setup_wizard"
SETUP_WIZARD_BACKEND_SCRIPT_PATH="${REPO_ROOT}/setup_wizard/backend/setup_wizard_backend.py"
# Host and port as in setup_wizard_backend.py
SETUP_WIZARD_BACKEND_STATUS_URL="http://127.0.0.1:8800/api/status"
SETUP_WIZARD_BACKEND_LOG_PATH="${REPO_ROOT}/log/setup_wizard_backend.log"
SETUP_WIZARD_BACKEND_START_TIMEOUT_S=60
# How long the backend gets per stop signal before the next one
SETUP_WIZARD_BACKEND_STOP_TIMEOUT_S=10
# apt packages Flutter needs to build a Linux app (flutter doctor, "Linux toolchain")
FLUTTER_LINUX_TOOLCHAIN_APT_PACKAGE_NAMES=(clang cmake ninja-build pkg-config libgtk-3-dev)

# The app's ID (APPLICATION_ID in setup_wizard/app/linux/CMakeLists.txt). Wayland desktops such as GNOME find a
# window's icon only through a .desktop file of that name, not from the window itself.
SETUP_WIZARD_APPLICATION_ID="com.github.vigitia.par_setup_wizard"
SETUP_WIZARD_APP_ICON_PATH="${SETUP_WIZARD_APP_FOLDER_PATH}/assets/app_icon.svg"
# The user's application folder (XDG base directory spec): $XDG_DATA_HOME, by default ~/.local/share
SETUP_WIZARD_DESKTOP_ENTRY_PATH="${XDG_DATA_HOME:-${HOME}/.local/share}/applications/${SETUP_WIZARD_APPLICATION_ID}.desktop"

ros_setup_script_path="/opt/ros/${ROS_DISTRO}/setup.bash"

# Co-authored by Claude Code
# True when the backend answers its status request. Uses Python instead of curl, which a fresh
# Ubuntu does not have.
is_setup_wizard_backend_answering() {
    python3 -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=1)" \
        "$SETUP_WIZARD_BACKEND_STATUS_URL" >/dev/null 2>&1
}

# Co-authored by Claude Code
# Warn when a node list has GitHub SSH URLs but GitHub does not accept this machine's key: cloning
# would fail later. `ssh -T git@github.com` exits with 1 even when it works, so its greeting is
# checked instead.
check_github_ssh_access() {
    local list_paths=("$REQUIRED_REPOS_LIST_PATH" "${REPO_ROOT}/config/catalog_repos.list")
    if [[ -f "$INSTALLED_REPOS_LIST_PATH" ]]; then
        list_paths+=("$INSTALLED_REPOS_LIST_PATH")
    fi
    if ! grep -q '^[^#]*git@github\.com:' "${list_paths[@]}"; then
        return
    fi

    local ssh_greeting_text
    # BatchMode: fail instead of asking for a password or a host key confirmation
    ssh_greeting_text="$(ssh -T -o BatchMode=yes -o ConnectTimeout=10 git@github.com 2>&1 || true)"
    if [[ "$ssh_greeting_text" == *"successfully authenticated"* ]]; then
        ok "GitHub accepts this machine's SSH key"
        return
    fi
    warn "GitHub does not accept an SSH key of this machine, so cloning git@github.com repositories fails"
    hint "ssh says: ${ssh_greeting_text}"
    hint "add a key: ssh-keygen -t ed25519, then paste ~/.ssh/id_ed25519.pub at https://github.com/settings/keys"
    hint "an unknown host key: run ssh -T git@github.com once and answer yes"
}

# Co-authored by Claude Code
# True when everything the backend imports is built: par_framework_core and par_geometry in
# install/, fastapi in .venv.
is_setup_wizard_backend_built() {
    [[ -d install/par_framework_core && -d install/par_geometry && -x .venv/bin/python ]] \
        && .venv/bin/python -c 'import fastapi, uvicorn' >/dev/null 2>&1
}

# Co-authored by Claude Code
# Build the wizard app's release bundle, after installing Flutter's Linux build tools when missing.
build_setup_wizard_app() {
    if ! command_exists flutter; then
        die "the wizard app is not built and Flutter is not installed -- install Flutter: https://docs.flutter.dev/get-started/install/linux (then flutter doctor)"
    fi

    local missing_package_names=() package_name
    for package_name in "${FLUTTER_LINUX_TOOLCHAIN_APT_PACKAGE_NAMES[@]}"; do
        if ! dpkg -s "$package_name" >/dev/null 2>&1; then
            missing_package_names+=("$package_name")
        fi
    done
    if (( ${#missing_package_names[@]} > 0 )); then
        info "installing Flutter's Linux build tools: ${missing_package_names[*]}"
        sudo apt-get install -y "${missing_package_names[@]}"
    fi

    (cd "$SETUP_WIZARD_APP_FOLDER_PATH" && flutter build linux --release)
}

# Co-authored by Claude Code
# Stop the backend this script started. SIGINT lets uvicorn shut down cleanly, so the backend stops
# what it started (camera previews, runs); SIGTERM is handled the same way. Now and then the backend
# ignores both (cause not found yet, see claude_usage_documentation.md); then SIGKILL, so it does not
# hold the port and block the next start, with a warning that its launches may still run.
#   stop_setup_wizard_backend <pid>
stop_setup_wizard_backend() {
    local backend_pid="$1" signal_name waited_s
    for signal_name in INT TERM; do
        kill -"$signal_name" "$backend_pid" 2>/dev/null || return 0
        for (( waited_s = 0; waited_s < SETUP_WIZARD_BACKEND_STOP_TIMEOUT_S; waited_s++ )); do
            if ! kill -0 "$backend_pid" 2>/dev/null; then
                return 0
            fi
            sleep 1
        done
    done
    kill -KILL "$backend_pid" 2>/dev/null || return 0
    warn "the setup wizard backend ignored SIGINT and SIGTERM and was killed"
    hint "a camera preview or run it started may still be running: pgrep -af 'ros2 launch'"
}

# Co-authored by Claude Code
# Write the .desktop file that puts the wizard into the application menu and gives the app's window its icon,
# when it is missing or names other paths (e.g. after the repository moved). It runs this script, so the menu
# starts the backend and the app the same way as a terminal does. No terminal window: the backend logs to
# SETUP_WIZARD_BACKEND_LOG_PATH, and the entry only exists after this script ran once, so the first-start
# builds (which may ask for a sudo password) have already happened in a terminal.
# Exec is quoted because the desktop entry spec splits unquoted paths at spaces.
write_setup_wizard_desktop_entry() {
    local desktop_entry_text
    desktop_entry_text="[Desktop Entry]
Type=Application
Name=PAR setup wizard
Comment=Set up the projected augmented reality framework (starts the backend and the app)
Exec=\"${REPO_ROOT}/scripts/start_setup_wizard.sh\"
Icon=${SETUP_WIZARD_APP_ICON_PATH}
StartupWMClass=${SETUP_WIZARD_APPLICATION_ID}
Terminal=false
Categories=Development;"
    if [[ -f "$SETUP_WIZARD_DESKTOP_ENTRY_PATH" && "$(cat "$SETUP_WIZARD_DESKTOP_ENTRY_PATH")" == "$desktop_entry_text" ]]; then
        return
    fi
    mkdir -p "$(dirname "$SETUP_WIZARD_DESKTOP_ENTRY_PATH")"
    printf '%s\n' "$desktop_entry_text" > "$SETUP_WIZARD_DESKTOP_ENTRY_PATH"
    ok "added to the application menu (${SETUP_WIZARD_DESKTOP_ENTRY_PATH})"
}

# 1. Prerequisites
step "Checking prerequisites"
if [[ ! -f "$ros_setup_script_path" ]]; then
    die "ROS 2 '${ROS_DISTRO}' not found at ${ros_setup_script_path} -- install it with the guide at https://docs.ros.org (ros-${ROS_DISTRO}-desktop), or set ROS_DISTRO to the installed one"
fi
ok "ROS 2 ${ROS_DISTRO}"
check_github_ssh_access

# 2. Workspace
if is_setup_wizard_backend_built; then
    ok "workspace built"
else
    step "Building the workspace (first start)"
    "${REPO_ROOT}/scripts/local_build.sh"
fi

# 3. App
if [[ -x "$SETUP_WIZARD_APP_EXECUTABLE_PATH" ]]; then
    ok "wizard app built"
else
    step "Building the wizard app (first start)"
    build_setup_wizard_app
fi

# 4. Application menu entry
write_setup_wizard_desktop_entry

# 5. Backend and app
step "Starting the setup wizard"
setup_wizard_backend_pid=""
if is_setup_wizard_backend_answering; then
    ok "a setup wizard backend already runs; using it"
else
    mkdir -p "$(dirname "$SETUP_WIZARD_BACKEND_LOG_PATH")"
    # ROS's setup scripts read unset variables, so the subshell switches off -u while sourcing them.
    # exec replaces the subshell with Python, so the PID below is the backend's own.
    (
        set +u
        source "$ros_setup_script_path"
        source "${REPO_ROOT}/install/setup.bash"
        exec .venv/bin/python "$SETUP_WIZARD_BACKEND_SCRIPT_PATH"
    ) > "$SETUP_WIZARD_BACKEND_LOG_PATH" 2>&1 &
    setup_wizard_backend_pid=$!
    # Stop the backend with the script, also after Ctrl+C or an error
    trap 'stop_setup_wizard_backend "$setup_wizard_backend_pid"' EXIT

    waited_s=0
    until is_setup_wizard_backend_answering; do
        if ! kill -0 "$setup_wizard_backend_pid" 2>/dev/null; then
            tail -n 20 "$SETUP_WIZARD_BACKEND_LOG_PATH" >&2
            die "the setup wizard backend stopped while starting -- see ${SETUP_WIZARD_BACKEND_LOG_PATH}"
        fi
        if (( waited_s >= SETUP_WIZARD_BACKEND_START_TIMEOUT_S )); then
            die "the setup wizard backend did not answer within ${SETUP_WIZARD_BACKEND_START_TIMEOUT_S} s -- see ${SETUP_WIZARD_BACKEND_LOG_PATH}"
        fi
        sleep 1
        waited_s=$((waited_s + 1))
    done
    ok "backend runs (log: ${SETUP_WIZARD_BACKEND_LOG_PATH})"
fi

# Not exec: the script has to stay to stop the backend when the app closes
"$SETUP_WIZARD_APP_EXECUTABLE_PATH"
