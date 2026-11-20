#!/usr/bin/env bash
# Shared helpers for the scripts in this directory.
# Not executable on its own: the other scripts load it with `source`.
# Written by Claude Code

# Stop at the first error instead of carrying on with a half-done step:
#   -e           exit when a command fails
#   -u           treat the use of an unset variable as an error (catches typos)
#   -o pipefail  a pipeline fails when any command in it fails, not only the last one
set -euo pipefail

# Absolute path of the repository, so the scripts work from any current directory.
# BASH_SOURCE[0] is this file, scripts/common.sh; its parent directory is the repository root.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_ROOT

# ROS 2 distribution the scripts source from /opt/ros. An already set value wins, e.g. from a
# sourced ROS or `ROS_DISTRO=jazzy ./scripts/local_build.sh`.
ROS_DISTRO="${ROS_DISTRO:-lyrical}"

# ---------------------------------------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------------------------------------

# Terminal colours, only when the output is a terminal (-t 1: stdout is a terminal). In a log file the
# escape codes would only be noise.
if [[ -t 1 ]]; then
    C_RESET=$'\033[0m'
    C_BOLD=$'\033[1m'
    C_DIM=$'\033[2m'
    C_RED=$'\033[31m'
    C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'
    C_BLUE=$'\033[34m'
else
    C_RESET=''
    C_BOLD=''
    C_DIM=''
    C_RED=''
    C_GREEN=''
    C_YELLOW=''
    C_BLUE=''
fi

# Co-authored by Claude Code
# Message helpers. "$*" is all arguments joined into one string. Warnings, hints and errors go to stderr
# (>&2), so they stay visible when stdout is redirected.

# Heading of a new step, e.g. "==> Building the workspace"
step() {
    printf '\n%s\n' "${C_BLUE}==>${C_RESET} ${C_BOLD}$*${C_RESET}"
}

# Plain indented line
info() {
    printf '    %s\n' "$*"
}

# Something succeeded
ok() {
    printf '    %s\n' "${C_GREEN}✓${C_RESET} $*"
}

# Something is wrong, but the script carries on
warn() {
    printf '    %s\n' "${C_YELLOW}!${C_RESET} $*" >&2
}

# Advice below a warning, e.g. the command that fixes it
hint() {
    printf '      %s\n' "${C_DIM}$*${C_RESET}" >&2
}

# Print an error and stop the script
die() {
    printf '\n%s\n' "${C_RED}error:${C_RESET} $*" >&2
    exit 1
}

# Co-authored by Claude Code
# True when the given command is installed, e.g. `command_exists colcon || die "..."`.
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------------------------------------
# Reading the list files in config/
# ---------------------------------------------------------------------------------------------------------

# Placeholder in read_repos_list's output for an entry without a branch. An empty field would not work:
# `read` with a tab separator merges two tabs in a row, so the fields would shift.
NO_BRANCH="-"

# The lists the build reads: the tracked required list and the gitignored list of what this installation
# added (written by the setup wizard). The second one may be missing.
REQUIRED_REPOS_LIST_PATH="${REPO_ROOT}/config/required_repos.list"
INSTALLED_REPOS_LIST_PATH="${REPO_ROOT}/config/installed_repos.list"
REQUIRED_ROS_PACKAGES_LIST_PATH="${REPO_ROOT}/config/required_ros_packages.list"
INSTALLED_ROS_PACKAGES_LIST_PATH="${REPO_ROOT}/config/installed_ros_packages.list"

# Co-authored by Claude Code
# Read a list in the required_repos.list format and print one line "<dir><TAB><url><TAB><branch>" per entry.
# Comments and blank lines are skipped, and a missing branch is printed as $NO_BRANCH.
#   read_repos_list <list_path>
read_repos_list() {
    local list="$1"
    if [[ ! -f "$list" ]]; then
        die "missing $list"
    fi

    local line line_number=0 dir url branch
    # `|| [[ -n "$line" ]]` also reads a last line that has no line break at its end
    while IFS= read -r line || [[ -n "$line" ]]; do
        line_number=$((line_number + 1))
        line="${line%%#*}"    # drop the comment: everything from the first '#'

        # Split at whitespace; words after the third are ignored
        read -r dir url branch _ <<< "$line"
        if [[ -z "$dir" ]]; then
            continue          # blank or comment-only line
        fi
        if [[ -z "$url" ]]; then
            echo "${list} line ${line_number}: expected \"<dir> <url> [branch]\"" >&2
            return 1
        fi

        printf '%s\t%s\t%s\n' "$dir" "$url" "${branch:-$NO_BRANCH}"
    done < "$list"
}

