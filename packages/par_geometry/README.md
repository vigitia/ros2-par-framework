<!-- Written by Claude Code -->

# par_geometry

Coordinate conversions of the PAR framework: camera pixels, the table plane and projector pixels.

The package is a single module, `par_geometry/par_geometry.py`, with plain functions on NumPy arrays. It imports
nothing from `rclpy` or message packages, so it can be used in any node and tested with plain pytest. The nodes take
the inputs (intrinsics, pose, homography) from ROS messages and TF and pass them in as arrays.

```python
from par_geometry import pixels_to_table, table_to_projector, quaternion_to_rotation_matrix
```

Dependencies: NumPy and OpenCV (`opencv-contrib-python`, pinned in `requirements.txt`).

## Coordinate systems

```
camera pixels ──pixels_to_table──► table (metres) ──table_to_projector──► projector pixels
              ◄──table_to_pixels──                ◄──projector_to_table──
```

| System | Unit | Meaning |
|---|---|---|
| Camera pixels | px | Pixels of the camera's **raw** (distorted) image, as the detectors publish them. |
| Table | m | The plane z = 0 of the `world` frame. x and y lie on the table, z points up. |
| Projector pixels | px | Pixels of the image the projector shows, at the resolution in `ProjectionMapping`. |

Camera and projector are never connected directly: every conversion goes through the table. Each device only needs
its own link to the table, the camera through its pose and intrinsics, the projector through the homography.

