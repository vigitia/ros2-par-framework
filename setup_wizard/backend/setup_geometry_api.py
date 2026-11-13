# Written by Claude Code
"""
Setup geometry API of the setup wizard backend: where a profile's cameras and projector are.

Everything in metres in world (the table plane is z = 0), read from the same files the launch
files use: each camera's pose (the measured camera_pose_<camera name>.yaml, else the placeholder
/<camera name>_tf_publisher in the parameter files), its unit's intrinsics for the field of view,
and the main camera's projection mapping for the projection area and the projector centre (from
another camera's mapping when the main camera's has none: only a depth camera measures it).
The app draws it as a simplified 2D picture of the setup (Overview). The math is par_geometry's,
the one place for it in the framework.

World's axes come from the pose calibration and say nothing about where people stand, so the
response also names the front: a long side of the projected image, so the drawing shows its
width. That is its bottom edge, where people read it upright, for a landscape image, and its left
edge for a portrait one (a projector turned on its side). Without a projection mapping the main
camera's image stands in for it.
"""

import os

from backend_shared_helpers import read_yaml_file
from fastapi import APIRouter
from launch import LaunchContext
import numpy as np
from par_framework_core.launch_helpers import (CAMERA_POSE_KEYS,
                                               get_extrinsics_relative_path,
                                               get_invalid_pose_keys,
                                               get_path_in_config_folder,
                                               get_unit_intrinsics_file_path,
                                               OPTICAL_FRAME_ROTATION_QUATERNION_XYZW,
                                               ProfileCamera, read_published_camera_pose)
from par_geometry.par_geometry import (pixels_to_table, projector_to_table,
                                       quaternion_to_rotation_matrix)
from profile_files import (check_profile_exists, create_profile_launch_context,
                           read_profile_cameras_or_raise)
from pydantic import BaseModel
import yaml

# Rotation of the optical frame in the camera's body frame (the child of its mount transform):
# exact for every camera type whose launch uses launch_helpers.create_optical_frame_tf_publisher
# (webcam, blackfly, event) or whose driver publishes the same rotation (e.g. the Brio's node).
# Simplification: drivers that publish their optical frames from their factory calibration (the
# depth cameras, e.g. kinect from camera_base, realsense from link) are taken with this nominal
# rotation too; their colour camera may sit a little tilted in its housing, so its optical axis
# may be off by that small angle. That angle is known only from TF while the driver runs. Upgrade:
# read the transform from TF while the camera runs and store it with the camera pose.
BODY_TO_OPTICAL_ROTATION = quaternion_to_rotation_matrix(*OPTICAL_FRAME_ROTATION_QUATERNION_XYZW)

# Points per image edge whose rays outline the field of view on the table; more than the corners,
# so lens distortion bends the outline as it does in the image.
FIELD_OF_VIEW_POINTS_PER_EDGE = 8

setup_geometry_router = APIRouter()


class CameraGeometry(BaseModel):
    # The camera's name in par_launch.cameras, as in its pose and mapping file names
    camera_name: str
    # Type and serial of its unit; serial '' when the profile names none
    camera_type: str
    serial: str
    # The first camera of par_launch.cameras, which the framework nodes use
    is_main_camera: bool
    # False: the placeholder pose from the parameter files, not a measurement
    is_pose_measured: bool
    # The camera body's position, [x, y, z]
    position_m: list[float]
    # Where the optical axis meets the table, [x, y]; None when it points away from the table
    optical_axis_table_hit_m: list[float] | None
    # The field of view's outline on the table, [[x, y], ...] around the image border; None
    # without an intrinsics file (e.g. a camera with factory intrinsics)
    table_footprint_m: list[list[float]] | None
    # The camera image's left-to-right direction on the table, a unit [x, y]; None when the camera
    # looks along the table, so its image has no direction on it
    image_right_direction: list[float] | None


class ProjectorGeometry(BaseModel):
    # The projector image's corners on the table, [[x, y], ...] clockwise from its top left
    projection_area_m: list[list[float]]
    # The projector's optical centre, [x, y, z]; None until measured with a depth camera
    center_m: list[float] | None


class SetupGeometryResponse(BaseModel):
    cameras: list[CameraGeometry]
    # None without a projection mapping of the main camera
    projector: ProjectorGeometry | None
    # Left to right as seen from the front, a unit [x, y] on the table
    front_view_right_direction: list[float]
    # What front_view_right_direction follows, for the user: e.g. 'the projected image'
    front_view_reference_text: str
    # Why a camera or the mapping is left out, e.g. a pose file edited by hand that lacks a key
    geometry_error_texts: list[str]


