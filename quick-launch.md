<!-- Written by Claude Code -->
# Quick launch: every node by hand

`ros2 run` commands for every node of the framework, without launch or parameter files. Use them to start a single
node for testing, or to try a parameter value for one run. The normal way stays
`ros2 launch par_framework_core par.launch.py`; these commands do what it does, node by node. Setup profiles
(`profile:=<name>`) are a launch feature: for one by hand, change the values in the command to the profile's, and the
calibration paths to `extrinsics/<name>/`.

Each command lists **all** parameters the node declares. The values are those of
`packages/par-framework-core/config/par_setup.yaml` where it sets them, otherwise the node's default. Change a value
by editing it in the command; leave a line out to get the node's default. When the code changes, check a node's
current parameters with `ros2 param describe <node> <parameter>` or `ros2 param list <node>` while it runs.

## Before you start

Every terminal, from the repository root (the file paths below use `$PWD`):

```bash
source /opt/ros/lyrical/setup.bash && source .venv/bin/activate && source install/setup.bash
export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA
```

Syntax used below:

- `-p name:=value` sets a parameter. The value is parsed as YAML, so its type matters: a float parameter needs a
  decimal point (`4.0`, not `4`), otherwise the node rejects it at startup.
- `-p "name:=''"` sets an empty string, `-p "name:=[a, b]"` a list. The double quotes keep bash from splitting or
  eating them.
- `-r old:=new` remaps a topic or service. The framework nodes listen on `/camera/...`; the camera drivers are
  remapped onto those names, exactly as `launch_helpers.CAMERA_DRIVER_REMAPPINGS` does.
- `-r __ns:=/ns` and `-r __node:=name` set a node's namespace and name, for drivers whose code does not set them.

## Cameras

Start **one** camera driver and its mount transform (next section).

### Logitech Brio (`camera:=brio`)

The node puts itself in `/camera/brio`. `camera_id:=-1` finds the Brio automatically; `serial` picks one of several.

```bash
ros2 run logitech_brio logitech_brio --ros-args \
  -p camera_id:=-1 -p "serial:=''" \
  -p camera_resolution_x:=1920 -p camera_resolution_y:=1080 -p camera_fps:=60 \
  -p exposure_time_ms:=4.0 -p gain:=64 \
  -p undistort_frame:=false -p qos_reliability:=best_effort -p encoding:=bgr8 \
  -p camera_name:=Logitech_Brio \
  -p camera_info_url:=file://$PWD/packages/par-framework-core/config/calibration/intrinsics/camera_info_brio.yaml \
  -r /camera/brio/image_raw:=/camera/image_raw \
  -r /camera/brio/image_raw/compressed:=/camera/image_raw/compressed \
  -r /camera/brio/image_rect_color:=/camera/image_rect_color \
  -r /camera/brio/camera_info:=/camera/camera_info \
  -r /camera/brio/set_camera_info:=/camera/set_camera_info
```

Node defaults that differ: `exposure_time_ms` 10.0, `gain` 0.

### Azure Kinect (`camera:=kinect`)

The driver names its node `k4a_ros_device_node` in code and publishes without a namespace.

```bash
ros2 run azure_kinect_ros_driver node --ros-args \
  -p "sensor_sn:=''" \
  -p color_enabled:=true -p color_format:=bgra -p color_resolution:=1080P \
  -p depth_enabled:=true -p depth_mode:=WFOV_2X2BINNED -p depth_unit:=16UC1 \
  -p fps:=30 \
  -p point_cloud:=false -p rgb_point_cloud:=false -p point_cloud_in_depth_frame:=true \
  -p "tf_prefix:=''" \
  -p "recording_file:=''" -p recording_loop_enabled:=false \
  -p body_tracking_enabled:=false -p body_tracking_smoothing_factor:=0.0 \
  -p imu_rate_target:=0 \
  -p rescale_ir_to_mono8:=false -p ir_mono8_scaling_factor:=1.0 \
  -p wired_sync_mode:=0 -p subordinate_delay_off_master_usec:=0 \
  -p exposure_control_mode:=manual -p exposure_time_absolute:=16670 \
  -p white_balance_control_mode:=auto -p white_balance:=4500 \
  -p brightness:=128 -p contrast:=5 -p saturation:=32 -p sharpness:=2 -p gain:=0 \
  -p backlight_compensation:=0 -p powerline_frequency:=2 \
  -r /rgb/image_raw:=/camera/image_raw \
  -r /rgb/camera_info:=/camera/camera_info \
  -r /depth_to_rgb/image_raw:=/camera/depth_registered/image_raw
```

Node defaults that differ: `color_enabled` false, `color_resolution` 720P, `depth_mode` NFOV_UNBINNED, `fps` 5,
`point_cloud` true. The Kinect publishes its factory calibration, so it has no `camera_info_url`.

