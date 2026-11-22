#!/usr/bin/env bash
# Written by Claude Code
#
# Builds the framework on the host, as described in README.md. Safe to re-run; that is also how node
# updates are pulled. Needs ROS 2 installed on the host, in the distro of ROS_DISTRO (scripts/common.sh);
# the build tools (rosdep, colcon, Python's venv) are installed when missing.
#   ./scripts/local_build.sh                     # everything
#   ./scripts/local_build.sh logitech_brio       # rebuild one package
#   ./scripts/local_build.sh --non-interactive   # never asks for a password, e.g. run by the setup wizard
#
# Steps:
#   1. clone or update the node repositories of config/required_repos.list and config/installed_repos.list into src/
#      (scripts/sync_nodes.sh)
#   2. install missing build tools and the nodes' apt dependencies (rosdep)
#   3. install their PyPI dependencies and the setup wizard backend's into .venv
#   4. build the workspace with colcon
#
# --non-interactive: whatever needs root (apt packages, `rosdep init`) is not run but printed as one line
# starting with "$SUDO_COMMAND_LINE_PREFIX", and the script exits with $EXIT_CODE_NEEDS_SUDO. Run that
# command in a terminal, then run the script again. The setup wizard's backend reads that line, so
# both values must stay as they are in setup_wizard/backend/.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
cd "$REPO_ROOT"

SUDO_COMMAND_LINE_PREFIX="needs sudo: "
EXIT_CODE_NEEDS_SUDO=3

# rosdep's own list of where its rules come from; `sudo rosdep init` creates it
ROSDEP_SOURCES_FOLDER_PATH="/etc/ros/rosdep/sources.list.d"
# rosdep's downloaded rules (a folder); `rosdep update` creates them
ROSDEP_CACHE_PATH="${HOME}/.ros/rosdep/sources.cache"

is_non_interactive=false
selected_package_names=()
for argument in "$@"; do
    case "$argument" in
        --non-interactive)
            is_non_interactive=true
            ;;
        -*)
            die "unknown option ${argument} -- usage: ./scripts/local_build.sh [--non-interactive] [package ...]"
            ;;
        *)
            selected_package_names+=("$argument")
            ;;
    esac
done

# What step 2 found missing: apt packages, merged into one install command, and other commands that
# need root (e.g. `sudo rosdep init`), run or printed in this order.
missing_apt_package_names=()
other_sudo_command_lines=()

# Co-authored by Claude Code
# Add the apt packages of build tools that are not installed to missing_apt_package_names, and
# `sudo rosdep init` to other_sudo_command_lines when rosdep has never been set up.
collect_missing_build_tools() {
    if ! command_exists git; then
        missing_apt_package_names+=(git)
    fi
    if ! command_exists rosdep; then
        missing_apt_package_names+=(python3-rosdep)
    fi
    if ! command_exists colcon; then
        missing_apt_package_names+=(python3-colcon-common-extensions)
    fi
    # Ubuntu's python3 lacks ensurepip, which `python -m venv` needs, until python3-venv is installed
    if [[ ! -d .venv ]] && ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
        missing_apt_package_names+=(python3-venv)
    fi
    # -z "$(ls -A ...)" is true when the folder has no file in it
    if [[ ! -d "$ROSDEP_SOURCES_FOLDER_PATH" || -z "$(ls -A "$ROSDEP_SOURCES_FOLDER_PATH")" ]]; then
        other_sudo_command_lines+=("sudo rosdep init")
    fi
}

# Co-authored by Claude Code
# Ask rosdep which system packages the nodes and the released packages need but are missing, without
# installing them (--simulate), and add them to missing_apt_package_names. A command that is not an
# apt install goes into other_sudo_command_lines as rosdep prints it.
#   collect_missing_rosdep_packages <ros_packages_manifest_dir>
collect_missing_rosdep_packages() {
    local ros_packages_manifest_dir="$1"
    local simulate_output_text
    if ! simulate_output_text="$(rosdep install --simulate --from-paths src packages "$ros_packages_manifest_dir" \
            --ignore-src -y 2>&1)"; then
        printf '%s\n' "$simulate_output_text" >&2
        die "rosdep could not resolve the dependencies above -- fix the package.xml naming them"
    fi

    # rosdep prints e.g. "  sudo -H apt-get install -y ros-lyrical-foo", one line per package
    local apt_install_pattern='^sudo -H apt-get install -y (.+)$'
    local output_line trimmed_line
    while IFS= read -r output_line; do
        # Strip the leading spaces: ${var%%[![:space:]]*} is the leading whitespace, removed with #
        trimmed_line="${output_line#"${output_line%%[![:space:]]*}"}"
        if [[ "$trimmed_line" =~ $apt_install_pattern ]]; then
            # The captured package list may hold several names; word splitting adds each one
            # shellcheck disable=SC2206
            missing_apt_package_names+=(${BASH_REMATCH[1]})
        elif [[ "$trimmed_line" == sudo\ * ]]; then
            other_sudo_command_lines+=("$trimmed_line")
        fi
    done <<< "$simulate_output_text"
}

