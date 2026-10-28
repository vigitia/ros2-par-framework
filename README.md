# ROS2 Projected Augmented Reality Framework

Readme written together with Claude Code. Comments in the Code indicate where Claude Code was used. 

A Framework for people who want to build their own Projected Augmented Reality (PAR) setups. 
It uses the Robot Operating System 2 (ROS2).

This repository contains the core components. Depending on your hardware and use case, additional components are required (see list below).

### Hardware requirements
- A Projector
- A camera (Webcam is fine to get started. Some applications/use cases require a depth camera such as the Azure Kinect or Realsense D435 or even other camera types such as IR, Thermal, etc.)

### Hardware setup

Camera and pointed at the same physical surface

### Quick start on a new computer (without Docker)


Clone this repo and navigate into the folder:
```bash
git clone git@github.com:vigitia/ros2-par-framework.git
cd ros2-par-framework
```

Install ROS2 and set the distro you picked in `scripts/common.sh` under `ROS_DISTRO`; default `lyrical`:
TODO: In the future a proper wizard/installer will take care of this

```bash
./scripts/local_build.sh           # clone every node, install dependencies, build
```
`local_build.sh` is safe to re-run — that is also how you pull node updates;

Source ROS, the python venv and the local ROS2 setup. Then enable Fast DDS Large Data Mode, so that large video streams don't drop packages:
```bash
source /opt/ros/lyrical/setup.bash && source .venv/bin/activate && source install/setup.bash
export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA
```

Run the calibration process:
```bash
ros2 launch par_framework_core calibration.launch.py
```

Launch the framwork
```bash
ros2 launch par_framework_core par.launch.py
```

Which camera and nodes `par.launch.py` starts is the `par_launch` section of
`packages/par-framework-core/config/par_setup.yaml`. Arguments override it for one run
(`camera:=kinect rviz:=true`), and `params_file:=<file>` uses another parameter file.
TODO: List available arguments here

**Setup profiles.** For another physical setup (another table, projector or camera unit), add
`profile:=<name>` to any launch file (`par.launch.py`, `calibration.launch.py`, `projection_calibration.launch.py`,
`camera_pose_calibration_kinect.launch.py`). The profile is `packages/par-framework-core/config/profiles/<name>.yaml`
(gitignored), and holds **only what differs** from `par_setup.yaml`, with the same node names and keys:

```yaml
par_launch:
  ros__parameters:
    camera: brio
/camera/brio/logitech_brio_node:
  ros__parameters:
    serial: "<serial of this Brio>"
/brio_tf_publisher:
  ros__parameters:
    translation.z: 1.10
```

A profile has its own camera pose, projection corners and projection mapping in
`config/calibration/extrinsics/<name>/`, so run the calibrations once per profile. Without `profile:=`, everything
uses `par_setup.yaml` and `config/calibration/extrinsics/` as before. Arguments on the command line still win over
both files.


In every new terminal, source `/opt/ros/<distro>/setup.bash`, `.venv/bin/activate` and
`install/setup.bash`, in that order, and run `export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA`. 

After editing node code, re-run the `colcon build` line.

### Repo structure

```
config/nodes.list           ROS2 Node repositories that make up the framework
config/ros_packages.list    released ROS packages installed instead of cloned (e.g. camera drivers)
packages/                   this repo's own ROS packages, built together with src/
  par-framework-core/       launch files + parameters (package par_framework_core)
    launch/                 ROS2 launch files
    config/par_setup.yaml   camera id, resolution, projector display
    par_framework_core/     launch_helpers.py: node start functions shared by the launch files
  par_geometry/             helper functions fpr transformations: camera pixels -> table (m) -> projector pixels
  rviz_bridge/              A ROS2 node that converts framework output into something RViz can display (e.g. turns /hand_landmarks into markers)
scripts/                    setup and helper scripts
src/                        node repositories, cloned by local_build.sh
utils/                      helper code, e.g. for creating a calibration chessboard pattern
```

### Current ROS2 packages that make up the framework

