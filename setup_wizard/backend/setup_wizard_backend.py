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

import os
import socket

from apps import apps_api
from calibration import extrinsics_api
from calibration import intrinsics_api
from calibration import setup_geometry_api
from cameras import camera_preview_api
from cameras import cameras_api
from cameras import focus_api
from fastapi import FastAPI
from install import install_api
from profiles import profiles_api
from projectors import displays_api
from projectors import projector_blackout_api
from run import run_api
from sensor_nodes import sensor_nodes_api
from shared import node_settings_api
import uvicorn

# Localhost only: nothing protects the backend yet, so other machines in the network must not
# reach it.
SETUP_WIZARD_BACKEND_HOST = '127.0.0.1'
# Not 8000, which the worksheets app's backend uses.
SETUP_WIZARD_BACKEND_PORT = 8800
# The framework's large camera images need this Fast DDS transport (README), and processes with
# different transports do not discover each other. Set for the backend itself, before its ROS
# node starts (rclpy.init in camera_launch_session's lifespan), so the backend and every process it
# starts (runs, previews, calibrations, settings reads) inherit the same; a value set before the
# backend starts wins, e.g. for testing
FASTDDS_TRANSPORTS_ENVIRONMENT_NAME = 'FASTDDS_BUILTIN_TRANSPORTS'
FASTDDS_TRANSPORTS_VALUE = 'LARGE_DATA'
os.environ.setdefault(FASTDDS_TRANSPORTS_ENVIRONMENT_NAME, FASTDDS_TRANSPORTS_VALUE)

setup_wizard_backend_app = FastAPI(title='PAR setup wizard backend')
# One module per area of the app, each with its own APIRouter (e.g. profiles_api.py), so the areas
# can be built independently; a new module needs only its include_router line here.
setup_wizard_backend_app.include_router(profiles_api.profiles_router)
setup_wizard_backend_app.include_router(cameras_api.cameras_router)
setup_wizard_backend_app.include_router(camera_preview_api.camera_preview_router)
setup_wizard_backend_app.include_router(focus_api.focus_router)
setup_wizard_backend_app.include_router(displays_api.displays_router)
setup_wizard_backend_app.include_router(intrinsics_api.intrinsics_router)
setup_wizard_backend_app.include_router(extrinsics_api.extrinsics_router)
setup_wizard_backend_app.include_router(apps_api.apps_router)
setup_wizard_backend_app.include_router(projector_blackout_api.projector_blackout_router)
setup_wizard_backend_app.include_router(sensor_nodes_api.sensor_nodes_router)
setup_wizard_backend_app.include_router(run_api.run_router)
setup_wizard_backend_app.include_router(setup_geometry_api.setup_geometry_router)
setup_wizard_backend_app.include_router(node_settings_api.node_settings_router)
setup_wizard_backend_app.include_router(install_api.install_router)


@setup_wizard_backend_app.get('/api/status')
def get_backend_status() -> dict:
    """Tell the app that the backend runs and on which machine, the machine the UI controls."""
    return {'machine_name': socket.gethostname()}


def main() -> None:
    """Serve the API; after a successful install, start anew so the new packages are found."""
    backend_server = uvicorn.Server(uvicorn.Config(setup_wizard_backend_app,
                                                   host=SETUP_WIZARD_BACKEND_HOST,
                                                   port=SETUP_WIZARD_BACKEND_PORT))
    install_api.set_backend_server_for_restart(backend_server)
    backend_server.run()
    if install_api.is_backend_restart_requested():
        install_api.restart_backend()


if __name__ == '__main__':
    main()
