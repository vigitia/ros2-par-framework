# Written by Claude Code
"""
Coordinate conversions of the PAR framework, free of ROS plumbing.

camera pixels --camera_pixels_to_surface--> surface (metres, z = 0 of world)
--surface_to_projector_pixels--> projector pixels, and back with projector_pixels_to_surface and
surface_to_camera_pixels. Above the surface: a depth image --depth_image_to_surface--> surface
frame points
--follow_projector_rays_to_surface--> the surface points lit by the same projector pixels, given
the projector's optical centre (found with compute_closest_point_to_rays).
"""

import itertools

import cv2
import numpy as np

# The corner fields of a ProjectionCorners message, clockwise from the projector image's top left
PROJECTION_CORNER_NAMES = ('top_left', 'top_right', 'bottom_right', 'bottom_left')
# Three projection corners spanning less than this lie on one line for
# compute_camera_to_projector_homography: no plane-to-plane mapping goes through them
MIN_CORNER_TRIANGLE_AREA_PX2 = 1.0


def quaternion_to_rotation_matrix(x, y, z, w):
    """
    Return the 3x3 rotation matrix of the quaternion (x, y, z, w).

    The quaternion is normalized first, so values rounded in a YAML file or a parameter still give
    a proper rotation.
    """
    quaternion_length = np.linalg.norm((x, y, z, w))
    x, y, z, w = np.array((x, y, z, w), np.float64) / quaternion_length
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def camera_pixels_to_surface(camera_pixels, camera_matrix, distortion_coefficients,
                             rotation_optical_in_surface, translation_optical_in_surface_m):
    """
    Intersect the rays of raw camera image pixels with the plane z = 0 of the surface frame.

    rotation_optical_in_surface and translation_optical_in_surface_m are the pose of the optical
    frame in the surface frame. Returns the hits as an Nx3 array in metres, dropping pixels whose
    ray misses the surface.
    """
    distorted_pixels = np.asarray(camera_pixels, np.float64).reshape(-1, 1, 2)
    # Distortion removed: each pixel becomes the direction (x, y, 1) of its ray in the optical
    # frame
    normalized_points = cv2.undistortPoints(distorted_pixels, camera_matrix,
                                            distortion_coefficients).reshape(-1, 2)
    optical_rays = np.column_stack([normalized_points, np.ones(len(normalized_points))])
    surface_rays = optical_rays @ rotation_optical_in_surface.T
    # Every ray starts at the camera: camera height + ray_scale * ray.z = 0
    with np.errstate(divide='ignore'):
        ray_scales = -translation_optical_in_surface_m[2] / surface_rays[:, 2]
    surface_hits_m = translation_optical_in_surface_m + ray_scales[:, None] * surface_rays
    # ray_scale <= 0: the ray points away from the surface; not finite: it runs parallel to it
    is_ray_hitting_surface = np.isfinite(ray_scales) & (ray_scales > 0)
    return surface_hits_m[is_ray_hitting_surface]


def surface_to_camera_pixels(points_m, camera_matrix, distortion_coefficients,
                             rotation_optical_in_surface, translation_optical_in_surface_m):
    """
    Map Nx2 surface points (x, y in metres, z = 0) to pixels of the raw camera image.

    The inverse of camera_pixels_to_surface.

    rotation_optical_in_surface and translation_optical_in_surface_m are the pose of the optical
    frame in the surface frame, as for camera_pixels_to_surface. Returns an Nx2 array with the
    camera's distortion applied. Points behind the camera are not dropped; they give meaningless
    pixels.
    """
    points_m = np.asarray(points_m, np.float64).reshape(-1, 2)
    surface_points_m = np.column_stack([points_m, np.zeros(len(points_m))])
    # Pose of the surface frame in the optical frame: the inverse of the optical frame's pose
    rotation_surface_to_optical = rotation_optical_in_surface.T
    translation_surface_to_optical_m = (-rotation_optical_in_surface.T
                                        @ translation_optical_in_surface_m)
    rotation_vector, _ = cv2.Rodrigues(rotation_surface_to_optical)
    pixels, _ = cv2.projectPoints(surface_points_m, rotation_vector,
                                  translation_surface_to_optical_m, camera_matrix,
                                  distortion_coefficients)
    return pixels.reshape(-1, 2)


