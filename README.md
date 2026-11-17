# ROS2 Projected Augmented Reality Framework

> Readme written together with Claude Code. Comments in the Code indicate where Claude Code was used while creating this framework. 

A Framework for people who want to build their own Projected Augmented Reality (PAR) setups. 
It is built on the Robot Operating System 2 (ROS2). Most components are fully interchangable ROS 2 packages that make it modular.

This repository contains the frameworks' core components. Depending on your hardware and use case, additional components are required (see list below).

### Minimum Hardware requirements
- A Projector
- A camera (Webcam is fine to get started. Some applications/use cases require a depth camera such as the Azure Kinect or Realsense D435 or even other camera types such as IR, Thermal, etc.)

Certain applications might require special camera types (e.g. Depth, IR, Thermal, ...) or multiple projectors (currently not yet supported).

### Hardware setup

Camera and projector pointed at the same surface. Optimal: Camera sees the entire projected image.

### Quick start on a new computer (without Docker)


Clone this repo and navigate into the folder:
```bash
git clone git@github.com:vigitia/ros2-par-framework.git
cd ros2-par-framework
```

Install ROS2 and set the distro you picked in `scripts/common.sh` under `ROS_DISTRO`; default `lyrical`:
TODO: In the future a proper wizard/installer will take care of this

```bash
./scripts/local_build.sh           # clone the core nodes, install dependencies, build
```
`local_build.sh` is safe to re-run — that is also how you pull node updates. It installs only what every setup needs
(`config/nodes.list`). Cameras, sensor processing nodes and apps are chosen per installation: add their lines from
`config/node_catalog.list` to `config/store_installed.list` (released camera drivers: their rosdep key to
`config/store_ros_packages.list`) and re-run it. For everything: `cp config/node_catalog.list config/store_installed.list`.

Source ROS, the python venv and the local ROS2 setup. Then enable Fast DDS Large Data Mode, so that large video streams don't drop packages:
```bash
source /opt/ros/lyrical/setup.bash && source .venv/bin/activate && source install/setup.bash
export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA
```

Run the calibration process (with several cameras, once per camera, choosing it with `camera:=<name>`):
```bash
ros2 launch par_framework_core calibration.launch.py
```

Launch the framework:
```bash
ros2 launch par_framework_core par.launch.py
```

Which cameras and nodes `par.launch.py` starts is the `par_launch` section of
`packages/par-framework-core/config/par_setup.yaml`. Arguments override it for one run
(`camera:=overhead rviz:=true`), and `params_file:=<file>` uses another parameter file.
TODO: List available arguments here

**Setup profiles.** For another physical setup (another table, projector or camera unit), add
`profile:=<name>` to any launch file (`par.launch.py`, `calibration.launch.py`, `projection_calibration.launch.py`,
`camera_pose_calibration_depth.launch.py`). The profile is `packages/par-framework-core/config/profiles/<name>.yaml`
(gitignored), and holds **only what differs** from `par_setup.yaml`, with the same node names and keys:

```yaml
par_launch:
  ros__parameters:
    cameras:
      overhead: 'brio:<serial of this Brio>'
    fiducials_detector: [overhead]
/overhead_tf_publisher:
  ros__parameters:
    translation.z: 1.10
```

A profile has its own camera poses, projection corners and projection mappings in
`config/calibration/extrinsics/<name>/` and its own intrinsics in `config/calibration/intrinsics/<name>/`, so run
the calibrations once per profile. The setup wizard (`setup_wizard/`) creates and edits profiles. Without `profile:=`, everything
uses `par_setup.yaml` and `config/calibration/extrinsics/` as before. Arguments on the command line still win over
both files.


In every new terminal, source `/opt/ros/<distro>/setup.bash`, `.venv/bin/activate` and
`install/setup.bash`, in that order, and run `export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA`. 

After editing node code, re-run the `colcon build` line.

### Repo structure

