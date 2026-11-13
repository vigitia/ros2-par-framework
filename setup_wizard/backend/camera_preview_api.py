# Written by Claude Code
"""
Camera preview API of the setup wizard backend: starts one camera, serves its feeds and settings.

The camera runs as the backend's camera launch (camera_launch_session.py), started here as
`ros2 launch par_framework_core par.launch.py camera:=<camera> camera_only:=true`. Everything else
is generic, so any driver that follows the ROS 2 conventions works without code here:
- The driver node is the node that publishes the camera's image_raw.
- Its feeds are all sensor_msgs/Image topics that node publishes (e.g. colour, depth and infrared
  of a depth camera). The backend's ROS node subscribes to a feed once the app asks for it and
  keeps only the latest frame, which the app fetches as JPEG.
- Its settings are its parameters, read and changed through the ROS 2 parameter services
  (node_parameters.py), except those ROS 2 itself adds to every node and image publisher.
The router's lifespan starts and stops the backend's ROS node and the camera launch session.
"""

from backend_ros_node import CAMERA_IMAGE_STREAM_NAME
from camera_launch_session import (check_camera_process_runs, create_profile_preview_camera,
                                   create_unit_preview_camera, find_own_camera_driver_node_name,
                                   get_camera_launch_session, get_driver_parameter_client,
                                   get_preview_topic_name, run_ros_for_camera_launches,
                                   start_camera_launch, stop_camera_launch)
import cv2
from fastapi import APIRouter, HTTPException, Response
from image_conversion import convert_image_message_to_frame
from node_parameters import (convert_parameter_value_to_plain_python, convert_setting_value,
                             NodeSetting, read_node_settings, wait_for_service_answer)
from profile_files import read_par_setup_node_settings, write_node_settings_into_profile
from pydantic import BaseModel
from rclpy.exceptions import InvalidTopicNameException
from rclpy.node import NodeNameNonExistentError
from rclpy.parameter import Parameter
from rclpy.validate_topic_name import validate_topic_name

# The app shows the preview small; a smaller JPEG also keeps the polling cheap.
PREVIEW_MAXIMUM_WIDTH_PX = 960
PREVIEW_JPEG_QUALITY_PERCENT = 80
# The preview's launch file in par_framework_core, started with camera_only:=true
CAMERA_PREVIEW_LAUNCH_FILE_NAME = 'par.launch.py'

camera_preview_router = APIRouter(lifespan=run_ros_for_camera_launches)


class CameraSettingsResponse(BaseModel):
    camera_name: str
    settings: list[NodeSetting]
    # Where changes can be saved; None while the camera runs without a saved profile
    profile_name: str | None
    unsaved_setting_names: list[str]


class CameraSettingsSaveResponse(BaseModel):
    profile_name: str
    node_section_name: str
    written_setting_names: list[str]
    removed_setting_names: list[str]


class CameraSettingChangeRequest(BaseModel):
    setting_name: str
    # Converted to the parameter's current type; the driver decides whether it accepts the value
    setting_value: bool | int | float | str | list


class CameraFeed(BaseModel):
    topic_name: str


class CameraFeedsResponse(BaseModel):
    feeds: list[CameraFeed]


class CameraPreviewStartRequest(BaseModel):
    # Starts the camera with this saved profile's settings; None uses par_setup.yaml's, e.g. for a
    # profile that is not saved yet.
    profile_name: str | None = None
    # A camera of the profile, by its name in par_launch.cameras; needs profile_name
    camera_name: str = ''
    # Instead of camera_name: a unit no profile names yet, of an installed camera type, and its
    # serial ('' opens the unit the driver finds first)
    camera_type: str = ''
    serial: str = ''


class CameraPreviewStartResponse(BaseModel):
    # Names this preview in its stop request
    preview_id: int


class CameraPreviewStopRequest(BaseModel):
    # Stop only while this preview runs. A screen closing after a newer screen started a preview,
    # even of the same camera, must not end that one. None stops whatever runs.
    preview_id: int | None = None


@camera_preview_router.post('/api/camera-preview/start')
def start_camera_preview(request: CameraPreviewStartRequest) -> CameraPreviewStartResponse:
    """Start the camera for the preview, stopping the camera of an earlier preview first."""
    if request.camera_name:
        if request.profile_name is None:
            raise HTTPException(status_code=422,
                                detail='camera_name names a camera of a profile: send '
                                       'profile_name too, or camera_type for a unit')
        preview_camera = create_profile_preview_camera(request.profile_name, request.camera_name)
    else:
        preview_camera = create_unit_preview_camera(request.camera_type, request.serial)
    preview_id = start_camera_launch(preview_camera, request.profile_name,
                                     CAMERA_PREVIEW_LAUNCH_FILE_NAME, ['camera_only:=true'])
    return CameraPreviewStartResponse(preview_id=preview_id)