def apply_homography(homography, points):
    """Map Nx2 points through the 3x3 homography and return them as an Nx2 array."""
    points = np.asarray(points, np.float64).reshape(-1, 1, 2)
    if len(points) == 0:
        return np.empty((0, 2))
    homography = np.asarray(homography, np.float64)
    return cv2.perspectiveTransform(points, homography).reshape(-1, 2)


def get_homography_from_mapping_msg(projection_mapping_msg):
    """Return the surface-to-projector homography of a ProjectionMapping message as 3x3 array."""
    return np.reshape(projection_mapping_msg.homography, (3, 3))


def compute_camera_to_projector_homography(projection_corners_msg, projector_width_px,
                                           projector_height_px):
    """
    Return the 3x3 homography from raw camera pixels to projector pixels, from four corners.

    projection_corners_msg: a ProjectionCorners message, the projector image's corners in camera
    pixels (top_left must be the projector image's top left, as projection_corner_selector stores
    them).
    Needs no camera intrinsics or pose, so it works without any other calibration. Valid for
    points on the surface plane only, exact at the four corners; the camera's lens distortion is
    not removed, so points between the corners are off by the distortion there. Raises ValueError
    when the corners give no homography (three of them on one line).
    """
    corner_pixels = []
    for corner_name in PROJECTION_CORNER_NAMES:
        corner_point = getattr(projection_corners_msg, corner_name)
        corner_pixels.append([corner_point.x, corner_point.y])
    corner_pixels = np.array(corner_pixels, np.float64)
    # findHomography does not reject such corners itself: it returns a matrix that maps points
    # to infinity
    for first_index, second_index, third_index in itertools.combinations(range(4), 3):
        first_edge_px = corner_pixels[second_index] - corner_pixels[first_index]
        second_edge_px = corner_pixels[third_index] - corner_pixels[first_index]
        # The 2D cross product, written out: np.cross takes 3D vectors only
        edges_cross_product_px2 = (first_edge_px[0] * second_edge_px[1]
                                   - first_edge_px[1] * second_edge_px[0])
        triangle_area_px2 = abs(edges_cross_product_px2) / 2
        if triangle_area_px2 < MIN_CORNER_TRIANGLE_AREA_PX2:
            raise ValueError('the projection corners give no homography, three of them lie on '
                             'one line')
    projector_corner_pixels = np.array([[0.0, 0.0],
                                        [projector_width_px, 0.0],
                                        [projector_width_px, projector_height_px],
                                        [0.0, projector_height_px]])
    # Four points, no outliers to reject: method 0 fits them exactly
    homography, _ = cv2.findHomography(corner_pixels, projector_corner_pixels, 0)
    if homography is None:
        raise ValueError('the projection corners give no homography')
    return homography / homography[2, 2]


def surface_to_projector_pixels(surface_to_projector_homography, points_m):
    """Map Nx2 surface points (x, y in metres) to projector pixels with the homography."""
    return apply_homography(surface_to_projector_homography, points_m)


def projector_pixels_to_surface(surface_to_projector_homography, projector_pixels):
    """Map Nx2 projector pixels to surface points (x, y in metres): the inverse homography."""
    return apply_homography(np.linalg.inv(surface_to_projector_homography), projector_pixels)


