# Written by Claude Code
"""
Start an event camera with metavision_driver as a PAR framework camera (camera type event).

The framework includes this file for the camera type's entry (resource/par_framework_cameras/
event) and passes the arguments every camera launch file declares (templates/par_camera/). Next
to the driver, event_camera_renderer collects the events into images, which become the camera's
image_raw; the raw events are on events. No intrinsics: the driver has no calibration, so
camera_info_url is ignored. Settings (serial, biases) under /cameras/*/event and
/cameras/*/event_renderer in the parameter files.
"""

import os

from launch import LaunchDescription
from launch.actions import LogInfo, OpaqueFunction
from launch_ros.actions import Node
from par_framework_core.launch_helpers import (create_camera_launch_arguments,
                                               create_optical_frame_tf_publisher,
                                               read_camera_launch_arguments)

DRIVER_NODE_NAME = 'event'
RENDERER_NODE_NAME = 'event_renderer'


def launch_setup(context):
    # TODO: intrinsic calibration. The driver publishes no camera_info and offers no
    # set_camera_info, so scripts/run_cameracalibrator.sh cannot store a calibration yet:
    # 1. A node that loads the camera's intrinsics file (as camera_info_url, like the other
    #    cameras), publishes camera_info with each image's header and serves set_camera_info.
    #    First check whether ROS 2 already ships one; otherwise a small node built on
    #    camera_info_manager.
    # 2. A blink source: utils/checkerboard.png full screen on a movable display (not the
    #    projector, the board needs many poses), alternating with black at a few Hz, slower than
    #    the renderer's fps. Only the white squares fire, so each rendered image shows the board.
    #    Not board and inverse: then every square fires, and a slice with two switches is uniform
    camera = read_camera_launch_arguments(context)
    namespace = camera['namespace']
    event_camera_actions = []
    # OpenEB finds plugins that a camera maker ships separately only through this variable.
    # Without it such a camera fails with "cannot open default camera", which names no cause
    if not os.environ.get('MV_HAL_PLUGIN_PATH'):
        event_camera_actions.append(LogInfo(
            msg='[camera_event.launch]: MV_HAL_PLUGIN_PATH is not set: an event camera whose '
                'maker ships its own OpenEB plugin is not found. Set it in this shell, e.g. for a '
                'SilkyEvCam: export MV_HAL_PLUGIN_PATH=/usr/lib/CenturyArks/hal/plugins'))
    # Publishes the events only while something subscribes. frame_id must match the optical frame
    # transform below, so it is set here and not in the parameter files
    event_camera_actions.append(Node(
        package='metavision_driver',
        executable='driver_node',
        name=DRIVER_NODE_NAME,
        namespace=namespace,
        output='screen',
        emulate_tty=True,
        parameters=[*camera['params_files'],
                    {'frame_id': f'{camera["camera_name"]}_optical_frame'}],
        remappings=[(f'{namespace}/{DRIVER_NODE_NAME}/events', f'{namespace}/events')],
    ))
    # Reads events only while something subscribes to the images, and its images carry the
    # events' frame_id
    event_camera_actions.append(Node(
        package='event_camera_renderer',
        executable='renderer_node',
        name=RENDERER_NODE_NAME,
        namespace=namespace,
        output='screen',
        emulate_tty=True,
        parameters=camera['params_files'],
        remappings=[(f'{namespace}/{RENDERER_NODE_NAME}/events', f'{namespace}/events'),
                    (f'{namespace}/{RENDERER_NODE_NAME}/image_raw', f'{namespace}/image_raw')],
    ))
    event_camera_actions.append(create_optical_frame_tf_publisher(camera['camera_name'],
                                                                  namespace))
    return event_camera_actions


def generate_launch_description():
    return LaunchDescription([
        *create_camera_launch_arguments(),
        OpaqueFunction(function=launch_setup),
    ])