@setup_geometry_router.get('/api/profiles/{profile_name}/setup-geometry')
def get_setup_geometry(profile_name: str) -> SetupGeometryResponse:
    """Return where the profile's cameras and projector are, in metres in world."""
    check_profile_exists(profile_name)
    profile_launch_context = create_profile_launch_context(profile_name)
    profile_cameras = read_profile_cameras_or_raise(profile_name)
    cameras = []
    geometry_error_texts = []
    for camera_index, profile_camera in enumerate(profile_cameras):
        is_main_camera = camera_index == 0
        try:
            cameras.append(_read_camera_geometry(profile_launch_context, profile_camera,
                                                 is_main_camera))
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
            geometry_error_texts.append(f'{profile_camera.camera_name}: {error}')

    projector = None
    try:
        projector = _read_projector_geometry(profile_launch_context,
                                             profile_cameras[0].camera_name)
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        geometry_error_texts.append(f'projection mapping: {error}')
    if projector is not None and projector.center_m is None:
        projector.center_m = _read_other_camera_projector_center(
            profile_launch_context, profile_cameras[1:], geometry_error_texts)
    front_view_right_direction, front_view_reference_text = _choose_front_view_right_direction(
        projector, cameras)
    return SetupGeometryResponse(cameras=cameras, projector=projector,
                                 front_view_right_direction=front_view_right_direction,
                                 front_view_reference_text=front_view_reference_text,
                                 geometry_error_texts=geometry_error_texts)


def _choose_front_view_right_direction(projector: ProjectorGeometry | None,
                                       cameras: list[CameraGeometry]) -> tuple[list[float], str]:
    """Return left to right as seen from the front, a unit [x, y], and what it follows."""
    if projector is not None:
        top_left_m, top_right_m, bottom_right_m, bottom_left_m = np.array(
            projector.projection_area_m)
        # Both edges of a pair, since perspective tilts them a little against each other
        horizontal_edges_m = (top_right_m - top_left_m) + (bottom_right_m - bottom_left_m)
        vertical_edges_m = (bottom_left_m - top_left_m) + (bottom_right_m - top_right_m)
        right_direction = horizontal_edges_m
        # A projector on its side throws a portrait image, whose long edges run top to bottom.
        # Seen from its left edge, the image's bottom is on the right
        if np.linalg.norm(vertical_edges_m) > np.linalg.norm(horizontal_edges_m):
            right_direction = vertical_edges_m
        unit_right_direction = _normalize_table_direction(right_direction)
        if unit_right_direction is not None:
            return unit_right_direction, 'the projected image'
    for camera in cameras:
        if camera.is_main_camera and camera.image_right_direction is not None:
            return camera.image_right_direction, f'the image of {camera.camera_name}'
    return [1.0, 0.0], 'the x axis of world'


def _normalize_table_direction(direction: np.ndarray) -> list[float] | None:
    """Return the [x, y] part of a direction scaled to length 1, None when it has none."""
    table_direction = np.asarray(direction, np.float64)[:2]
    direction_length = float(np.linalg.norm(table_direction))
    if direction_length < 1e-6:
        return None
    return (table_direction / direction_length).tolist()


def _read_camera_geometry(profile_launch_context: LaunchContext, profile_camera: ProfileCamera,
                          is_main_camera: bool) -> CameraGeometry:
    """Return the camera's position, optical axis and field of view on the table."""
    camera_pose, is_pose_measured = _read_camera_pose(profile_launch_context,
                                                      profile_camera.camera_name)
    translation_m = np.array([float(camera_pose[f'translation.{axis}']) for axis in 'xyz'])
    body_rotation = quaternion_to_rotation_matrix(
        *[float(camera_pose[f'rotation.{axis}']) for axis in 'xyzw'])
    optical_rotation = body_rotation @ BODY_TO_OPTICAL_ROTATION

    optical_axis_direction = optical_rotation[:, 2]
    optical_axis_table_hit_m = None
    # The axis reaches z = 0 at translation.z + ray_scale * direction.z = 0, ahead of the camera
    if optical_axis_direction[2] < 0:
        ray_scale = -translation_m[2] / optical_axis_direction[2]
        axis_hit_m = translation_m + ray_scale * optical_axis_direction
        optical_axis_table_hit_m = [float(axis_hit_m[0]), float(axis_hit_m[1])]

    table_footprint_m = None
    camera_info = _read_camera_info(profile_launch_context, profile_camera)
    if camera_info is not None:
        camera_matrix, distortion_coefficients, image_width_px, image_height_px = camera_info
        border_pixels = _create_image_border_pixels(image_width_px, image_height_px)
        footprint_points_m = pixels_to_table(border_pixels, camera_matrix,
                                             distortion_coefficients, optical_rotation,
                                             translation_m)
        if len(footprint_points_m) > 0:
            table_footprint_m = footprint_points_m[:, :2].tolist()

    # The optical frame's x axis runs along the image rows, left to right
    image_right_direction = _normalize_table_direction(optical_rotation[:, 0])
    return CameraGeometry(camera_name=profile_camera.camera_name,
                          camera_type=profile_camera.camera_type, serial=profile_camera.serial,
                          is_main_camera=is_main_camera,
                          is_pose_measured=is_pose_measured, position_m=translation_m.tolist(),
                          optical_axis_table_hit_m=optical_axis_table_hit_m,
                          table_footprint_m=table_footprint_m,
                          image_right_direction=image_right_direction)


