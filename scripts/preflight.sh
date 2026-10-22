#!/usr/bin/env bash
# Verify this machine can build and run the framework, before anything slow or
# half-finished happens. Every failure prints the command that fixes it.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

failed=0
fail() { warn "$1"; shift; for line in "$@"; do hint "$line"; done; failed=1; }

step "Checking prerequisites"

if have docker; then
    ok "docker $(docker --version | sed 's/Docker version //; s/,.*//')"
else
    fail "docker is not installed" \
         "https://docs.docker.com/engine/install/"
fi

if have docker && docker compose version >/dev/null 2>&1; then
    ok "docker compose $(docker compose version --short)"
else
    fail "docker compose v2 is not available" \
         "install the docker-compose-plugin package (not the old 'docker-compose' binary)"
fi

if have docker && ! docker info >/dev/null 2>&1; then
    fail "cannot talk to the docker daemon" \
         "sudo systemctl start docker" \
         "sudo usermod -aG docker \$USER   # then log out and back in"
fi

if have git; then
    ok "git $(git --version | sed 's/git version //')"
else
    fail "git is not installed" "sudo apt install git"
fi

# The node repos are private, so cloning needs a key in the agent. Checking here
# turns a confusing "Permission denied (publickey)" halfway through setup into a
# one-line instruction up front.
if [[ -n "${SSH_AUTH_SOCK:-}" ]] && ssh-add -l >/dev/null 2>&1; then
    ok "ssh-agent has $(ssh-add -l | wc -l) key(s) loaded"
    # `ssh -T git@github.com` always exits non-zero (no shell access), so judge
    # it by what it says, not by its status.
    ssh_reply="$(ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -T git@github.com 2>&1 || true)"
    if [[ "$ssh_reply" == *'successfully authenticated'* ]]; then
        ok "github.com accepts your SSH key"
    else
        fail "github.com rejected your SSH key" \
             "check which key is loaded with: ssh-add -l" \
             "and that it is added at https://github.com/settings/keys"
    fi
else
    fail "no SSH key loaded in ssh-agent (the node repos are private)" \
         "eval \$(ssh-agent -s) && ssh-add ~/.ssh/id_ed25519" \
         "if you have no key yet: ssh-keygen -t ed25519 -C \"\$USER@\$(hostname)\"" \
         "then add the public key at https://github.com/settings/keys"
fi

if [[ -n "${DISPLAY:-}" ]]; then
    ok "DISPLAY=$DISPLAY"
else
    fail "DISPLAY is not set -- RViz and the projector window will not open" \
         "run setup.sh from a graphical session, not a bare SSH shell"
fi

if have v4l2-ctl; then
    cams="$(v4l2-ctl --list-devices 2>/dev/null | grep -c '^\S' || true)"
    ok "v4l2 sees ${cams:-0} capture device(s)"
else
    info "v4l-utils not installed on the host (optional -- it is in the container)"
fi

(( failed == 0 )) || die "prerequisites missing, see above"
ok "all prerequisites satisfied"