### Intel RealSense (`camera:=realsense`)

`realsense2_camera` declares far more parameters than fit here; these are the ones the framework sets. The others:
`ros2 param list /camera/realsense` while it runs.

```bash
ros2 run realsense2_camera realsense2_camera_node --ros-args \
  -r __ns:=/camera -r __node:=realsense \
  -p camera_name:=realsense \
  -p enable_color:=true -p enable_depth:=true -p enable_infra1:=false -p enable_infra2:=false \
  -p rgb_camera.color_profile:=1280x720x30 -p rgb_camera.color_format:=BGR8 \
  -p align_depth.enable:=true \
  -r /camera/realsense/color/image_raw:=/camera/image_raw \
  -r /camera/realsense/color/camera_info:=/camera/camera_info \
  -r /camera/realsense/aligned_depth_to_color/image_raw:=/camera/depth_registered/image_raw
```

### Generic UVC webcam (`camera:=webcam`)

`v4l2_camera` also turns each control of the camera (exposure, focus, ...) into a parameter: `ros2 param list
/camera/webcam/webcam_node` while it runs. The second command is the body-to-optical-frame transform that the Brio
node publishes itself.

```bash
ros2 run v4l2_camera v4l2_camera_node --ros-args \
  -r __ns:=/camera/webcam -r __node:=webcam_node \
  -p video_device:=/dev/video0 -p "image_size:=[640, 480]" -p pixel_format:=YUYV \
  -p output_encoding:=bgr8 -p camera_frame_id:=webcam_optical_frame \
  -p camera_info_url:=file://$PWD/packages/par-framework-core/config/calibration/intrinsics/camera_info_webcam.yaml \
  -r /camera/webcam/image_raw:=/camera/image_raw \
  -r /camera/webcam/camera_info:=/camera/camera_info \
  -r /camera/webcam/set_camera_info:=/camera/set_camera_info
```

```bash
ros2 run tf2_ros static_transform_publisher \
  --frame-id webcam_link --child-frame-id webcam_optical_frame \
  --qx -0.5 --qy 0.5 --qz -0.5 --qw 0.5 \
  --ros-args -r __node:=webcam_optical_tf_publisher
```

### FLIR Lepton thermal camera

Not part of `par.launch.py`. The node puts itself in `/thermal/lepton`; nothing in the framework reads it yet, so it
needs no remapping.

```bash
ros2 run flir_lepton flir_lepton --ros-args \
  -p "device_path:=''" \
  -p camera_name:=FLIR_Lepton \
  -p "camera_info_url:=''"
```

## Camera mount transform (`world` → camera body)

Where the camera hangs above the table. `static_transform_publisher` takes the pose only as command-line flags, not
as parameters. The values are the placeholders from `par_setup.yaml`; once
`config/calibration/extrinsics/camera_pose_<camera>.yaml` exists, `par.launch.py` uses the pose from there instead,
so copy its seven values into the flags. Run the one for your camera:

```bash
ros2 run tf2_ros static_transform_publisher --frame-id world --child-frame-id brio_link \
  --x 0.0 --y 0.0 --z 0.93 --qx 0.0 --qy 0.7071068 --qz 0.0 --qw 0.7071068 \
  --ros-args -r __node:=brio_tf_publisher

ros2 run tf2_ros static_transform_publisher --frame-id world --child-frame-id camera_base \
  --x 0.0 --y 0.0 --z 1.00 --qx 0.0 --qy 0.7071068 --qz 0.0 --qw 0.7071068 \
  --ros-args -r __node:=kinect_tf_publisher

ros2 run tf2_ros static_transform_publisher --frame-id world --child-frame-id realsense_link \
  --x 0.0 --y 0.0 --z 0.93 --qx 0.0 --qy 0.7071068 --qz 0.0 --qw 0.7071068 \
  --ros-args -r __node:=realsense_tf_publisher

ros2 run tf2_ros static_transform_publisher --frame-id world --child-frame-id webcam_link \
  --x 0.0 --y 0.0 --z 0.93 --qx 0.0 --qy 0.7071068 --qz 0.0 --qw 0.7071068 \
  --ros-args -r __node:=webcam_tf_publisher
```

## Detectors

These listen on the neutral `/camera/...` names, so they need no remapping. `use_compressed` and `use_depth` depend
on the camera, as `par.launch.py` sets them:

| camera              | `use_compressed`                                      | `use_depth`                                              |
|---------------------|-------------------------------------------------------|----------------------------------------------------------|
| brio                | `true` (object_detector, fiducials_detector, page_locator) | `false`                                             |
| kinect, realsense   | `false`                                               | `true` (object_detector, fiducials_detector, hand_landmarks) |
| webcam              | `false`                                               | `false`                                                  |