def _read_camera_pose(profile_launch_context: LaunchContext,
                      camera_name: str) -> tuple[dict, bool]:
    """Return the pose the launch would publish and whether it is measured, as (pose, bool)."""
    camera_pose, pose_source_text, is_pose_measured = read_published_camera_pose(
        profile_launch_context, camera_name)
    invalid_pose_keys = get_invalid_pose_keys(camera_pose)
    if invalid_pose_keys:
        raise ValueError(f'{pose_source_text} has no finite number for '
                         f'{", ".join(invalid_pose_keys)}')
    pose_by_key = {}
    for pose_key in CAMERA_POSE_KEYS:
        pose_by_key[pose_key] = camera_pose[pose_key]
    return pose_by_key, is_pose_measured


def _read_camera_info(profile_launch_context: LaunchContext, profile_camera: ProfileCamera):
    """
    Return the unit's intrinsics from its file in the profile, None without one.

    As (camera matrix, distortion coefficients, image width px, image height px), read from the
    file the driver loads (camera_calibration's YAML format).
    """
    intrinsics_path = get_unit_intrinsics_file_path(profile_launch_context,
                                                    profile_camera.camera_type,
                                                    profile_camera.serial)
    if not os.path.exists(intrinsics_path):
        return None
    camera_info = read_yaml_file(intrinsics_path)
    camera_matrix = np.array(camera_info['camera_matrix']['data'], np.float64).reshape(3, 3)
    distortion_coefficients = np.array(camera_info['distortion_coefficients']['data'],
                                       np.float64)
    image_width_px = int(camera_info['image_width'])
    image_height_px = int(camera_info['image_height'])
    return camera_matrix, distortion_coefficients, image_width_px, image_height_px


def _create_image_border_pixels(image_width_px: int, image_height_px: int) -> np.ndarray:
    """Return pixels along the image border, clockwise from the top left corner, as Nx2."""
    edge_steps = np.linspace(0.0, 1.0, FIELD_OF_VIEW_POINTS_PER_EDGE, endpoint=False)
    right_px = image_width_px - 1
    bottom_px = image_height_px - 1
    border_pixels = []
    for edge_step in edge_steps:
        border_pixels.append([edge_step * right_px, 0.0])
    for edge_step in edge_steps:
        border_pixels.append([right_px, edge_step * bottom_px])
    for edge_step in edge_steps:
        border_pixels.append([(1.0 - edge_step) * right_px, bottom_px])
    for edge_step in edge_steps:
        border_pixels.append([0.0, (1.0 - edge_step) * bottom_px])
    return np.array(border_pixels, np.float64)


def _read_other_camera_projector_center(profile_launch_context: LaunchContext,
                                        other_profile_cameras: list,
                                        geometry_error_texts: list[str]) -> list[float] | None:
    """
    Return the projector centre from the first of the cameras whose mapping has one, else None.

    Only a depth camera measures the centre, and it need not be the main camera. The centre is
    taken as it is, in world: it lines up with the main camera's projection area once both
    cameras' projection calibrations ran with a measured pose, which puts both into the projected
    image's world (projection_calibrator, camera_pose_file).
    """
    for other_profile_camera in other_profile_cameras:
        try:
            other_projector = _read_projector_geometry(profile_launch_context,
                                                       other_profile_camera.camera_name)
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
            geometry_error_texts.append(
                f'projection mapping of {other_profile_camera.camera_name}: {error}')
            continue
        if other_projector is not None and other_projector.center_m is not None:
            return other_projector.center_m
    return None


def _read_projector_geometry(profile_launch_context: LaunchContext,
                             camera_name: str) -> ProjectorGeometry | None:
    """Return the projection area and projector centre from the camera's projection mapping."""
    mapping_path = get_path_in_config_folder(get_extrinsics_relative_path(
        profile_launch_context, 'projection_mapping', camera_name))
    if not os.path.exists(mapping_path):
        return None
    projection_mapping = read_yaml_file(mapping_path)
    homography = np.array(projection_mapping['homography'], np.float64).reshape(3, 3)
    projector_width_px = float(projection_mapping['projector_width'])
    projector_height_px = float(projection_mapping['projector_height'])
    projector_corner_pixels = [[0.0, 0.0], [projector_width_px, 0.0],
                               [projector_width_px, projector_height_px],
                               [0.0, projector_height_px]]
    projection_area_m = projector_to_table(homography, projector_corner_pixels)

    center_m = None
    stored_center_m = projection_mapping.get('projector_center')
    if stored_center_m is not None:
        center_m = [float(coordinate_m) for coordinate_m in stored_center_m]
    return ProjectorGeometry(projection_area_m=projection_area_m.tolist(), center_m=center_m)