# Co-authored by Claude Code
# Print every command step 2 found necessary as one line, joined with &&, e.g.
# "sudo apt-get install -y git ros-lyrical-foo && sudo rosdep init". Prints nothing when nothing is
# needed. Duplicates (a tool rosdep also wants) are installed once: sort -u.
create_sudo_command_line() {
    local command_lines=()
    if (( ${#missing_apt_package_names[@]} > 0 )); then
        local unique_package_names_text
        unique_package_names_text="$(printf '%s\n' "${missing_apt_package_names[@]}" | sort -u | tr '\n' ' ')"
        command_lines+=("sudo apt-get install -y ${unique_package_names_text% }")
    fi
    command_lines+=("${other_sudo_command_lines[@]}")
    if (( ${#command_lines[@]} == 0 )); then
        return
    fi

    local joined_command_line="${command_lines[0]}" command_line
    for command_line in "${command_lines[@]:1}"; do
        joined_command_line+=" && ${command_line}"
    done
    echo "$joined_command_line"
}

# 1. Node repositories
"${REPO_ROOT}/scripts/sync_nodes.sh"

ros_setup_script_path="/opt/ros/${ROS_DISTRO}/setup.bash"
if [[ ! -f "$ros_setup_script_path" ]]; then
    die "ROS 2 '${ROS_DISTRO}' not found at ${ros_setup_script_path} -- install it with the guide at https://docs.ros.org (ros-${ROS_DISTRO}-desktop), or set ROS_DISTRO to the installed one"
fi

# ROS's setup script reads variables that may be unset, which set -u would stop at. So -u is switched
# off while it runs.
set +u
source "$ros_setup_script_path"
set -u

# 2. Build tools and apt dependencies
step "Installing build tools and apt dependencies (rosdep)"
# nullglob makes a pattern without matches expand to nothing instead of staying as literal text
shopt -s nullglob
# The released packages of config/installed_ros_packages.list, as a package.xml
# rosdep can read. It goes into a temporary directory outside the workspace, so colcon never builds it;
# `trap ... EXIT` deletes the directory when the script ends, also after an error.
ros_packages_dir="$(mktemp -d)"
trap 'rm -rf "$ros_packages_dir"' EXIT
write_ros_packages_manifest "$ros_packages_dir"

collect_missing_build_tools
if [[ "$is_non_interactive" == true ]]; then
    # rosdep can only list what the nodes need once it is installed and set up (no `sudo rosdep init`
    # pending); otherwise the tools come first and the next run lists the rest
    if command_exists rosdep && (( ${#other_sudo_command_lines[@]} == 0 )); then
        if [[ ! -e "$ROSDEP_CACHE_PATH" ]]; then
            rosdep update
        fi
        collect_missing_rosdep_packages "$ros_packages_dir"
    fi
    sudo_command_line="$(create_sudo_command_line)"
    if [[ -n "$sudo_command_line" ]]; then
        warn "some packages need root to install; run this in a terminal, then run the build again:"
        echo "${SUDO_COMMAND_LINE_PREFIX}${sudo_command_line}"
        exit "$EXIT_CODE_NEEDS_SUDO"
    fi
    ok "build tools and apt dependencies installed"
else
    sudo_command_line="$(create_sudo_command_line)"
    if [[ -n "$sudo_command_line" ]]; then
        info "installing build tools: ${sudo_command_line}"
        # The line holds only commands built above from fixed names and rosdep's package names
        bash -c "$sudo_command_line"
    fi
    if [[ ! -e "$ROSDEP_CACHE_PATH" ]]; then
        rosdep update
    fi
    # --ignore-src: packages that are in the workspace are built, not installed.
    rosdep install --from-paths src packages "$ros_packages_dir" --ignore-src -y
fi

# 3. PyPI dependencies
step "Installing PyPI dependencies into .venv"
if [[ ! -d .venv ]]; then
    # --system-site-packages keeps rclpy, cv_bridge and colcon from apt importable.
    python3 -m venv --system-site-packages .venv
    # Tells colcon not to look for packages inside the venv
    touch .venv/COLCON_IGNORE
fi

# One pip install for all nodes, so conflicting pins fail instead of one node silently overwriting
# another's.
pip_args=()
for requirements_file in src/*/requirements.txt packages/*/requirements.txt setup_wizard/backend/requirements.txt; do
    pip_args+=(-r "$requirements_file")
done
if (( ${#pip_args[@]} > 0 )); then
    # pip keeps each downloaded wheel in a temporary file until it is installed. /tmp is often a small RAM disk
    # (tmpfs), too small for large wheels such as torch with its CUDA libraries, so pip's temporary files go to
    # the workspace's gitignored build folder on disk instead. pip removes its files there when it is done.
    pip_temp_folder_path="${REPO_ROOT}/build/pip_tmp"
    mkdir -p "$pip_temp_folder_path"
    TMPDIR="$pip_temp_folder_path" .venv/bin/python -m pip install "${pip_args[@]}"
fi

# 4. Build. Through the venv's python, so node executables run with the venv's packages.
step "Building the workspace"
build_args=(--symlink-install --base-paths src packages)
if (( ${#selected_package_names[@]} > 0 )); then
    build_args+=(--packages-select "${selected_package_names[@]}")
fi
.venv/bin/python -m colcon build "${build_args[@]}"

ok "workspace built"
info "in each new bash terminal:"
info "  source ${ros_setup_script_path} && source .venv/bin/activate && source install/setup.bash"
info "  export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA"
