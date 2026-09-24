#!/usr/bin/env bash
# Clone (or update) every repository listed in config/nodes.list into src/, then
# stage the dependency manifests of every package they contain for the image build.
#
# src/ is bind-mounted into the container, so what you check out here is exactly
# what runs -- and each repo stays a normal git repo you can commit and push from.
#
# --clone-only skips the staging, for host-side builds without Docker
# (scripts/local_build.sh). Co-authored by Claude Code.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

SRC_DIR="${REPO_ROOT}/src"
DEPS_DIR="${REPO_ROOT}/docker/deps"

# Co-authored by Claude Code
clone_only=false
[[ "${1:-}" == "--clone-only" ]] && clone_only=true

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
        hint "commit and push it, then re-run ./setup.sh"
        failures+=("$dir")
        continue
    fi

    ok "${dir} at $(git -C "$target" rev-parse --short HEAD)"
done < <(read_nodes_list)

# Co-authored by Claude Code
if $clone_only; then
    (( ${#failures[@]} == 0 )) || die "could not sync: ${failures[*]}"
    exit 0
fi

# The image installs dependencies from manifests only, never from source. Staging
# them in their own directory means editing code does not invalidate the (slow)
# rosdep and pip layers -- only touching a package.xml or requirements.txt does.
#
# A repository may hold its package at the root, or one level down, and may hold
# more than one, so every package.xml in the checkout is staged under its declared
# package name rather than its directory name. This repo's own bringup package is
# staged too, so its dependencies resolve alongside the nodes'.
step "Staging dependency manifests"
rm -rf "$DEPS_DIR"
mkdir -p "$DEPS_DIR"

staged=0
while IFS= read -r manifest; do
    [[ -n "$manifest" ]] || continue
    pkg_dir="$(dirname "$manifest")"
    name="$(sed -n 's:.*<name>\(.*\)</name>.*:\1:p' "$manifest" | head -1)"
    if [[ -z "$name" ]]; then
        warn "${manifest#"$REPO_ROOT"/} declares no <name> -- skipping"
        continue
    fi

    mkdir -p "${DEPS_DIR}/${name}"
    cp "$manifest" "${DEPS_DIR}/${name}/package.xml"

    # requirements.txt sits next to package.xml, or at the root of a checkout
    # whose package lives in a subdirectory.
    for candidate in "${pkg_dir}/requirements.txt" "${pkg_dir}/../requirements.txt"; do
        if [[ -f "$candidate" ]]; then
            cp "$candidate" "${DEPS_DIR}/${name}/requirements.txt"
            break
        fi
    done

    staged=$((staged + 1))
done < <(
    find "$SRC_DIR" -mindepth 2 -maxdepth 3 -name package.xml \
        -not -path '*/.git/*' -not -path '*/build/*' -not -path '*/install/*' 2>/dev/null
    find "${REPO_ROOT}/bringup" -maxdepth 1 -name package.xml 2>/dev/null
)

(( staged > 0 )) || die "no ROS packages found under src/ -- nothing to build"
ok "staged manifests for ${staged} package(s)"

if (( ${#failures[@]} > 0 )); then
    die "could not sync: ${failures[*]}"
fi