| Package | Repository | Role |
| --- | --- | --- |
| `par_framework_core` | this repo | launch files and per-setup parameters |
| `par_framework_interfaces` | `ros2-par-framework-interfaces` | shared message, service and action definitions |
| `logitech_brio` | `ros2-logitech-brio` | publishes camera frames on `/camera/brio/image_raw` (+ `/compressed`) and `CameraInfo` on `/camera/brio/camera_info`; the launch files remap them onto the framework's `/camera/...` topics |
| `surface_selector` | `ros2-par-framework-calibration` | subscribes to `/camera/image_raw`, lets you mark the projection area; `projection_calibrator` calibrates the table-to-projector mapping automatically from projected ArUco markers seen on `/fiducials` |
| `object_detector` | `ros2-par-framework-object-detection` | detects objects in `/camera/image_raw/compressed` (raw image for cameras without JPEGs), publishes them in image pixels on `/objects` |
| `fiducials_detector` | `ros2-par-framework-fiducials` | detects fiducial markers in `/camera/image_raw`, publishes them on `/fiducials` |
| `hand_landmarks` | `ros2-par-framework-hand-landmarks` | tracks hands in `/camera/image_raw` with MediaPipe, publishes their landmarks in image pixels on `/hand_landmarks` |
| `par_geometry` | this repo | library: `pixels_to_table`, `table_to_projector`, `projector_to_table` — the coordinate conversions every node shares |
| `camera_pose_calibrator` | `ros2-par-framework-calibration` | fits the table plane in the depth camera's registered depth image and writes the camera pose to `config/calibration/extrinsics/camera_pose_<camera>.yaml` |
| `projection_calibration_server` | `ros2-par-framework-calibration` | optional (`par.launch.py` starts it only when installed); stores the homography from `projection_calibrator` in `config/calibration/extrinsics/projection_mapping_<camera>.yaml` and the corners from `surface_selector` in `projection_corners_<camera>.yaml` next to it (one of each per camera), publishes them latched on `/projection_mapping` and `/projection_corners` |
| `rviz_bridge` | this repo | projects `/objects`, `/hand_landmarks`, `/fiducials`, `/projection_corners` and `/projection_mapping` onto the table as `/objects/markers`, `/hand_landmarks/markers`, `/fiducials/markers`, `/projection_corners/markers` and `/projection_mapping/markers` for RViz |

Camera frames are published **best-effort, keep-last-1** — a late frame is worthless because a newer one
already exists. Any subscriber must explicitly request `BEST_EFFORT` too; a subscriber left on the default
reliable profile is QoS-incompatible and silently receives nothing.

---

## Design decisions and conventions

**One venv on purpose.** It puts every node's `requirements.txt` into one `pip install`, so conflicting
version pins fail instead of one node silently overwriting another's.

**`python -m colcon`, not `colcon`.** Plain `colcon` builds node executables for the system Python, which
can't see the venv, so they fail with e.g. `No module named cv2`.

**`FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA`.** A raw 1080p frame is ~6 MB. With Fast DDS's default transports
most of these best-effort frames are lost on the way. The setting must be identical for
**every** ROS process: if only the publisher or only the subscriber has it, they don't connect at all and
nothing arrives (measured between two nodes).

**Nodes live in `src/`.** `scripts/sync_nodes.sh` clones each entry of `config/nodes.list` into
`src/`. Each node stays a normal git repository you can edit and can commit from if desired; after changing node code,
rebuild with `./scripts/local_build.sh <pkg>`.

**Dependencies come from the manifests.** `local_build.sh` installs the apt dependencies of every
`package.xml` with `rosdep`, and all `requirements.txt` with a single `pip` invocation into the `.venv` that is shared 
by all framework nodes. The single pip call is deliberate: if two nodes pin conflicting versions, the install fails 
instead of one node silently overwriting the other's pin.

**Per-setup values are parameters, not constants.** Which `/dev/video*` the camera is and which display the
projector is on differ per machine and sometimes even after a restart, so they live in 
`packages/par-framework-core/config/par_setup.yaml` and are passed to nodes by the launch files.

---

## Development instructions:

### Adding a node

1. Create the repository containing your new ROS2 node (if you use Python: an `ament_python` package with a `package.xml`, and a `requirements.txt` at its
   root for PyPI dependencies). The package may sit at the repo root or in a subdirectory.
2. Add the new repository to `config/nodes.list`.
3. Re-run `./scripts/local_build.sh`, this will clone the repo to `src/`.

### Custom messages, services and actions

They all live in one package, `par_framework_interfaces`, in its own repository.

