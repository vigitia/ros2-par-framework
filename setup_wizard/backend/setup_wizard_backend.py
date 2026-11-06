# Written by Claude Code
"""
Backend of the PAR setup wizard.

Runs on the PAR machine and does everything that touches it (profiles, cameras, displays,
launches), so the Flutter app can talk to it the same way from the desktop now and from a phone or
browser later. Start it from the repository root, in a bash with the workspace sourced (it reads
the profiles through par_framework_core):
    source /opt/ros/lyrical/setup.bash && source install/setup.bash
    .venv/bin/python setup_wizard/backend/setup_wizard_backend.py
API docs, to try every endpoint in the browser: http://127.0.0.1:8800/docs
"""

import socket

from fastapi import FastAPI
import profiles_api
import uvicorn

# Localhost only: nothing protects the backend yet, so other machines in the network must not
# reach it.
SETUP_WIZARD_BACKEND_HOST = '127.0.0.1'
# Not 8000, which the worksheets app's backend uses.
SETUP_WIZARD_BACKEND_PORT = 8800

setup_wizard_backend_app = FastAPI(title='PAR setup wizard backend')
# One module per area of the app, each with its own APIRouter (e.g. profiles_api.py), so the areas
# can be built independently; a new module needs only its include_router line here.
setup_wizard_backend_app.include_router(profiles_api.profiles_router)


@setup_wizard_backend_app.get('/api/status')
def get_backend_status() -> dict:
    """Tell the app that the backend runs and on which machine, the machine the UI controls."""
    return {'machine_name': socket.gethostname()}


def main() -> None:
    uvicorn.run(setup_wizard_backend_app, host=SETUP_WIZARD_BACKEND_HOST,
                port=SETUP_WIZARD_BACKEND_PORT)


if __name__ == '__main__':
    main()
