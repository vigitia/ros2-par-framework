# ROS2 Projected Augmented Reality Framework

> Readme written together with Claude Code. Comments in the Code indicate where Claude Code was used while creating this framework. 

## 1. Overview

A Framework for people who want to build their own Projected Augmented Reality (PAR) setups. 

It is built on the Robot Operating System 2 (ROS2). Most components are fully interchangeable ROS 2 packages that make it modular.

This repository contains the frameworks' core components. 
Depending on your hardware and use case, additional components are required (see list below).

## 2. Hardware

### 2.1 Minimum Hardware requirements
- A Projector
- A camera (Webcam is fine to get started)

Certain applications might require special camera types (e.g. Depth, IR, Thermal, ...) or multiple projectors (currently not yet supported).

### 2.2 Hardware setup

Camera and projector pointed at the same surface. Optimal: Camera sees the entire projected image.


## 3. Installation 

Currently, only manual installation is supported.
While most parts of the framework should run under Windows or MacOS, some parts currently do not. Support for Docker is work in progress and should close this gap.
Everything is currently tested on **Ubuntu 26.04**.

### Prerequisites

Install **ROS2**. Tested with `lyrical`:

Clone this repo and navigate into the folder:
```bash
git clone https://github.com/vigitia/ros2-par-framework.git
cd ros2-par-framework
```

### Framework Installation with the provided Wizard

![Wizard.png](setup_wizard/assets/Wizard.png)

```bash
./scripts/start_setup_wizard.sh
```

The installation also adds the wizard to the application menu (a .desktop file in ~/.local/share/applications).

The wizard will guide you then through all installation, setup and calibration steps and allows you to test components and

#### Manual installation

```bash
./scripts/local_build.sh
```
`local_build.sh` is safe to re-run — that is also how you pull node updates. 

