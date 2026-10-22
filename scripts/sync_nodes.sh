#!/usr/bin/env bash
# Clone (or update) every repository listed in config/nodes.list into src/.
# Each repo stays a normal git repo you can commit and push from.
# Co-authored by Claude Code: called by scripts/local_build.sh; split into functions for readability.
#
# A repository is never changed when that could lose work: a checkout with uncommitted changes, on another
# branch than nodes.list names, or with local commits is reported and left as it is.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

SRC_DIR="${REPO_ROOT}/src"

# A repo that fails to sync should not hide the state of the others, so failures are collected here and
# reported together at the end.
failures=()

# Co-authored by Claude Code
# Clone a repository that is not in src/ yet. Returns 1 (and records a failure) when the clone fails.
clone_repo() {
    local dir="$1" url="$2" branch="$3" target="$4"

    info "cloning ${dir} <- ${url}"
    local clone_args=(--quiet)
    if [[ "$branch" != "$NO_BRANCH" ]]; then
        clone_args+=(--branch "$branch")
    fi

    if ! git clone "${clone_args[@]}" "$url" "$target" 2>/dev/null; then
        rm -rf "$target"    # remove what a half-finished clone left behind
        warn "${dir}: clone failed"
        hint "check the URL in config/nodes.list and that branch '${branch}' exists"
        hint "a repository with no commits yet has no branches -- push it first"
        failures+=("$dir")
        return 1
    fi
}

# Co-authored by Claude Code
# Fast-forward an existing checkout to its upstream branch. Returns 1 when the checkout is left
# untouched; that is a warning, not a failure, because the existing checkout still builds.
update_repo() {
    local dir="$1" branch="$2" target="$3"

    # --porcelain prints one line per changed file, so any output means uncommitted changes
    if [[ -n "$(git -C "$target" status --porcelain)" ]]; then
        warn "${dir} has uncommitted changes -- leaving it untouched"
        return 1
    fi

    local current_branch
    current_branch="$(git -C "$target" rev-parse --abbrev-ref HEAD)"
    if [[ "$branch" != "$NO_BRANCH" && "$current_branch" != "$branch" ]]; then
        warn "${dir} is on '${current_branch}', nodes.list says '${branch}' -- leaving it untouched"
        return 1
    fi

    # Handled explicitly: set -e does not stop a function that is called as a condition (update_repo || ...)
    if ! git -C "$target" fetch --quiet --prune origin; then
        warn "${dir} could not fetch from origin (offline?) -- leaving it untouched"
        return 1
    fi

    # @{upstream} is the remote branch the current branch tracks, e.g. origin/main. --ff-only refuses
    # instead of creating a merge commit when there are local commits.
    if ! git -C "$target" merge --quiet --ff-only "@{upstream}" 2>/dev/null; then
        warn "${dir} could not fast-forward (diverged from upstream?) -- leaving it untouched"
        return 1
    fi
}

# Co-authored by Claude Code
# A repository that exists but has never been pushed to clones "successfully" into an empty directory,
# which would otherwise surface much later as a ROS package that is inexplicably missing. Returns 1 (and
# records a failure) in that case.
has_commits() {
    local dir="$1" url="$2" target="$3"

    if ! git -C "$target" rev-parse HEAD >/dev/null 2>&1; then
        warn "${dir}: repository is empty -- nothing has been pushed to ${url}"
        hint "commit and push it, then re-run ./scripts/local_build.sh"
        failures+=("$dir")
        return 1
    fi
}

step "Syncing node repositories"
mkdir -p "$SRC_DIR"

# Co-authored by Claude Code
# read_nodes_list prints "<dir><TAB><url><TAB><branch>" per entry; IFS=$'\t' splits each line at the tabs.
# `< <(...)` feeds that output into the loop. A pipe (read_nodes_list | while ...) would run the loop in a
# subshell, and the failures it records would be lost when the subshell ends.
while IFS=$'\t' read -r dir url branch; do
    target="${SRC_DIR}/${dir}"

    # An empty repository has no branch yet, so it is checked before update_repo asks for one
    if [[ -d "${target}/.git" ]]; then
        has_commits "$dir" "$url" "$target" || continue
        update_repo "$dir" "$branch" "$target" || continue
    else
        clone_repo "$dir" "$url" "$branch" "$target" || continue
        has_commits "$dir" "$url" "$target" || continue
    fi

    ok "${dir} at $(git -C "$target" rev-parse --short HEAD)"
done < <(read_nodes_list)

if (( ${#failures[@]} > 0 )); then
    die "could not sync: ${failures[*]}"
fi
