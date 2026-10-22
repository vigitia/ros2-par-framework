#!/usr/bin/env bash
# Clone (or update) every repository listed in config/nodes.list into src/.
# Each repo stays a normal git repo you can commit and push from.
# Co-authored by Claude Code: called by scripts/local_build.sh.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

SRC_DIR="${REPO_ROOT}/src"

# A repo that fails to sync should not hide the state of the others, so failures
# are collected and reported together at the end.
failures=()

step "Syncing node repositories"
mkdir -p "$SRC_DIR"

while IFS=$'\t' read -r dir url branch; do
    target="${SRC_DIR}/${dir}"

    if [[ ! -d "$target/.git" ]]; then
        info "cloning ${dir} <- ${url}"
        clone_args=(--quiet)
        [[ "$branch" != "-" ]] && clone_args+=(--branch "$branch")
        if ! git clone "${clone_args[@]}" "$url" "$target" 2>/dev/null; then
            rm -rf "$target"
            warn "${dir}: clone failed"
            hint "check the URL in config/nodes.list and that branch '${branch}' exists"
            hint "a repository with no commits yet has no branches -- push it first"
            failures+=("$dir")
            continue
        fi
    else
        # Existing checkout: never throw away work. Fast-forward only when the
        # tree is clean and on the expected branch, otherwise report and move on.
        if [[ -n "$(git -C "$target" status --porcelain)" ]]; then
            warn "${dir} has uncommitted changes -- leaving it untouched"
            continue
        fi

        current="$(git -C "$target" rev-parse --abbrev-ref HEAD)"
        if [[ "$branch" != "-" && "$current" != "$branch" ]]; then
            warn "${dir} is on '${current}', nodes.list says '${branch}' -- leaving it untouched"
            continue
        fi

        git -C "$target" fetch --quiet --prune origin
        if ! git -C "$target" merge --quiet --ff-only "@{upstream}" 2>/dev/null; then
            warn "${dir} could not fast-forward (diverged from upstream?) -- leaving it untouched"
            continue
        fi
    fi

    # A repository that exists but has never been pushed to clones "successfully"
    # into an empty directory, which would otherwise surface much later as a ROS
    # package that is inexplicably missing.
    if ! git -C "$target" rev-parse HEAD >/dev/null 2>&1; then
        warn "${dir}: repository is empty -- nothing has been pushed to ${url}"
        hint "commit and push it, then re-run ./scripts/local_build.sh"
        failures+=("$dir")
        continue
    fi

    ok "${dir} at $(git -C "$target" rev-parse --short HEAD)"
done < <(read_nodes_list)

if (( ${#failures[@]} > 0 )); then
    die "could not sync: ${failures[*]}"
fi