Missing build tools (rosdep, colcon, Python's venv) are installed on the way; 
for some dependencies it might ask for your sudo password. With `--non-interactive` it never asks: it prints the one `sudo ...` command instead for you to run yourself. 

Dependencies: It installs only what every setup needs (as defined in `config/required_repos.list`). 
Cameras, Sensor Processing Nodes and Apps are chosen per installation: add their lines from `config/catalog_repos.list` to `config/installed_repos.list` (released camera drivers: their rosdep key to `config/installed_ros_packages.list`) and re-run it. 

Source ROS, the python venv and the local ROS2 setup. Then enable Fast DDS Large Data Mode, so that large video streams don't drop packages:
```bash
source /opt/ros/lyrical/setup.bash && source .venv/bin/activate && source install/setup.bash
export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA
```

Run the calibration process (with several cameras, once per camera, choosing it with `camera:=<name>`):
```bash
ros2 launch projection_calibration projection_corners.launch.py
```
The calibration launch files come with `ros2-par-framework-calibration`; its README lists all of them.

Launch the framework (the wizard will help you setup custom profiles. Without it, you need to update launch entries manually):
```bash
ros2 launch par_framework_core par.launch.py
```

### Profiles

The wizard allows creation of individual profiles (physical, e.g., a different hardware setup, or digital, e.g., different apps that should launch).


### Repo structure

```
config/required_repos.list           ROS2 node repositories every installation needs
config/catalog_repos.list    ROS2 node repositories an installation can add (cameras, sensor nodes, apps)
config/required_ros_packages.list    released ROS packages every installation needs, installed instead of cloned
config/installed_repos.list     (gitignored) repositories of catalog_repos.list this installation added
config/installed_ros_packages.list  (gitignored) released packages this installation added (e.g. camera drivers)
packages/                   this repo's own ROS packages, built together with src/
  par-framework-core/       launch files + parameters (package par_framework_core)
    launch/                 ROS2 launch files
    config/par_setup.yaml   cameras and nodes to start, projector display, placeholder camera pose
    par_framework_core/     shared Python modules: launch_helpers.py (launch arguments and actions), setup files, camera types, apps, sensor nodes
  par_camera_adapters/      camera types for third-party drivers (webcam, RealSense, Kinect, Blackfly, event camera)
  par_geometry/             helper functions fpr transformations: camera pixels -> table (m) -> projector pixels
  rviz_bridge/              A ROS2 node that converts framework output into something RViz can display (e.g. turns /hand_landmarks into markers)
scripts/                    setup and helper scripts
setup_wizard/               setup wizard: Flutter app + FastAPI backend that create and calibrate profiles
src/                        node repositories, cloned by local_build.sh
templates/                  blueprints: a camera type, a PAR app, a sensor processing node
utils/                      helper code, e.g. for creating a calibration chessboard pattern
```


### Current ROS2 packages that make up the framework

| Package | Repository | Role |
| --- | --- | --- |
| `par_framework_core` | this repo | launch files and per-setup parameters |
| `par_framework_interfaces` | `ros2-par-framework-interfaces` | shared message, service and action definitions |
| `logitech_brio` | `ros2-logitech-brio` | Brio driver and camera type `brio`: frames on `/cameras/<camera>/image_raw` (+ `/compressed`) and `CameraInfo` on `/cameras/<camera>/camera_info` |
| `projection_calibration` | `ros2-par-framework-calibration` | `projection_corner_selector` subscribes to a camera's `image_raw`, lets you mark the projection area; `projection_calibrator` calibrates the table-to-projector mapping automatically from projected ArUco markers seen on the camera's `fiducials` |
| `object_detector` | `ros2-par-framework-object-detection` | detects objects in a camera's `image_raw/compressed` (raw image for cameras without JPEGs), publishes them in image pixels on `objects` in that camera's namespace |
| `fiducials_detector` | `ros2-par-framework-fiducials` | detects fiducial markers in a camera's `image_raw`, publishes them on `fiducials` in that camera's namespace |
| `hand_landmarks` | `ros2-par-framework-hand-landmarks` | tracks hands in a camera's `image_raw` with MediaPipe, publishes their landmarks in image pixels on `hand_landmarks` in that camera's namespace |
| `par_geometry` | this repo | library: `pixels_to_table`, `table_to_projector`, `projector_to_table` — the coordinate conversions every node shares |
| `camera_pose_calibrator` | `ros2-par-framework-calibration` | fits the table plane in the depth camera's registered depth image and writes the camera pose to `config/calibration/extrinsics/camera_pose_<camera>.yaml` |
| `projection_calibration_server` | `ros2-par-framework-calibration` | optional (`par.launch.py` starts it only when installed); stores the homography from `projection_calibrator` in `config/calibration/extrinsics/projection_mapping_<camera>.yaml` and the corners from `projection_corner_selector` in `projection_corners_<camera>.yaml` next to it (one of each per camera), one server per camera publishes them latched on `/cameras/<camera>/projection_mapping` and `/cameras/<camera>/projection_corners` (RViz and the rendering manager read the main camera's through remappings, a PAR app the camera of its input) |
| `rviz_bridge` | this repo | projects `objects`, `hand_landmarks`, `fiducials`, `projection_corners` and `projection_mapping` onto the table as `/objects/markers`, `/hand_landmarks/markers`, `/fiducials/markers`, `/projection_corners/markers` and `/projection_mapping/markers` for RViz; reads the main camera's `camera_info` and projection calibration, but no detections yet, since the sensor nodes publish in their camera's namespace |

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

**Nodes live in `src/`.** `scripts/sync_nodes.sh` clones each entry of `config/required_repos.list` and
`config/installed_repos.list` into `src/`. Each node stays a normal git repository you can edit and can commit from if desired; after changing node code,
rebuild with `./scripts/local_build.sh <pkg>`.

**Dependencies come from the manifests.** `local_build.sh` installs the apt dependencies of every
`package.xml` with `rosdep`, and all `requirements.txt` with a single `pip` invocation into the `.venv` that is shared 
by all framework nodes. The single pip call is deliberate: if two nodes pin conflicting versions, the install fails 
instead of one node silently overwriting the other's pin.

**Per-setup values are parameters, not constants.** Which `/dev/video*` the camera is and which display the
projector is on differ per machine and sometimes even after a restart, so they are ROS parameters: each node declares
its defaults in its code, a camera type for a third-party driver brings its driver defaults as `parameters_file`, and
a profile overrides them; the launch files pass the parameter files to the nodes.

---

## Development instructions:

### Adding a node

1. Create the repository containing your new ROS2 node (if you use Python: an `ament_python` package with a `package.xml`, and a `requirements.txt` at its
   root for PyPI dependencies). The package may sit at the repo root or in a subdirectory.
2. Add the new repository to `config/catalog_repos.list` (or to `config/required_repos.list` if every installation needs it),
   and to your `config/installed_repos.list`.
3. Re-run `./scripts/local_build.sh`, this will clone the repo to `src/`.

### Custom messages, services and actions

They all live in one package, `par_framework_interfaces`, in its own repository.

Nodes declare `<depend>par_framework_interfaces</depend>` and import `from par_framework_interfaces.msg import Object`.
When adding a definition, register it in `rosidl_generate_interfaces()` in `CMakeLists.txt`, and declare any
newly referenced external package (`std_msgs`, `geometry_msgs`, …) in **both** the CMake `DEPENDENCIES` list
**and** `package.xml` — `rosdep` installs dependencies from `package.xml` only.

---

## Camera interface

Every camera of a setup has a name, chosen by its role or mount position, and a unit:
`par_launch.cameras: {overhead: 'blackfly:22260470', capture: 'blackfly:25290614'}` (`'<type>'` for a type without
serial numbers). `par.launch.py` starts all of them, each in its own namespace `/cameras/<name>/`; `camera:=<name>`
starts one of them, `camera:=<type>[:<serial>]` a unit no profile names yet. The camera types are installed in the
ament index (`par_framework_cameras`): `brio`, `cu40`, `webcam`, `blackfly`, `kinect`, `realsense`, `event`.

The framework nodes never subscribe to a camera driver's own topics. Inside the camera's namespace every driver's
streams have the same names, those of the ROS image pipeline; the camera type's launch file maps the driver's own
names onto them. Which streams a camera offers is `streams` in its type's entry.

| Name below `/cameras/<name>/` | Type | Content | Camera types |
| --- | --- | --- | --- |
| `image_raw` | `sensor_msgs/Image` | colour image, BGR channel order (`bgr8`; the Kinect `bgra8`, a monochrome Blackfly `mono8`; from an event camera its events collected into images) | every camera |
| `image_raw/compressed` | `sensor_msgs/CompressedImage` | the camera's own JPEGs, passed through undecoded | brio |
| `camera_info` | `sensor_msgs/CameraInfo` | intrinsics of `image_raw` | every camera except event |
| `set_camera_info` | `sensor_msgs/srv/SetCameraInfo` | stores new intrinsics | brio, cu40, webcam, blackfly |
| `depth_registered/image_raw` | `sensor_msgs/Image` | depth on the colour image's pixel grid | kinect, realsense |
| `ir/image_raw` | `sensor_msgs/Image` | infrared on the colour image's pixel grid (`mono8`; the Kinect's only while subscribed) | cu40, kinect |
| `depth_sensor/ir/image_raw`, `depth_sensor/depth/image_raw`, `depth_sensor/camera_info` | `sensor_msgs/Image`, `CameraInfo` | the depth camera's own infrared and depth, unregistered and aligned pixel by pixel; its pose relative to the colour camera is in TF | kinect |
| `events` | `event_camera_msgs/EventPacket` | raw events, EVT3 encoded; published only while something subscribes | event |
| `projection_mapping`, `projection_corners` | `par_framework_interfaces` | the camera's projection calibration, latched | every camera, while `projection_calibration_server` is installed |

**Sensor nodes run in their camera's namespace.** `par_launch.<sensor node>` lists the cameras a node runs on, e.g.
`fiducials_detector: [overhead]`; it runs once per listed camera as `/cameras/<name>/<package>_node`, where its
relative names resolve to that camera's streams and its outputs stay apart from another camera's
(`/cameras/overhead/fiducials`). A node another one needs (`required_sensor_nodes` in its entry, e.g. page_locator
needs fiducials_detector) starts along with it on the same camera. Settings: the node's own defaults, in
a profile for every camera under `/cameras/*/<package>_node` or per camera under `/cameras/<name>/<package>_node`.
`<sensor node>:=false` turns all its runs off for one run, `:=true` runs it on the only camera. Merging the outputs
of several cameras into one (e.g. markers in table metres) is planned as a fusion node, not built yet.

**Apps bind their inputs to cameras.** An app runs in the root namespace; its entry names the cameras it reads
(`inputs`), and `par_launch.app_inputs` binds each input to a camera, e.g. `app_inputs: {demo_app: {camera:
overhead}}`, set in the setup wizard's Apps area. `par.launch.py` remaps the app's names onto that camera; an
input left unbound reads the only camera of a run (details: `templates/par_app/README.md`). RViz and the rendering
manager use the main camera, the first of `par_launch.cameras`.

**Names are constants, remapping chooses.** Nodes take these names as relative constants, not as parameters; which
camera they mean is chosen by the namespace they run in or by remapping, ROS 2's own mechanisms. The camera type's
launch file is the only place that knows a driver's own names.

**Frames are best-effort, keep-last-1.** Subscribers must request `BEST_EFFORT` explicitly (see above). For a
subscriber that can't be changed, such as `cameracalibrator`, the Brio's `qos_reliability: reliable` in
the profile is the switch.

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
for the cameras whose entry lists the stream (`DETECTOR_PARAMETER_BY_CAMERA_STREAM`).

**Detections are in raw image pixels.** Detectors publish positions in pixels of their camera's `image_raw`,
distorted as the camera saw them. `par_geometry.pixels_to_table` undistorts them with that camera's `camera_info`
and turns them into table coordinates; it needs calibrated intrinsics and the camera pose.

**Intrinsics travel on `camera_info`.** A camera type with `intrinsics: calibratable` in its entry loads them from
`config/calibration/intrinsics/<profile>/camera_info_<type>_<serial>.yaml` (`camera_info_<type>.yaml` for a unit
without serial; gitignored; without `profile:=` the shared `config/calibration/intrinsics/`), which
`scripts/run_cameracalibrator.sh <camera> <corners> <square size>` writes through the camera's `set_camera_info`.
They belong to the unit, since every lens differs: a replaced unit is calibrated anew, while the camera's name, pose
and projection mapping stay. Each profile has its own intrinsics, so recalibrating a camera for one setup (e.g.
after refocusing) leaves the others alone. `factory` types (Kinect, RealSense) publish their factory calibration
instead, the event camera (`none`) has none.

**The camera pose is a static transform.** `world` → the camera's body frame `<name>_<body_frame>` (e.g.
`overhead_link`, the Kinect's `<name>_camera_base`) is published by `/<name>_tf_publisher`, started with the camera.
It uses the measured `config/calibration/extrinsics/camera_pose_<name>.yaml` while that file exists (written by
`camera_pose_calibration_depth.launch.py` or `camera_pose_calibration_sheet.launch.py` of `camera_pose_calibrator`; with a profile in
`extrinsics/<profile>/`), and otherwise a placeholder pose: `/<name>_tf_publisher` where a profile sets one for this
camera, else `placeholder_camera_pose` in `par_setup.yaml`, the same for every camera. The camera's frames are named
after it too: `<name>_link`, `<name>_optical_frame`. The table is the plane z = 0 of `world`.

### Adding a camera

No change in core and none in the consumers. A camera type is an entry in the ament index plus a launch file that
starts the driver in the camera's namespace and maps its names onto the table above; blueprint and rules:
`templates/par_camera/README.md`. Our own drivers ship both in their repo (`logitech_brio`, `see3cam_cu40`); for
third-party drivers they are in `packages/par_camera_adapters/`.
Then:

1. The driver defaults the framework needs (e.g. colour images in BGR order) in a parameter file under
   `/cameras/*/<driver node>`, named as `parameters_file` in the camera entry (e.g.
   `packages/par_camera_adapters/config/realsense.yaml`).
2. A released driver is named in the camera entry's `required_packages` (installations add its rosdep key to
   `config/installed_ros_packages.list`), a driver from source goes into `config/catalog_repos.list`.

