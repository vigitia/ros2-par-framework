# Written by Claude Code
"""
Backend of the PAR setup wizard.

Runs on the PAR machine and does everything that touches it (profiles, cameras, displays, launches), so the
Flutter app can talk to it the same way from the desktop now and from a phone or browser later.
Start it with the workspace's venv, from the repository root:
    .venv/bin/python setup_wizard/backend/setup_wizard_backend.py
API docs, to try every endpoint in the browser: http://127.0.0.1:8800/docs
"""

import socket

from fastapi import FastAPI
import uvicorn

# Localhost only: nothing protects the backend yet, so other machines in the network must not reach it.
SETUP_WIZARD_BACKEND_HOST = '127.0.0.1'
# Not 8000, which the worksheets app's backend uses.
SETUP_WIZARD_BACKEND_PORT = 8800

setup_wizard_backend_app = FastAPI(title='PAR setup wizard backend')


@setup_wizard_backend_app.get('/api/status')
def get_backend_status() -> dict:
    """Tell the app that the backend runs, and on which machine, so the UI can show what it controls."""
    return {'machine_name': socket.gethostname()}


def main() -> None:
    uvicorn.run(setup_wizard_backend_app, host=SETUP_WIZARD_BACKEND_HOST, port=SETUP_WIZARD_BACKEND_PORT)


if __name__ == '__main__':
    main()