The commands below show the Brio's values. With another camera, change them as the table says: a raw-frame subscriber
on the Brio makes its driver decode every JPEG, which slows down every node reading the compressed frames.

### object_detector

`models_dir` empty means `<workspace root>/models`.

```bash
ros2 run object_detector object_detector --ros-args \
  -p use_compressed:=true -p use_depth:=false \
  -p min_object_height:=0.015 \
  -p "models_dir:=''"
```

Node default that differs: `min_object_height` 0.0 (off).

### fiducials_detector

```bash
ros2 run fiducials_detector fiducials_detector --ros-args \
  -p marker_type:=aruco -p dictionary:=4X4_100 \
  -p corner_refinement:=none -p adaptive_thresh_constant:=7.0 \
  -p use_compressed:=true -p use_depth:=false \
  -p debug:=false
```

Node default that differs: `dictionary` empty.

### hand_landmarks

```bash
ros2 run hand_landmarks hand_landmarks --ros-args \
  -p use_depth:=false -p num_hands:=2 -p debug:=false
```

### page_locator

Needs fiducials_detector.

```bash
ros2 run page_locator page_locator --ros-args \
  -p page_width_mm:=210.0 -p page_height_mm:=297.0 \
  -p marker_size_mm:=20.0 -p marker_margin_mm:=5.0 \
  -p "marker_corners:=[bottom_left, top_left, top_right, bottom_right]" \
  -p marker_quarter_turns:=0 -p max_pages:=25 -p hold_time_sec:=0.5 \
  -p smoothing_min_cutoff_hz:=0.5 -p smoothing_beta_per_px:=0.05 \
  -p use_compressed:=true -p debug:=false
```

### gesture_detector

Needs hand_landmarks.

```bash
ros2 run gesture_detector gesture_detector --ros-args -p debug:=false
```

## Projection calibration and mask

Need `ros2-par-framework-calibration` and `ros2-par-framework-projection-mask` in `config/nodes.list`.

### projection_calibration_server

Publishes the stored projection corners and mapping (latched). One file pair per camera; replace `brio` in both
paths with your camera.

```bash
ros2 run projection_calibration_server projection_calibration_server --ros-args \
  -p projection_corners_file:=$PWD/packages/par-framework-core/config/calibration/extrinsics/projection_corners_brio.yaml \
  -p projection_mapping_file:=$PWD/packages/par-framework-core/config/calibration/extrinsics/projection_mapping_brio.yaml
```

### projection_mask

Needs a depth camera and the projection mapping.

```bash
ros2 run projection_mask projection_mask --ros-args \
  -p min_height:=0.015 -p max_height:=1.0 -p margin_px:=15 -p stride:=6 \
  -p debug:=false -p display_id:=2
```

Node default that differs: `display_id` 0.

## Apps and visualisation

These declare no parameters.

```bash
ros2 run demo_app demo_app
ros2 run rviz_bridge rviz_bridge
ros2 run rviz2 rviz2 -d packages/par-framework-core/config/rviz/par_framework_brio.rviz
```

RViz configurations: `par_framework_brio.rviz`, `par_framework_kinect.rviz`, `par_framework_realsense.rviz`,
`par_framework_webcam.rviz`.

## Calibration tools

Each needs the camera, its mount transform and `projection_calibration_server` running.

### surface_selector (click the projection corners, `calibration.launch.py`)

```bash
ros2 run surface_selector surface_selector --ros-args -p display_id:=2
```

### projection_calibrator (table-to-projector mapping, `projection_calibration.launch.py`)

Needs fiducials_detector, with `use_depth:=true` for the `projector_center:=true` run.

```bash
ros2 run surface_selector projection_calibrator --ros-args \
  -p display_id:=2 -p dictionary:=4X4_100 \
  -p "marker_ids:=[0, 1, 2, 3, 4, 5, 6, 7, 8]" \
  -p max_reprojection_error_px:=5.0 \
  -p projector_center:=false -p max_center_ray_distance_m:=0.01
```

Node default that differs: `display_id` 0.

### camera_pose_calibrator (camera height and tilt, `camera_pose_calibration_kinect.launch.py`)

Needs a depth camera looking at the clear table. `placeholder_rotation` is the placeholder rotation (x, y, z, w) of the
camera's mount transform.

```bash
ros2 run camera_pose_calibrator camera_pose_calibrator --ros-args \
  -p camera_pose_file:=$PWD/packages/par-framework-core/config/calibration/extrinsics/camera_pose_kinect.yaml \
  -p base_frame:=camera_base \
  -p "placeholder_rotation:=[0.0, 0.7071068, 0.0, 0.7071068]" \
  -p frames:=30 -p timeout_sec:=20.0
```