Points above the table (hands, objects) are a separate case, see [Points above the table](#points-above-the-table).

## Inputs and where they come from

| Argument | Shape | Source |
|---|---|---|
| `camera_matrix` | 3×3 | `camera_info.k`, reshaped: `np.reshape(camera_info.k, (3, 3))` |
| `distortion_coefficients` | 1D | `camera_info.d`: `np.array(camera_info.d)` |
| `rotation_optical_in_table` | 3×3 | Rotation of the camera's **optical frame in the table frame**: TF `lookup_transform('world', <optical frame>, ...)`, quaternion converted with `quaternion_to_rotation_matrix` |
| `translation_optical_in_table_m` | 3 | Position of the optical frame in the table frame, metres, from the same transform |
| `table_to_projector_homography` | 3×3 | Table → projector, from the latched `/projection_mapping` (`get_homography_from_mapping_msg`) |
| `center_m` | 3 | The projector's optical centre in the table frame, `ProjectionMapping.projector_center`, only valid when `projector_center_valid` |

`rotation_optical_in_table` and `translation_optical_in_table_m` are the pose of the camera in the table, not the
other way round, as their names say. Passing the
inverted pose raises no error, the points only land in the wrong place.

Points are N×2 (pixels, table x/y) or N×3 (table x/y/z) arrays. Lists and single points are accepted where the
functions reshape their input (`pixels_to_table`, `table_to_pixels`, `apply_homography`, `project_to_table`,
`compute_closest_point_to_rays`).

## Functions

### Pose

**`quaternion_to_rotation_matrix(x, y, z, w)`** → 3×3 array
Rotation matrix of a unit quaternion, e.g. the `rotation` of a TF transform.

### Camera pixels ⇄ table

**`pixels_to_table(camera_pixels, camera_matrix, distortion_coefficients, rotation_optical_in_table, translation_optical_in_table_m)`** → N×3 array, metres
Casts a ray from the camera through each pixel and returns where it hits the table (z = 0). The lens distortion is
removed first (`cv2.undistortPoints`). Pixels whose ray points away from the table or runs parallel to it are
**dropped**, so the result can be shorter than the input.

**`table_to_pixels(points_m, camera_matrix, distortion_coefficients, rotation_optical_in_table, translation_optical_in_table_m)`** → N×2 array, px
The inverse: where a table point (N×2, x/y in metres, z = 0) appears in the raw camera image, with the distortion
applied (`cv2.projectPoints`). Points behind the camera are not dropped; their pixels are meaningless.

### Table ⇄ projector pixels

**`get_homography_from_mapping_msg(projection_mapping_msg)`** → 3×3 array
The homography of a `ProjectionMapping` message (stored row-major as 9 values).

**`apply_homography(homography, points)`** → N×2 array
Maps N×2 points through any 3×3 homography (`cv2.perspectiveTransform`). An empty input gives an empty 0×2 array.

**`table_to_projector(table_to_projector_homography, points_m)`** → N×2 array, px
Table points (x/y in metres) to projector pixels.

**`projector_to_table(table_to_projector_homography, projector_pixels)`** → N×2 array, metres
Projector pixels to table points, with the inverse of the homography (inverted on every call).

The homography is valid for the table plane only. It is measured by `projection_calibration.launch.py` and
published latched on `/projection_mapping`; subscribe with `QoSDurabilityPolicy.TRANSIENT_LOCAL`.

### Camera pixels → projector pixels without intrinsics

**`compute_camera_to_projector_homography(projection_corners_msg, projector_width_px, projector_height_px)`** → 3×3
array
The homography from raw camera pixels directly to projector pixels, from the four corners of a `ProjectionCorners`
message (latched on `/cameras/<camera>/projection_corners`, clicked with `calibration.launch.py`). Needs no camera
intrinsics and no camera pose, so it works for a camera that has neither. Map points with `apply_homography`.
Valid on the table plane only and exact at the four corners; the camera's lens distortion is not removed, so the
error is largest between the corners. Raises `ValueError` when three corners lie on one line. With intrinsics and a
pose, prefer `pixels_to_table` + `table_to_projector`: they remove the distortion and give table metres in between.

### Points above the table

A point above the table seen through the homography lands offset sideways (parallax): the projector pixel that lights
it is not the pixel of the table point straight below it. With a depth camera and the projector's optical centre, the
correct pixel is found in three steps:

```
depth image ──depth_to_table──► 3D points (table frame) ──project_to_table──► table points ──table_to_projector──► projector pixels
```

**`compute_pixel_rays(camera_matrix, distortion_coefficients, width_px, height_px, stride_px=1)`** → (rows, columns, 3)
The ray direction `(x, y, 1)` in the optical frame of every `stride_px`-th camera pixel, in the shape of
`image[::stride_px, ::stride_px]`. Undistorting a whole image is slow: compute it once per `camera_info` and reuse it.

**`depth_to_table(depth_m, rays, rotation_optical_in_table, translation_optical_in_table_m)`** → N×3 array, metres
The points of a depth image in the table frame. `depth_m` is the depth along the optical axis in metres, sampled like
`rays`. Pixels without depth (0 or not finite) are dropped.

**`project_to_table(points_m, center_m)`** → N×2 array, metres
Moves each 3D point along the line from `center_m` through it down to the table: the table point lit by the same
projector pixel. Pass the result to `table_to_projector`. Points at or above the centre's height are dropped.
With `center_m=None` the points are projected straight down, which is only right directly below the projector.

### Calibration

**`compute_closest_point_to_rays(origins, directions)`** → (point, RMS distance in the rays' unit)
The point closest to all rays (least squares) and how far the rays pass from it. Origins and directions are N×3;
directions need not be normalised. Returns `(None, inf)` for fewer than two rays or rays that do not pin down a point,
e.g. parallel ones. `projection_calibrator` uses it to find the projector's optical centre from marker rays.

## Example: a detected pixel to projector pixels

```python
import numpy as np
from par_geometry import (get_homography_from_mapping_msg, pixels_to_table, quaternion_to_rotation_matrix,
                          table_to_projector)

camera_matrix = np.reshape(camera_info.k, (3, 3))
distortion_coefficients = np.array(camera_info.d)

transform = tf_buffer.lookup_transform('world', camera_info.header.frame_id, Time())
q = transform.transform.rotation
t = transform.transform.translation
rotation_optical_in_table = quaternion_to_rotation_matrix(q.x, q.y, q.z, q.w)
translation_optical_in_table_m = np.array([t.x, t.y, t.z])

table_points_m = pixels_to_table([[812.0, 440.0]], camera_matrix, distortion_coefficients,
                                 rotation_optical_in_table, translation_optical_in_table_m)
table_to_projector_homography = get_homography_from_mapping_msg(projection_mapping_msg)
projector_pixels = table_to_projector(table_to_projector_homography, table_points_m[:, :2])
```

Without calibrated intrinsics (`camera_info.k` all zeros) or without the transform, a node stays in camera pixels; see
"Calibration is optional" in the repository's `CLAUDE.md`.

## Limits

- Camera pixels are pixels of the raw image. For pixels of a rectified image (`image_rect`), pass zero distortion and
  the rectified camera matrix (the left 3×3 of `camera_info.p`), or the distortion is removed twice.
- The table is assumed flat. Accuracy on the table does not depend on an exact camera pose, as long as the
  projection calibration used the same pose: both steps share the same plane.
- `pixels_to_table`, `depth_to_table` and `project_to_table` drop points. A caller that matches results to its inputs
  by position has to check the lengths.

## Used by

| Use | Functions | Packages |
|---|---|---|
| Camera pose from TF | `quaternion_to_rotation_matrix` | most nodes below |
| Detected point → table | `pixels_to_table` | `gesture_detector`, `rviz_bridge`, setup wizard |
| Page → projector | `pixels_to_table`, `table_to_projector`, `apply_homography` | `demo_app`, `rendering_manager_bridge` |
| Projector pixel → camera image | `projector_to_table`, `table_to_pixels` | `training_images_collector` |
| Mask over hands and objects | `compute_pixel_rays`, `depth_to_table`, `project_to_table`, `table_to_projector` | `projection_mask` |
| Projector calibration | `pixels_to_table`, `projector_to_table`, `compute_closest_point_to_rays` | `projection_calibrator` (`projection_calibration`) |
