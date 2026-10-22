#!/usr/bin/env bash
# Drop into a shell in the running container, with ROS and the workspace sourced.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

require_container_running

# Unlike the other scripts this one is interactive by definition, so a missing
# terminal is a usage error rather than something to work around.
[[ -t 0 && -t 1 ]] || die "shell.sh needs a terminal -- run it directly, not from a script or a pipe"

exec docker exec -it "$(container_name)" /usr/local/bin/entrypoint.sh bash