@camera_preview_router.post('/api/camera-preview/stop')
def stop_camera_preview(request: CameraPreviewStopRequest) -> None:
    """Stop the preview's camera; a stop naming another preview than the running one is ignored."""
    stop_camera_launch(request.preview_id)


@camera_preview_router.get('/api/camera-preview/feeds')
def get_camera_preview_feeds() -> CameraFeedsResponse:
    """List the previewed camera's image topics; 503 while its driver node is not up yet."""
    session = get_camera_launch_session()
    with session.session_lock:
        check_camera_process_runs(session)
        # Waiting for a starting camera counts as watching: ROS may report its node seconds after
        # the driver runs, and the watchdog must not stop it before the first frame is asked for
        session.record_preview_request()
        driver_node_name = find_own_camera_driver_node_name(session)
    try:
        feed_topic_names = session.preview_ros_node.list_feed_topic_names(driver_node_name)
    except NodeNameNonExistentError as error:
        # The node has left the graph meanwhile, e.g. the camera just stopped
        raise HTTPException(status_code=503,
                            detail=f'Cannot list the topics of {driver_node_name}: {error}'
                            ) from error
    feeds = []
    for feed_topic_name in feed_topic_names:
        feeds.append(CameraFeed(topic_name=feed_topic_name))
    return CameraFeedsResponse(feeds=feeds)


@camera_preview_router.get('/api/camera-preview/frame')
def get_camera_preview_frame(topic_name: str = '') -> Response:
    """Return a feed's latest frame as JPEG, '' the camera's image; 204 before the first one."""
    session = get_camera_launch_session()
    with session.session_lock:
        check_camera_process_runs(session)
        if not topic_name:
            topic_name = get_preview_topic_name(session, CAMERA_IMAGE_STREAM_NAME)
    # Comes from the network and ends up in a subscription: must be a valid ROS topic name
    try:
        validate_topic_name(topic_name)
    except InvalidTopicNameException as error:
        raise HTTPException(status_code=400, detail=f'Not a topic name: {error}') from error
    with session.session_lock:
        check_camera_process_runs(session)
        session.record_preview_request()
        session.preview_ros_node.subscribe_to_feed(topic_name)
    image_message = session.preview_ros_node.get_latest_image_message(topic_name)
    if image_message is None:
        return Response(status_code=204)
    preview_frame = _convert_image_message_to_preview_frame(image_message)
    if preview_frame is None:
        raise HTTPException(status_code=409,
                            detail=f'{topic_name} has the encoding {image_message.encoding!r}, '
                                   f'which the preview cannot show')
    jpeg_quality = [cv2.IMWRITE_JPEG_QUALITY, PREVIEW_JPEG_QUALITY_PERCENT]
    is_encoded, jpeg_bytes = cv2.imencode('.jpg', preview_frame, jpeg_quality)
    if not is_encoded:
        raise HTTPException(status_code=500, detail='Could not encode the frame as JPEG')
    return Response(content=jpeg_bytes.tobytes(), media_type='image/jpeg')


@camera_preview_router.get('/api/camera-preview/settings')
def get_camera_preview_settings() -> CameraSettingsResponse:
    """Return the previewed camera's settings, read live from its driver node."""
    session = get_camera_launch_session()
    driver_node_name, parameter_client = get_driver_parameter_client(session)
    settings = read_node_settings(parameter_client)
    # Simplification: a driver setting par_setup.yaml does not list gets no default, since the
    # driver's own value is not known while it runs with the profile. Upgrade: read the driver once
    # without a profile, as node_settings_api.py does for sensor nodes.
    par_setup_value_by_name = read_par_setup_node_settings(driver_node_name)
    for node_setting in settings:
        if node_setting.setting_name in par_setup_value_by_name:
            node_setting.has_default_value = True
            node_setting.default_value = par_setup_value_by_name[node_setting.setting_name]
    with session.session_lock:
        profile_name = session.profile_name
        unsaved_setting_names = sorted(session.unsaved_setting_value_by_name)
        preview_camera = session.preview_camera
    camera_name = ''
    if preview_camera is not None:
        camera_name = preview_camera.camera_name
    return CameraSettingsResponse(camera_name=camera_name, settings=settings,
                                  profile_name=profile_name,
                                  unsaved_setting_names=unsaved_setting_names)