Nodes declare `<depend>par_framework_interfaces</depend>` and import `from par_framework_interfaces.msg import Object`.
When adding a definition, register it in `rosidl_generate_interfaces()` in `CMakeLists.txt`, and declare any
newly referenced external package (`std_msgs`, `geometry_msgs`, …) in **both** the CMake `DEPENDENCIES` list
**and** `package.xml` — `rosdep` installs dependencies from `package.xml` only.

---

## Camera interface

The framework nodes never subscribe to a camera driver's own topics. Every driver keeps its own names
(`/camera/brio/...`, the Kinect's `/rgb/...`, `/camera/realsense/...`, `/camera/webcam/...`), and the launch file
that starts it remaps them onto one neutral interface. Which camera runs is `par_launch.camera` in `par_setup.yaml`,
or `camera:=` for one run.

| Name | Type | Content | Provided by |
| --- | --- | --- | --- |
| `/camera/image_raw` | `sensor_msgs/Image` | colour image, BGR channel order (`bgr8`; the Kinect `bgra8`) | every camera |
| `/camera/image_raw/compressed` | `sensor_msgs/CompressedImage` | the camera's own JPEGs, passed through undecoded | Brio |
| `/camera/image_rect_color` | `sensor_msgs/Image` | undistorted colour image | Brio |
| `/camera/camera_info` | `sensor_msgs/CameraInfo` | intrinsics of `/camera/image_raw` | every camera |
| `/camera/set_camera_info` | `sensor_msgs/srv/SetCameraInfo` | stores new intrinsics | Brio, webcam |
| `/camera/depth_registered/image_raw` | `sensor_msgs/Image` | depth on the colour image's pixel grid | Kinect, RealSense |

**Names are constants, remapping chooses.** Nodes take these names as constants, not as parameters; another topic
is chosen by remapping, ROS 2's own mechanism. The defaults are the `DEFAULT_TOPIC_NAME_*` constants in
`par_framework_core/launch_helpers.py`, and `CAMERA_DRIVER_REMAPPINGS` there is the only place that knows a
driver's own names.

**Frames are best-effort, keep-last-1.** Subscribers must request `BEST_EFFORT` explicitly (see above). For a
subscriber that can't be changed, such as `cameracalibrator`, the Brio's `qos_reliability: reliable` in
`par_setup.yaml` is the switch.

The depth of 1 decides *which* frame a slow node loses, not *whether* it loses one. While a callback processes
a frame, one slot holds the next; a frame arriving before the callback is done replaces the waiting one, so a
node drops frames only while its processing takes longer than the camera's frame interval. A deeper queue
does not make a node faster, it trades drops for latency:

- If processing is faster than the frame interval on average and only single frames take longer, a queue of
  2-3 absorbs those spikes, but the frames after a spike are processed late.
- If processing is slower on average, a deeper queue fills up, every frame arrives late, and frames are still
  dropped, only older ones.

For projection, latency is the worse of the two: the projected content visibly trails the paper or hand it
belongs to. So every sensor node aims to process each frame before the next one arrives, and that has to come
from processing fast enough. Depth 1 makes a node that falls behind continue with the newest frame instead of
catching up on old ones. Before changing the depth of a node, measure its processing time per frame against
the frame interval.

**Optional streams are switched per camera, not detected.** A node that can use the compressed or the depth
stream has a parameter for it (`object_detector`, `fiducials_detector`: `use_compressed`, `use_depth`), and `par.launch.py` sets it
for the cameras that provide the stream (`CAMERA_OVERRIDES`).

**Detections are in raw image pixels.** Detectors publish positions in pixels of `/camera/image_raw`, distorted
as the camera saw them. `par_geometry.pixels_to_table` undistorts them with `/camera/camera_info` and turns them
into table coordinates; it needs calibrated intrinsics and the camera pose.

**Intrinsics travel on `camera_info`.** The Brio and the webcam load theirs from
`config/calibration/intrinsics/camera_info_<camera>.yaml` (gitignored, one per camera type), which
`scripts/run_cameracalibrator.sh` writes through `/camera/set_camera_info`. A Brio whose `serial` is set has its own
file, `camera_info_brio_<serial>.yaml`, since every lens differs; set it when several Brios are in use. Intrinsics
are shared by all profiles. The Kinect and the RealSense publish
their factory calibration instead.

**The camera pose is a static transform.** `world` → the camera's body frame (`brio_link`, `camera_base`,
`realsense_link`, `webcam_link`) is published by `/<camera>_tf_publisher`, started with the driver. It uses the
measured `config/calibration/extrinsics/camera_pose_<camera>.yaml` while that file exists (written by
`camera_pose_calibration_kinect.launch.py`; with a profile in `extrinsics/<profile>/`), and otherwise the placeholder
under `/<camera>_tf_publisher` in `par_setup.yaml` or the profile. The table is the plane z = 0 of `world`.

