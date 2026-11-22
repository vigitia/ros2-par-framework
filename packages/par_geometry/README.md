<!-- Written by Claude Code -->

# par_geometry

Coordinate conversions of the PAR framework: camera pixels, the surface plane and projector pixels.

The package is a single module, `par_geometry/par_geometry.py`, with plain functions on NumPy arrays. It imports
nothing from `rclpy` or message packages, so it can be used in any node and tested with plain pytest. The nodes take
the inputs (intrinsics, pose, homography) from ROS messages and TF and pass them in as arrays.

```python
from par_geometry import camera_pixels_to_surface, surface_to_projector_pixels, quaternion_to_rotation_matrix
```

Dependencies: NumPy and OpenCV (`opencv-contrib-python`, pinned in `requirements.txt`).

## Coordinate systems

```
camera pixels ──camera_pixels_to_surface──► surface (metres) ──surface_to_projector_pixels──► projector pixels
              ◄──surface_to_camera_pixels──                ◄──projector_pixels_to_surface──
```

| System | Unit | Meaning |
|---|---|---|
| Camera pixels | px | Pixels of the camera's **raw** (distorted) image, as the detectors publish them. |
| Surface | m | The plane z = 0 of the `world` frame that camera and projector are aimed at, e.g. a table, wall or floor. x and y lie on the surface, z points up. In the framework, "the surface" always means this plane; other surfaces are named explicitly (an object's surface). |
| Projector pixels | px | Pixels of the image the projector shows, at the resolution in `ProjectionMapping`. |

Camera and projector are never connected directly: every conversion goes through the surface. Each device only needs
its own link to the surface, the camera through its pose and intrinsics, the projector through the homography.

Points above the surface (hands, objects) are a separate case, see [Points above the surface](#points-above-the-surface).

## Inputs and where they come from

| Argument | Shape | Source |
|---|---|---|
| `camera_matrix` | 3×3 | `camera_info.k`, reshaped: `np.reshape(camera_info.k, (3, 3))` |
| `distortion_coefficients` | 1D | `camera_info.d`: `np.array(camera_info.d)` |
| `rotation_optical_in_surface` | 3×3 | Rotation of the camera's **optical frame in the surface frame**: TF `lookup_transform('world', <optical frame>, ...)`, quaternion converted with `quaternion_to_rotation_matrix` |
| `translation_optical_in_surface_m` | 3 | Position of the optical frame in the surface frame, metres, from the same transform |
| `surface_to_projector_homography` | 3×3 | Surface → projector, from the latched `/projection_mapping` (`get_homography_from_mapping_msg`) |
| `projector_center_m` | 3 | The projector's optical centre in the surface frame, `ProjectionMapping.projector_center`, only valid when `projector_center_valid` |

`rotation_optical_in_surface` and `translation_optical_in_surface_m` are the pose of the camera in the surface, not the
other way round, as their names say. Passing the
inverted pose raises no error, the points only land in the wrong place.

Points are N×2 (pixels, surface x/y) or N×3 (surface x/y/z) arrays. Lists and single points are accepted where the
functions reshape their input (`camera_pixels_to_surface`, `surface_to_camera_pixels`, `apply_homography`, `follow_projector_rays_to_surface`,
`compute_closest_point_to_rays`).

## Functions

### Pose

**`quaternion_to_rotation_matrix(x, y, z, w)`** → 3×3 array
Rotation matrix of a unit quaternion, e.g. the `rotation` of a TF transform.

### Camera pixels ⇄ surface

**`camera_pixels_to_surface(camera_pixels, camera_matrix, distortion_coefficients, rotation_optical_in_surface, translation_optical_in_surface_m)`** → N×3 array, metres
Casts a ray from the camera through each pixel and returns where it hits the surface (z = 0). The lens distortion is
removed first (`cv2.undistortPoints`). Pixels whose ray points away from the surface or runs parallel to it are
**dropped**, so the result can be shorter than the input.

**`surface_to_camera_pixels(points_m, camera_matrix, distortion_coefficients, rotation_optical_in_surface, translation_optical_in_surface_m)`** → N×2 array, px
The inverse: where a surface point (N×2, x/y in metres, z = 0) appears in the raw camera image, with the distortion
applied (`cv2.projectPoints`). Points behind the camera are not dropped; their pixels are meaningless.

### Surface ⇄ projector pixels

**`get_homography_from_mapping_msg(projection_mapping_msg)`** → 3×3 array
The homography of a `ProjectionMapping` message (stored row-major as 9 values).

**`apply_homography(homography, points)`** → N×2 array
Maps N×2 points through any 3×3 homography (`cv2.perspectiveTransform`). An empty input gives an empty 0×2 array.

**`surface_to_projector_pixels(surface_to_projector_homography, points_m)`** → N×2 array, px
Surface points (x/y in metres) to projector pixels.

**`projector_pixels_to_surface(surface_to_projector_homography, projector_pixels)`** → N×2 array, metres
Projector pixels to surface points, with the inverse of the homography (inverted on every call).

The homography is valid for the surface plane only. It is measured by `projection_calibration.launch.py` (package `projection_calibration`) and
published latched on `/projection_mapping`; subscribe with `QoSDurabilityPolicy.TRANSIENT_LOCAL`.

### Camera pixels → projector pixels without intrinsics

**`compute_camera_to_projector_homography(projection_corners_msg, projector_width_px, projector_height_px)`** → 3×3
array
The homography from raw camera pixels directly to projector pixels, from the four corners of a `ProjectionCorners`
message (latched on `/cameras/<camera>/projection_corners`, clicked with `projection_corners.launch.py`). Needs no camera
intrinsics and no camera pose, so it works for a camera that has neither. Map points with `apply_homography`.
Valid on the surface plane only and exact at the four corners; the camera's lens distortion is not removed, so the
error is largest between the corners. Raises `ValueError` when three corners lie on one line. With intrinsics and a
pose, prefer `camera_pixels_to_surface` + `surface_to_projector_pixels`: they remove the distortion and give surface metres in between.

### Points above the surface

A point above the surface seen through the homography lands offset sideways (parallax): the projector pixel that lights
it is not the pixel of the surface point straight below it. With a depth camera and the projector's optical centre, the
correct pixel is found in three steps:

```
depth image ──depth_image_to_surface──► 3D points (surface frame) ──follow_projector_rays_to_surface──► surface points ──surface_to_projector_pixels──► projector pixels
```

**`compute_pixel_rays(camera_matrix, distortion_coefficients, width_px, height_px, stride_px=1)`** → (rows, columns, 3)
The ray direction `(x, y, 1)` in the optical frame of every `stride_px`-th camera pixel, in the shape of
`image[::stride_px, ::stride_px]`. Undistorting a whole image is slow: compute it once per `camera_info` and reuse it.

**`depth_image_to_surface(depth_m, rays, rotation_optical_in_surface, translation_optical_in_surface_m)`** → N×3 array, metres
The points of a depth image in the surface frame. `depth_m` is the depth along the optical axis in metres, sampled like
`rays`. Pixels without depth (0 or not finite) are dropped.

**`follow_projector_rays_to_surface(points_m, projector_center_m)`** → N×2 array, metres
Moves each 3D point along the line from `projector_center_m` through it down to the surface: the surface point lit by the same
projector pixel. Pass the result to `surface_to_projector_pixels`. Points at or above the centre's height are dropped.
With `projector_center_m=None` the points are projected straight down, which is only right directly below the projector.

### Calibration

**`compute_closest_point_to_rays(origins, directions)`** → (point, RMS distance in the rays' unit)
The point closest to all rays (least squares) and how far the rays pass from it. Origins and directions are N×3;
directions need not be normalised. Returns `(None, inf)` for fewer than two rays or rays that do not pin down a point,
e.g. parallel ones. `projection_calibrator` uses it to find the projector's optical centre from marker rays.

## Example: a detected pixel to projector pixels

```python
import numpy as np
from par_geometry import (get_homography_from_mapping_msg, camera_pixels_to_surface, quaternion_to_rotation_matrix,
                          surface_to_projector_pixels)

camera_matrix = np.reshape(camera_info.k, (3, 3))
distortion_coefficients = np.array(camera_info.d)

transform = tf_buffer.lookup_transform('world', camera_info.header.frame_id, Time())
q = transform.transform.rotation
t = transform.transform.translation
rotation_optical_in_surface = quaternion_to_rotation_matrix(q.x, q.y, q.z, q.w)
translation_optical_in_surface_m = np.array([t.x, t.y, t.z])

surface_points_m = camera_pixels_to_surface([[812.0, 440.0]], camera_matrix, distortion_coefficients,
                                 rotation_optical_in_surface, translation_optical_in_surface_m)
surface_to_projector_homography = get_homography_from_mapping_msg(projection_mapping_msg)
projector_pixels = surface_to_projector_pixels(surface_to_projector_homography, surface_points_m[:, :2])
```

Without calibrated intrinsics (`camera_info.k` all zeros) or without the transform, a node stays in camera pixels; see
"Calibration is optional" in the repository's `CLAUDE.md`.

## Limits

- Camera pixels are pixels of the raw image. For pixels of a rectified image (`image_rect`), pass zero distortion and
  the rectified camera matrix (the left 3×3 of `camera_info.p`), or the distortion is removed twice.
- The surface is assumed flat. Accuracy on the surface does not depend on an exact camera pose, as long as the
  projection calibration used the same pose: both steps share the same plane.
- `camera_pixels_to_surface`, `depth_image_to_surface` and `follow_projector_rays_to_surface` drop points. A caller that matches results to its inputs
  by position has to check the lengths.

## Used by

| Use | Functions | Packages |
|---|---|---|
| Camera pose from TF | `quaternion_to_rotation_matrix` | most nodes below |
| Detected point → surface | `camera_pixels_to_surface` | `gesture_detector`, `rviz_bridge`, setup wizard |
| Page → projector | `camera_pixels_to_surface`, `surface_to_projector_pixels`, `apply_homography` | `demo_app`, `rendering_manager_bridge` |
| Projector pixel → camera image | `projector_pixels_to_surface`, `surface_to_camera_pixels` | `training_images_collector` |
| Mask over hands and objects | `compute_pixel_rays`, `depth_image_to_surface`, `follow_projector_rays_to_surface`, `surface_to_projector_pixels` | `projection_mask` |
| Projector calibration | `camera_pixels_to_surface`, `projector_pixels_to_surface`, `compute_closest_point_to_rays` | `projection_calibrator` (`projection_calibration`) |