The one RViz configuration, `config/rviz/par_framework.rviz`, shows the main camera and needs no change.

### Event camera

Setup of an event camera (vendor plugin, USB 3): `packages/par_camera_adapters/README.md`.

---

## Coordinate systems

Four coordinate systems, and every value in the framework is in exactly one of them:

| System | Unit | Origin and axes | Used for |
| --- | --- | --- | --- |
| Camera pixels | px | raw, distorted `image_raw` of the camera: origin top left, x right, y down | everything detectors find (contours, fiducial and page corners, hand landmarks, `Gesture.pixel`), the clicked projection corners |
| Camera optical frame | m | the image's `header.frame_id` (`<camera>_optical_frame`; the Kinect's `<camera>_rgb_camera_link`): x right, y down, z forward | what a depth camera measures: `center_3d`, `hull_contour_3d`, `hand_landmarks_3d`, `corners_3d` |
| Table, frame `world` | m | z = 0 is the tabletop, z points up, the origin lies below the camera | `Gesture.position`, each camera's `projection_mapping` and the projector centre, the RViz markers |
| Projector pixels | px | origin top left of the projected image, at the projector's resolution | `/projector/mask`, `/projector/content_mask`, what an app draws |

**`world` is the primary projection surface.** For PAR tabletops this means the tabletop is the plane z = 0 of `world`, in metres, with z pointing away from the
table. Every node that needs table coordinates uses the frame name `world`; there is no separate table frame. The
TF tree is `world` → the camera's body frame (the mount transform, see above) → its optical frame (published by
the driver). The camera pose calibration measures height and tilt; x, y and the rotation about the vertical come
from the placeholder in `par_setup.yaml`, so the origin is the point on the table below the camera. Until the poses
of several cameras are measured in one common `world`, each camera's placeholder makes its own table plane, so every
camera has its own projection mapping.