@camera_preview_router.put('/api/camera-preview/settings')
def change_camera_preview_setting(request: CameraSettingChangeRequest) -> None:
    """Set one setting on the running driver; 409 with the driver's reason when it refuses."""
    session = get_camera_launch_session()
    with session.session_lock:
        changed_preview_id = session.running_preview_id
    driver_node_name, parameter_client = get_driver_parameter_client(session)
    current_parameter_values = wait_for_service_answer(
        parameter_client.get_parameters([request.setting_name])).values
    if not current_parameter_values:
        raise HTTPException(status_code=404,
                            detail=f'{driver_node_name} has no setting {request.setting_name!r}')
    parameter_type = Parameter.Type(current_parameter_values[0].type)
    parameter_value = convert_setting_value(request.setting_value, parameter_type)
    parameter = Parameter(request.setting_name, parameter_type, parameter_value)
    set_results = wait_for_service_answer(
        parameter_client.set_parameters([parameter])).results
    if not set_results[0].successful:
        refusal_reason = set_results[0].reason or 'no reason given'
        raise HTTPException(status_code=409,
                            detail=f'{driver_node_name} refused {request.setting_name} = '
                                   f'{parameter_value!r}: {refusal_reason}')
    with session.session_lock:
        # A camera restarted meanwhile has new settings, which this change is not part of
        if session.running_preview_id == changed_preview_id:
            # The value as the driver accepted it, in the parameter's own type (e.g. 5.0 for a
            # double), so ROS accepts it from the profile at the next start
            session.unsaved_setting_value_by_name[request.setting_name] = (
                convert_parameter_value_to_plain_python(parameter.get_parameter_value()))
            session.unsaved_settings_node_name = driver_node_name


@camera_preview_router.post('/api/camera-preview/settings/save-to-profile')
def save_camera_preview_settings_to_profile() -> CameraSettingsSaveResponse:
    """Write the settings changed on the running driver into the profile it was started with."""
    session = get_camera_launch_session()
    with session.session_lock:
        check_camera_process_runs(session)
        profile_name = session.profile_name
        preview_id = session.running_preview_id
        driver_node_name = session.unsaved_settings_node_name
        setting_value_by_name = dict(session.unsaved_setting_value_by_name)
    if profile_name is None:
        raise HTTPException(status_code=409,
                            detail='The camera runs without a saved profile; the new-profile '
                                   'wizard saves its changes when the profile is created')
    if not setting_value_by_name:
        return CameraSettingsSaveResponse(profile_name=profile_name, node_section_name='',
                                          written_setting_names=[], removed_setting_names=[])
    # Simplification: a setting the launch file sets itself after the parameter files (e.g. a
    # camera's camera_info_url) is saved too, but the launch value wins at the next start.
    # Upgrade: mark such settings read-only in the drivers, or compare with the launch's values.
    write_result = write_node_settings_into_profile(profile_name, driver_node_name,
                                                    setting_value_by_name)
    with session.session_lock:
        if session.running_preview_id == preview_id:
            for setting_name in setting_value_by_name:
                session.unsaved_setting_value_by_name.pop(setting_name, None)
    return CameraSettingsSaveResponse(profile_name=profile_name,
                                      node_section_name=write_result.node_section_name,
                                      written_setting_names=write_result.written_setting_names,
                                      removed_setting_names=write_result.removed_setting_names)


@camera_preview_router.delete('/api/camera-preview/new-profile-settings')
def discard_new_profile_settings() -> None:
    """Forget setting changes kept for a new profile, e.g. when the new-profile wizard starts."""
    session = get_camera_launch_session()
    with session.session_lock:
        session.new_profile_setting_values_by_unit = {}
        if session.profile_name is None:
            session.unsaved_setting_value_by_name = {}


def _convert_image_message_to_preview_frame(image_message):
    """Return the frame as a uint8 array for OpenCV (gray or BGR), scaled down for the preview."""
    frame = convert_image_message_to_frame(image_message)
    if frame is None:
        return None

    frame_width_px = image_message.width
    if frame_width_px <= PREVIEW_MAXIMUM_WIDTH_PX:
        return frame
    scale_factor = PREVIEW_MAXIMUM_WIDTH_PX / frame_width_px
    preview_height_px = max(1, round(image_message.height * scale_factor))
    return cv2.resize(frame, (PREVIEW_MAXIMUM_WIDTH_PX, preview_height_px),
                      interpolation=cv2.INTER_AREA)
