#!/usr/bin/env bash
# Clone (or update) every repository listed in config/required_repos.list and config/installed_repos.list into src/.
# Each repo stays a normal git repo you can commit and push from.
# Co-authored by Claude Code: called by scripts/local_build.sh; split into functions for readability; reads
# the installed list next to the required list and reports git's own error for a failed clone.
#
# A repository is never changed when that could lose work: a checkout with uncommitted changes, on another
# branch than its list names, or with local commits is reported and left as it is.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

SRC_DIR="${REPO_ROOT}/src"

# A repo that fails to sync should not hide the state of the others, so failures are collected here and
# reported together at the end.
failures=()

# Co-authored by Claude Code
# Clone a repository that is not in src/ yet. Returns 1 (and records a failure) when the clone fails.
clone_repo() {
    local repo_dir_name="$1" url="$2" branch="$3" repo_checkout_path="$4"

    info "cloning ${repo_dir_name} <- ${url}"
    local clone_args=(--quiet)
    if [[ "$branch" != "$NO_BRANCH" ]]; then
        clone_args+=(--branch "$branch")
    fi

    # git's own message (e.g. no access, branch not found) is kept to show it when the clone fails
    local clone_error_text
    if ! clone_error_text="$(git clone "${clone_args[@]}" "$url" "$repo_checkout_path" 2>&1)"; then
        rm -rf "$repo_checkout_path"    # remove what a half-finished clone left behind
        warn "${repo_dir_name}: clone failed: ${clone_error_text}"
        hint "check the URL in config/required_repos.list or config/installed_repos.list"
        if [[ "$branch" != "$NO_BRANCH" ]]; then
            hint "check that branch '${branch}' exists"
        fi
        hint "for an SSH URL (git@github.com:...): ssh -T git@github.com must greet you; else add an SSH key to GitHub"
        hint "a repository with no commits yet has no branches -- push it first"
        failures+=("$repo_dir_name")
        return 1
    fi
}

# Co-authored by Claude Code
# Fast-forward an existing checkout to its upstream branch. Returns 1 when the checkout is left
# untouched; that is a warning, not a failure, because the existing checkout still builds.
update_repo() {
    local repo_dir_name="$1" branch="$2" repo_checkout_path="$3"

    # --porcelain prints one line per changed file, so any output means uncommitted changes
    if [[ -n "$(git -C "$repo_checkout_path" status --porcelain)" ]]; then
        warn "${repo_dir_name} has uncommitted changes -- leaving it untouched"
        return 1
    fi

    local current_branch
    current_branch="$(git -C "$repo_checkout_path" rev-parse --abbrev-ref HEAD)"
    if [[ "$branch" != "$NO_BRANCH" && "$current_branch" != "$branch" ]]; then
        warn "${repo_dir_name} is on '${current_branch}', its list says '${branch}' -- leaving it untouched"
        return 1
    fi

    # Handled explicitly: set -e does not stop a function that is called as a condition (update_repo || ...)
    if ! git -C "$repo_checkout_path" fetch --quiet --prune origin; then
        warn "${repo_dir_name} could not fetch from origin (offline?) -- leaving it untouched"
        return 1
    fi

    # @{upstream} is the remote branch the current branch tracks, e.g. origin/main. --ff-only refuses
    # instead of creating a merge commit when there are local commits.
    if ! git -C "$repo_checkout_path" merge --quiet --ff-only "@{upstream}" 2>/dev/null; then
        warn "${repo_dir_name} could not fast-forward (diverged from upstream?) -- leaving it untouched"
        return 1
    fi
}

# Co-authored by Claude Code
# A repository that exists but has never been pushed to clones "successfully" into an empty directory,
# which would otherwise surface much later as a ROS package that is inexplicably missing. Returns 1 (and
# records a failure) in that case.
check_repo_has_commits() {
    local repo_dir_name="$1" url="$2" repo_checkout_path="$3"

    if ! git -C "$repo_checkout_path" rev-parse HEAD >/dev/null 2>&1; then
        warn "${repo_dir_name}: repository is empty -- nothing has been pushed to ${url}"
        hint "commit and push it, then re-run ./scripts/local_build.sh"
        failures+=("$repo_dir_name")
        return 1
    fi
}

step "Syncing node repositories"
mkdir -p "$SRC_DIR"

# Co-authored by Claude Code
# read_repos_to_build prints "<dir><TAB><url><TAB><branch>" per entry; IFS=$'\t' splits each line at
# the tabs. It runs first on its own, so a broken list stops the script instead of silently syncing fewer
# repos. `<<<` feeds the entries into the loop; a pipe (... | while ...) would run the loop in a subshell,
# and the failures it records would be lost when the subshell ends.
node_entries="$(read_repos_to_build)" || die "fix the list named above"
while IFS=$'\t' read -r repo_dir_name url branch; do
    if [[ -z "$repo_dir_name" ]]; then
        continue    # no entries at all
    fi
    repo_checkout_path="${SRC_DIR}/${repo_dir_name}"

    # An empty repository has no branch yet, so it is checked before update_repo asks for one
    if [[ -d "${repo_checkout_path}/.git" ]]; then
        check_repo_has_commits "$repo_dir_name" "$url" "$repo_checkout_path" || continue
        update_repo "$repo_dir_name" "$branch" "$repo_checkout_path" || continue
    else
        clone_repo "$repo_dir_name" "$url" "$branch" "$repo_checkout_path" || continue
        check_repo_has_commits "$repo_dir_name" "$url" "$repo_checkout_path" || continue
    fi

    ok "${repo_dir_name} at $(git -C "$repo_checkout_path" rev-parse --short HEAD)"
done <<< "$node_entries"

if (( ${#failures[@]} > 0 )); then
    die "could not sync: ${failures[*]}"
fi