**Messages stay in the frame they were measured in.** Detectors publish camera pixels and optical-frame points,
with the image's `stamp` and `frame_id` copied into their header, and leave conversion to the consumer. A node that
also offers table coordinates adds them next to the pixels instead of replacing them, with a validity flag
(`gesture_detector`: `pixel` always, `position` with `position_valid`), so it still works without a calibration.

**Conversions happen locally, with `par_geometry`.** It is the one place for this math; nodes call it on their
own data instead of a service per point:

- camera pixels → table: `pixels_to_table`, which undistorts with the camera's `camera_info` and intersects each pixel's
  ray with z = 0, using the camera pose from TF;
- optical frame → table: `depth_to_table` for a whole depth image, or the pose from TF directly;
- table ↔ projector pixels: `table_to_projector` and `projector_to_table`, with the homography from the camera's
  latched `projection_mapping`;
- above the table → table: `project_to_table` moves a point along its projector ray onto z = 0, so
  `table_to_projector` then gives the pixel that lights it.

**The table plane links camera and projector.** The homography is fitted from markers that `pixels_to_table`
placed on the same plane, so projection accuracy does not depend on an exact camera pose; the metric scale (and so
what RViz shows) does. The homography only covers the plane: a point above the table (a hand) lands offset by
parallax, unless the projector centre is calibrated and `project_to_table` is used first.


## WIP: Types of Nodes in the Framework:
- Core
- Cameras
- Sensor Processing Nodes
- Apps