# Co-authored by Claude Code
# Read every repository the build installs: the required list, then the installed list if it exists.
# Prints the read_repos_list format. A directory in both lists is printed once, from the required list; a
# different URL or branch for it in the installed list is reported and ignored.
read_repos_to_build() {
    local required_entries installed_entries=""
    required_entries="$(read_repos_list "$REQUIRED_REPOS_LIST_PATH")" || return 1
    if [[ -f "$INSTALLED_REPOS_LIST_PATH" ]]; then
        installed_entries="$(read_repos_list "$INSTALLED_REPOS_LIST_PATH")" || return 1
    fi

    # Directory -> "<url><TAB><branch>" of the entry already printed
    local -A printed_entry_by_dir=()
    local dir url branch
    while IFS=$'\t' read -r dir url branch; do
        if [[ -z "$dir" ]]; then
            continue          # an empty list gives one empty line
        fi
        if [[ -v "printed_entry_by_dir[$dir]" ]]; then
            if [[ "${printed_entry_by_dir[$dir]}" != "${url}"$'\t'"${branch}" ]]; then
                warn "${dir} is listed twice with different URLs or branches; using the first entry"
                hint "fix ${INSTALLED_REPOS_LIST_PATH}"
            fi
            continue
        fi
        printed_entry_by_dir[$dir]="${url}"$'\t'"${branch}"
        printf '%s\t%s\t%s\n' "$dir" "$url" "$branch"
    done <<< "${required_entries}"$'\n'"${installed_entries}"
}

# Co-authored by Claude Code
# Read a list in the required_ros_packages.list format and print one rosdep key per line. Comments and blank
# lines are skipped. The keys end up in a generated package.xml, so anything that is not a plain key
# fails here instead of producing broken XML.
#   read_ros_packages_list <list_path>
read_ros_packages_list() {
    local list="$1"
    if [[ ! -f "$list" ]]; then
        die "missing $list"
    fi

    local line line_number=0 key extra
    while IFS= read -r line || [[ -n "$line" ]]; do
        line_number=$((line_number + 1))
        line="${line%%#*}"    # drop the comment

        read -r key extra <<< "$line"
        if [[ -z "$key" ]]; then
            continue          # blank or comment-only line
        fi
        if [[ -n "$extra" || ! "$key" =~ ^[A-Za-z0-9_.-]+$ ]]; then
            echo "${list} line ${line_number}: expected one rosdep key" >&2
            return 1
        fi

        echo "$key"
    done < "$list"
}

# Co-authored by Claude Code
# Write <output_dir>/par_ros_packages/package.xml: a package that only depends on every key of
# config/required_ros_packages.list and config/installed_ros_packages.list (if it exists), so that
# `rosdep install --from-paths <output_dir>` installs those packages the same way it installs the
# nodes' dependencies.
write_ros_packages_manifest() {
    local output_dir="$1"
    local keys
    keys="$(read_ros_packages_list "$REQUIRED_ROS_PACKAGES_LIST_PATH")" || die "fix ${REQUIRED_ROS_PACKAGES_LIST_PATH}"
    if [[ -f "$INSTALLED_ROS_PACKAGES_LIST_PATH" ]]; then
        local installed_keys
        installed_keys="$(read_ros_packages_list "$INSTALLED_ROS_PACKAGES_LIST_PATH")" \
            || die "fix ${INSTALLED_ROS_PACKAGES_LIST_PATH}"
        # A key in both lists once: sort -u removes duplicates
        keys="$(printf '%s\n%s\n' "$keys" "$installed_keys" | sort -u)"
    fi

    # One <exec_depend> line per key
    local depends="" key
    for key in $keys; do
        depends+="  <exec_depend>${key}</exec_depend>"$'\n'
    done

    mkdir -p "${output_dir}/par_ros_packages"
    # The license is required by rosdep's manifest parser; it is the same as par_framework_core's
    cat > "${output_dir}/par_ros_packages/package.xml" <<EOF
<?xml version="1.0"?>
<!-- Generated from config/required_ros_packages.list and config/installed_ros_packages.list by scripts/common.sh -->
<package format="3">
  <name>par_ros_packages</name>
  <version>0.0.0</version>
  <description>Released packages listed in config/required_ros_packages.list and config/installed_ros_packages.list.</description>
  <maintainer email="none@example.com">generated</maintainer>
  <license>MIT</license>
${depends}</package>
EOF
}