```
config/nodes.list           ROS2 node repositories every installation needs
config/node_catalog.list    ROS2 node repositories an installation can add (cameras, sensor nodes, apps)
config/ros_packages.list    released ROS packages every installation needs, installed instead of cloned
config/store_installed.list     (gitignored) repositories of node_catalog.list this installation added
config/store_ros_packages.list  (gitignored) released packages this installation added (e.g. camera drivers)
packages/                   this repo's own ROS packages, built together with src/
  par-framework-core/       launch files + parameters (package par_framework_core)
    launch/                 ROS2 launch files
    config/par_setup.yaml   camera id, resolution, projector display
    par_framework_core/     launch_helpers.py: node start functions shared by the launch files
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
| `surface_selector` | `ros2-par-framework-calibration` | subscribes to a camera's `image_raw`, lets you mark the projection area; `projection_calibrator` calibrates the table-to-projector mapping automatically from projected ArUco markers seen on the camera's `fiducials` |
| `object_detector` | `ros2-par-framework-object-detection` | detects objects in a camera's `image_raw/compressed` (raw image for cameras without JPEGs), publishes them in image pixels on `objects` in that camera's namespace |
| `fiducials_detector` | `ros2-par-framework-fiducials` | detects fiducial markers in a camera's `image_raw`, publishes them on `fiducials` in that camera's namespace |
| `hand_landmarks` | `ros2-par-framework-hand-landmarks` | tracks hands in a camera's `image_raw` with MediaPipe, publishes their landmarks in image pixels on `hand_landmarks` in that camera's namespace |
| `par_geometry` | this repo | library: `pixels_to_table`, `table_to_projector`, `projector_to_table` — the coordinate conversions every node shares |
| `camera_pose_calibrator` | `ros2-par-framework-calibration` | fits the table plane in the depth camera's registered depth image and writes the camera pose to `config/calibration/extrinsics/camera_pose_<camera>.yaml` |
| `projection_calibration_server` | `ros2-par-framework-calibration` | optional (`par.launch.py` starts it only when installed); stores the homography from `projection_calibrator` in `config/calibration/extrinsics/projection_mapping_<camera>.yaml` and the corners from `surface_selector` in `projection_corners_<camera>.yaml` next to it (one of each per camera), one server per camera publishes them latched on `/cameras/<camera>/projection_mapping` and `/cameras/<camera>/projection_corners` (RViz and the rendering manager read the main camera's through remappings, a PAR app the camera of its input) |
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

**Nodes live in `src/`.** `scripts/sync_nodes.sh` clones each entry of `config/nodes.list` and
`config/store_installed.list` into `src/`. Each node stays a normal git repository you can edit and can commit from if desired; after changing node code,
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
2. Add the new repository to `config/node_catalog.list` (or to `config/nodes.list` if every installation needs it),
   and to your `config/store_installed.list`.
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
needs fiducials_detector) starts along with it on the same camera. Settings: defaults under
`/cameras/*/<package>_node` in `par_setup.yaml`, per camera under `/cameras/<name>/<package>_node` in the profile.
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
`camera_pose_calibration_depth.launch.py` or `camera_pose_calibration_sheet.launch.py`; with a profile in
`extrinsics/<profile>/`), and otherwise the placeholder under `/<name>_tf_publisher` in the profile (`par_setup.yaml`
has one per type, for a camera named after its type). The camera's frames are named after it too:
`<name>_link`, `<name>_optical_frame`. The table is the plane z = 0 of `world`.

### Adding a camera

No change in core and none in the consumers. A camera type is an entry in the ament index plus a launch file that
starts the driver in the camera's namespace and maps its names onto the table above; blueprint and rules:
`templates/par_camera/README.md`. Our own drivers ship both in their repo (`logitech_brio`, `see3cam_cu40`), core
ships them for third-party drivers (`packages/par-framework-core/resource/par_framework_cameras/`, `launch/camera_*.launch.py`).
Then:

1. `config/par_setup.yaml`: the driver's defaults under `/cameras/*/<driver node>` (colour images in BGR order) and
   a placeholder pose under `/<type>_tf_publisher`.
2. A released driver is named in the camera entry's `required_packages` (installations add its rosdep key to
   `config/store_ros_packages.list`), a driver from source goes into `config/node_catalog.list`.

The one RViz configuration, `config/rviz/par_framework.rviz`, shows the main camera and needs no change.

### Event camera

An event camera reports brightness changes per pixel instead of frames. A camera of type `event`
(`cameras: {event: event}`, or `camera:=event`) starts like the other cameras, through the released
`metavision_driver` (OpenEB) as `/cameras/<name>/event`, with its settings under `/cameras/*/event` in
`par_setup.yaml`. Next to it, `event_camera_renderer` (`/cameras/<name>/event_renderer`) collects the events into
`bgr8` images on `/cameras/<name>/image_raw`, at `fps` per second, and reads events only while something subscribes
to the images. The raw events are on `/cameras/<name>/events` for nodes that want them. The driver publishes no `camera_info`, so the
event camera has no intrinsics, and nothing that needs them (`pixels_to_table`, the frustum in RViz) works with it.
The detectors are built for normal images; how well they work on collected events depends on the scene.

**Vendor plugin.** OpenEB opens Prophesee's own cameras; other makers ship a HAL plugin, which has to match the OpenEB
version bundled with the driver
(`grep VERSION /opt/ros/$ROS_DISTRO/opt/openeb_vendor/include/metavision/sdk/version.h`). For a SilkyEvCam that is
Century Arks' "SilkyEvCam Plugin Installer for ubuntu" of the same version. Its installer refuses Ubuntu versions it
has no folder for; the newest folder's plugin can be installed by hand instead, from the unpacked installer:

```bash
sudo install -D -m 644 resources/24.04/libsilky_common_plugin.so /usr/lib/CenturyArks/hal/plugins/libsilky_common_plugin.so
sudo cp resources/ca_device.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules
```

Then replug the camera, and set the plugin folder in every shell that starts ROS (`par.launch.py` warns when it is
missing; bash: `~/.bashrc`, fish: `set -gx` in `~/.config/fish/config.fish`):

```bash
export MV_HAL_PLUGIN_PATH=/usr/lib/CenturyArks/hal/plugins
```

The package's two command-line tools are not needed by the driver.

**USB 3 only.** On a USB 2 link (`cat /sys/bus/usb/devices/*/speed` shows `480`, e.g. through a USB 2 extension cable),
changing a bias while events stream can abort the driver, and the camera then opens again only after replugging.

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
