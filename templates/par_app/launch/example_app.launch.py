# Written by Claude Code
"""
Start the example app with everything it owns: its node and its web frontend.

par.launch.py includes this file when the profile chooses the app (par_launch.projector_app) and
passes params_file, profile and display_id. Shared framework nodes (detectors, page_locator) are
not started here: the app's entry names them in required_launch_switches, and par.launch.py
starts them once for everyone. Started alone, for development:

    ros2 launch example_app example_app.launch.py profile:=<name> display_id:=1
"""

import os
import sys

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from par_framework_core.launch_helpers import create_profile_launch_argument, get_params_file_paths

PACKAGE_NAME = 'example_app'
NODE_NAME = 'example_app_node'
# Optional: a web frontend served on this machine only
FRONTEND_PORT = 8090


def launch_setup(context):
    node_parameters = list(get_params_file_paths(context))
    # Empty: the node keeps the display_id of the parameter files
    display_id_text = LaunchConfiguration('display_id').perform(context)
    if display_id_text:
        node_parameters.append({'display_id': int(display_id_text)})

    launch_actions = [
        Node(package=PACKAGE_NAME,
             executable=PACKAGE_NAME,
             name=NODE_NAME,
             output='screen',
             emulate_tty=True,
             parameters=node_parameters),
    ]

    # Optional: a process that is no ROS node, e.g. a web server. ExecuteProcess ties it to the
    # launch: it starts with it and is stopped with it (SIGINT, then SIGTERM), so nothing keeps
    # running after Ctrl+C. The frontend is built before (npm run build) and installed with the
    # package (setup.py), so it needs no build tool at start. sys.executable: the same Python the
    # launch runs in.
    frontend_folder_path = os.path.join(get_package_share_directory(PACKAGE_NAME), 'frontend')
    launch_actions.append(ExecuteProcess(
        cmd=[sys.executable, '-m', 'http.server', str(FRONTEND_PORT), '--bind', '127.0.0.1',
             '--directory', frontend_folder_path],
        name=f'{PACKAGE_NAME}_frontend',
        output='screen'))
    return launch_actions


def generate_launch_description():
    default_params_file_path = os.path.join(
        get_package_share_directory('par_framework_core'), 'config', 'par_setup.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('params_file', default_value=default_params_file_path,
                              description='Parameter file of this physical PAR setup.'),
        create_profile_launch_argument(),
        DeclareLaunchArgument('display_id', default_value='',
                              description='Display of the projector, counted like SDL/pygame '
                                          '(0 = primary). Empty keeps the value of the parameter '
                                          'files.'),
        OpaqueFunction(function=launch_setup),
    ])