### Adding a camera

No consumer changes. In `packages/par-framework-core/`:

1. `par_framework_core/launch_helpers.py`: a `create_<camera>_...` function that starts the driver, its entry in
   `CAMERA_DRIVER_REMAPPINGS` (the driver's names onto the table above), and its branch in `create_camera_nodes`
   with the mount transform.
2. `config/par_setup.yaml`: the driver's parameters (colour images in BGR order) and a placeholder pose under
   `/<camera>_tf_publisher`.
3. `launch/par.launch.py`: an RViz configuration (a file in `config/rviz/`, named in `RVIZ_CONFIG_FILE_NAMES`),
   and the camera in
   `CAMERA_OVERRIDES` if it provides depth or JPEGs. A depth camera also goes into `DEPTH_CAMERAS` in
   `launch/projection_calibration.launch.py`.
4. A released driver goes into `config/ros_packages.list`, a driver from source into `config/nodes.list`.

---

## Coordinate systems

Four coordinate systems, and every value in the framework is in exactly one of them:

| System | Unit | Origin and axes | Used for |
| --- | --- | --- | --- |
| Camera pixels | px | raw, distorted `/camera/image_raw`: origin top left, x right, y down | everything detectors find (contours, fiducial and page corners, hand landmarks, `Gesture.pixel`), the clicked projection corners |
| Camera optical frame | m | the image's `header.frame_id` (`rgb_camera_link`, `brio_optical_frame`, `realsense_color_optical_frame`, `webcam_optical_frame`): x right, y down, z forward | what a depth camera measures: `center_3d`, `hull_contour_3d`, `hand_landmarks_3d`, `corners_3d` |
| Table, frame `world` | m | z = 0 is the tabletop, z points up, the origin lies below the camera | `Gesture.position`, `/projection_mapping` and the projector centre, the RViz markers |
| Projector pixels | px | origin top left of the projected image, at the projector's resolution | `/projector/mask`, `/projector/content_mask`, what an app draws |

**`world` is the table.** The tabletop is the plane z = 0 of `world`, in metres, with z pointing away from the
table. Every node that needs table coordinates uses the frame name `world`; there is no separate table frame. The
TF tree is `world` → the camera's body frame (the mount transform, see above) → its optical frame (published by
the driver). The camera pose calibration measures height and tilt; x, y and the rotation about the vertical come
from the placeholder in `par_setup.yaml`, so the origin is the point on the table below the camera.

**Messages stay in the frame they were measured in.** Detectors publish camera pixels and optical-frame points,
with the image's `stamp` and `frame_id` copied into their header, and leave conversion to the consumer. A node that
also offers table coordinates adds them next to the pixels instead of replacing them, with a validity flag
(`gesture_detector`: `pixel` always, `position` with `position_valid`), so it still works without a calibration.

**Conversions happen locally, with `par_geometry`.** It is the one place for this math; nodes call it on their
own data instead of a service per point:

- camera pixels → table: `pixels_to_table`, which undistorts with `/camera/camera_info` and intersects each pixel's
  ray with z = 0, using the camera pose from TF;
- optical frame → table: `depth_to_table` for a whole depth image, or the pose from TF directly;
- table ↔ projector pixels: `table_to_projector` and `projector_to_table`, with the homography from the latched
  `/projection_mapping`;
- above the table → table: `project_to_table` moves a point along its projector ray onto z = 0, so
  `table_to_projector` then gives the pixel that lights it.

**The table plane links camera and projector.** The homography is fitted from markers that `pixels_to_table`
placed on the same plane, so projection accuracy does not depend on an exact camera pose; the metric scale (and so
what RViz shows) does. The homography only covers the plane: a point above the table (a hand) lands offset by
parallax, unless the projector centre is calibrated and `project_to_table` is used first.