def compute_pixel_rays(camera_matrix, distortion_coefficients, width_px, height_px, stride_px=1):
    """
    Return the ray direction (x, y, 1) in the optical frame of every stride_px-th camera pixel.

    The result has the shape (rows, columns, 3) of image[::stride_px, ::stride_px], so it lines
    up with a depth image sampled the same way. Undistorting is slow, so compute it once per
    camera_info.
    """
    pixel_columns, pixel_rows = np.meshgrid(np.arange(0, width_px, stride_px),
                                            np.arange(0, height_px, stride_px))
    grid_shape = pixel_columns.shape
    pixels = np.column_stack([pixel_columns.ravel(), pixel_rows.ravel()])
    pixels = pixels.astype(np.float64).reshape(-1, 1, 2)
    normalized_points = cv2.undistortPoints(pixels, camera_matrix, distortion_coefficients)
    normalized_points = normalized_points.reshape(grid_shape + (2,))
    return np.concatenate([normalized_points, np.ones(grid_shape + (1,))], axis=2)


def depth_image_to_surface(depth_m, rays, rotation_optical_in_surface,
                           translation_optical_in_surface_m):
    """
    Return the points of a depth image as an Nx3 array in the surface frame, in metres.

    depth_m is the depth along the optical axis, sampled like rays (see compute_pixel_rays);
    rotation_optical_in_surface and translation_optical_in_surface_m are the pose of the optical
    frame in the surface frame. Pixels
    without depth (0 or not finite) are dropped.
    """
    has_depth = np.isfinite(depth_m) & (depth_m > 0)
    optical_points_m = rays[has_depth] * depth_m[has_depth][:, None]
    return optical_points_m @ rotation_optical_in_surface.T + translation_optical_in_surface_m


def follow_projector_rays_to_surface(points_m, projector_center_m):
    """
    Move Nx3 surface-frame points along the projector's rays onto z = 0 and return them as Nx2.

    With projector_center_m the projector's optical centre, a point above the surface maps to the
    surface point lit by the same projector pixel, so surface_to_projector_pixels then gives that
    pixel. Points at or above the centre's height are lit by no pixel and are dropped.
    projector_center_m None projects straight down instead, which is only right directly below the
    projector.
    """
    points_m = np.asarray(points_m, np.float64).reshape(-1, 3)
    if projector_center_m is None:
        return points_m[:, :2]
    projector_center_m = np.asarray(projector_center_m, np.float64)
    points_m = points_m[points_m[:, 2] < projector_center_m[2]]
    # Along the ray center + ray_scale * (point - center), z reaches 0 at
    # ray_scale = c_z / (c_z - p_z)
    ray_scales = projector_center_m[2] / (projector_center_m[2] - points_m[:, 2])
    surface_points_m = projector_center_m + ray_scales[:, None] * (points_m - projector_center_m)
    return surface_points_m[:, :2]


def compute_closest_point_to_rays(origins, directions):
    """
    Return the point closest to all rays and the RMS distance of the rays from it.

    origins and directions are Nx3, one ray per row; the directions need not be normalised.
    Returns (None, inf) if the rays do not pin down one point, e.g. when they are all parallel.
    """
    origins = np.asarray(origins, np.float64).reshape(-1, 3)
    directions = np.asarray(directions, np.float64).reshape(-1, 3)
    directions = directions / np.linalg.norm(directions, axis=1, keepdims=True)
    # (I - d d^T) removes the part along the ray: what is left is the offset perpendicular to it.
    # The sum of the squared perpendicular offsets is smallest where sum(P) c = sum(P o)
    perpendicular_projection_matrices = np.eye(3) - directions[:, :, None] * directions[:, None, :]
    perpendicular_sum = perpendicular_projection_matrices.sum(axis=0)
    if len(origins) < 2 or np.linalg.matrix_rank(perpendicular_sum) < 3:
        return None, np.inf
    projected_origins = perpendicular_projection_matrices @ origins[:, :, None]
    projected_origins_sum = projected_origins.sum(axis=0).ravel()
    closest_point = np.linalg.solve(perpendicular_sum, projected_origins_sum)
    offsets = (perpendicular_projection_matrices @ (closest_point - origins)[:, :, None])[:, :, 0]
    squared_distances = np.sum(offsets ** 2, axis=1)
    rms_distance = float(np.sqrt(np.mean(squared_distances)))
    return closest_point, rms_distance
