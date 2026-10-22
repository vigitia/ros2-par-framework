# CLAUDE.md

<!-- Co-authored by Claude Code -->

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Core repository of a projected augmented reality (PAR) framework on ROS 2 — a camera and a projector aimed at
the same surface. It declares which repos make up a setup (`config/nodes.list`)
and provides the launch files and per-setup parameters that compose them. Its own source is limited to what every setup builds.

**Where a package belongs.** Ask in this order; the first yes decides:

1. **Useful outside the framework?** (a camera driver, a detector) → its own repo under `github.com/vigitia`, or a
   public third-party repo.
2. **A shared library other repos build on, or tooling to set up and inspect the framework?** (`par_geometry`,
   `rviz_bridge`) → this repo, under `packages/`.
3. **Otherwise it is a framework capability** (calibration, projection mask) → its own repo under
   `github.com/vigitia`, even though it only makes sense inside the framework. A setup gets it through its line in
   `config/nodes.list`. Nothing in this repo declares it as a dependency, and `par.launch.py` starts it only when it
   is installed (`has_resource('packages', …)`), otherwise it logs which repo to add.

Capability repos today: `ros2-par-framework-calibration` (below) and `ros2-par-framework-projection-mask`.

**Calibration is a framework capability** (rule 3). The framework runs without any calibration, in camera pixels:
an application that, say, detects gestures and changes what is projected needs none. Everything that produces or
serves a calibration — camera pose, projection corners, projection mapping, and the node that loads and publishes
them latched — belongs in `ros2-par-framework-calibration`; adding that repo to a setup is what makes it fully
calibrated. So a node that can work without calibration must: it publishes camera pixels always and adds table or
projector coordinates only when the calibration is there (e.g. `gesture_detector`: `pixel` always, `position` with
`position_valid`), instead of publishing nothing. Camera intrinsics are not part of this split: they belong to the
camera and travel on ROS's standard `camera_info` channel, so `launch_helpers` setting each driver's
`camera_info_url` and `scripts/run_cameracalibrator.sh` stay here. The calibration repo holds three packages one level
down (`surface_selector`, `camera_pose_calibrator`, `projection_calibration_server`); `par_framework_core` declares
none of them, `par.launch.py` starts the server only when it is installed, and the calibration launch files here need
the repo.

This repo's own ROS packages live under `packages/`, which `local_build.sh` takes as a whole, so a
new package there needs no path changes. `packages/par-framework-core/` (package `par_framework_core`) holds the
launch files and `config/par_setup.yaml` only, no nodes. New core packages (rule 2) get their own package directory next to it.

## Commands

Everything runs on the host. ROS's setup scripts only source in bash, so the scripts and manual commands run there.

```bash
./scripts/local_build.sh [pkg]      # clone nodes, rosdep, .venv, colcon build --symlink-install; safe to re-run

# by hand, in each new bash terminal:
source /opt/ros/lyrical/setup.bash && source .venv/bin/activate && source install/setup.bash
export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA
ros2 launch par_framework_core par.launch.py camera:=kinect rviz:=true   # one entry point; args override par_launch per run
ros2 launch par_framework_core calibration.launch.py display_id:=1
```

Tests are the standard `ament` lint suite each package carries (`test_flake8`, `test_pep257`,
`test_copyright`) — linting *is* the test suite here:

```bash
# sourced as above
colcon test --packages-select logitech_brio
colcon test-result --all --verbose        # colcon test's own exit status hides failures; read results here
colcon test --packages-select logitech_brio --pytest-args -k flake8
```

## Architecture

**Source in `src/`, dependencies from the manifests.** `scripts/sync_nodes.sh` clones each entry of
`config/nodes.list` into `src/`; each node stays its own git repo. `scripts/local_build.sh` resolves the
`package.xml` of every package with `rosdep` and all `requirements.txt` with one `pip` call into `.venv`
(`--system-site-packages`, so apt's rclpy stays importable), then builds with `.venv/bin/python -m colcon`.
All `requirements.txt` go into a single `pip install` on purpose: conflicting pins fail the install instead of
one node silently overwriting another's.

**Adding a node** = one line in `config/nodes.list`, then `./scripts/local_build.sh`. Nothing else — the
dependency steps are generic. A node repo needs a colcon-buildable package with a `package.xml` that declares
all its dependencies — `ament_python` or `ament_cmake` both work (`par_framework_interfaces` and
`azure_kinect_ros_driver` are CMake). Our own nodes are `ament_python` by convention (see below); third-party
repos keep whatever they use, but one written for an older distro may not build on this one without a fork.
PyPI deps go in an optional `requirements.txt` at the repo root. Every repo currently puts its package at the root; staging also
tolerates a package one level down, or several per repo, keying each by the declared `<name>` rather than the
directory name.

**Released packages** used unchanged (`v4l2_camera` for the webcam, `realsense2_camera`) are not cloned: they are
rosdep keys in `config/ros_packages.list`. `scripts/common.sh` (`write_ros_packages_manifest`) turns the list into a
generated `package.xml` that `local_build.sh`'s rosdep call reads from a temporary directory. So camera drivers
stay optional: `par_framework_core` declares none of them. The Azure Kinect SDK (`K4A`) has no rosdep rule and is
installed by hand, so rosdep runs with `--skip-keys K4A`, and nothing in `par_framework_core` may declare the Kinect
driver, or a Brio-only build breaks.

### Custom interfaces

All `.msg`, `.srv` and `.action` definitions live in one package, `par_framework_interfaces`, from
`ros2-par-framework-interfaces`. It is `ament_cmake` because `rosidl_generate_interfaces()` is a CMake macro —
interfaces **cannot** be generated from an `ament_python` package, so they can never be folded into a node.
Nodes ported from the older VIGITIA framework import it under its old name, `custom_interfaces`; change those
imports and `<depend>` entries to `par_framework_interfaces`.

Adding an interface means three edits, and the third is the one that gets forgotten:
1. the `.msg`/`.srv`/`.action` file;
2. its path in the `rosidl_generate_interfaces()` list in `CMakeLists.txt`;
3. any newly referenced external package in **both** `DEPENDENCIES` in `CMakeLists.txt` **and** as `<depend>`
   in `package.xml`. rosdep resolves dependencies from `package.xml` alone, so a package declared only in
   CMake builds by luck — it works while the installed `ros-desktop` happens to ship it and breaks on a slimmer
   install.

Consumers declare `<depend>par_framework_interfaces</depend>` and import `from par_framework_interfaces.msg import Object`.
Changing an existing definition or pulling in a new *external* message package needs `./scripts/local_build.sh`
(rosdep installs the new dependency, colcon rebuilds dependents in order).

**Per-setup values are parameters.** Camera index, resolution, projector display live in
`packages/par-framework-core/config/par_setup.yaml`, keyed by node name, and are handed to nodes by the launch files. Hardware
constants belong there, not in node source. A node in a namespace (the Brio sets `/camera/brio` in code) must
be keyed by its full name, e.g. `/camera/brio/logitech_brio_node` — a bare name is silently ignored.

**Node package convention** (follow it for every new node): `<pkg>/<pkg>_node.py` does only the ROS work,
where possible — the `rclpy.node.Node` subclass with its topics, services, `declare_parameter` with
`ParameterDescriptor`, message conversion, and the `main()` that `setup.py` exposes as a `console_scripts` entry
point. All other logic (device access, algorithms, geometry, display) lives in other Python files of the package,
`<pkg>/<pkg>.py` or more where it helps, which import nothing from `rclpy` or the message packages. The node calls
into them with plain Python and NumPy values. That keeps the logic testable with plain pytest, without a running
ROS graph, and reusable outside the node.

### Current pipeline

**The camera interface is neutral.** Whichever camera runs, the framework nodes subscribe to `/camera/image_raw`
(plus the Brio's own JPEGs on `/camera/image_raw/compressed`), `/camera/camera_info`, `/camera/set_camera_info` and,
from a depth camera, `/camera/depth_registered/image_raw` (depth on the colour image's pixel grid). The drivers keep
their own names (`/camera/brio/...`, the Kinect's `/rgb/...` and `/depth_to_rgb/...`, `/camera/webcam/...`); where a
launch file starts a driver, it remaps it onto the neutral names with `launch_helpers.DRIVER_REMAPPINGS`, so that table
is the only place that knows a driver's topics. A new camera = a driver start in `launch_helpers` plus its entry
there, and no consumer changes. `surface_selector` consumes frames to mark the projection area. `page_locator` turns `/fiducials` into `/pages` (`par_framework_interfaces/PageList`, every frame, corners
in camera pixels): sheets with markers `4n .. 4n+3` in their corners, located by one homography to the printed layout,
so the `marker_*` layout in `par_setup.yaml` must match the paper (default: the VIGITIA document pages, ids 96-99;
`make_page_template` prints matching pages). Camera intrinsics are
`config/calibration/intrinsics/camera_info_<camera>.yaml` (gitignored, one per camera type): `launch_helpers`
sets each camera's `camera_info_url` there, and `scripts/run_cameracalibrator.sh` writes it through the camera's
`set_camera_info`. The Kinect driver publishes its factory calibration instead.

**QoS is a trap here.** Frames are published BEST_EFFORT / KEEP_LAST depth 1. A subscriber on the default
reliable profile — including the shorthand of passing an int depth as `qos_profile` — is QoS-incompatible and
receives nothing, silently and without error. New image subscribers must request
`QoSReliabilityPolicy.BEST_EFFORT` explicitly. For third-party subscribers that can't be changed, the Brio's
`qos_reliability: reliable` (and `encoding: rgb8` for nodes that expect RGB) in `par_setup.yaml` is the switch.

The opposite trap for rarely changing state: `/projection_corners` and `/projection_mapping` are published latched
(RELIABLE + TRANSIENT_LOCAL, depth 1, like `/tf_static`). A subscriber must request
`QoSDurabilityPolicy.TRANSIENT_LOCAL`, otherwise it only receives the next change and a node started later sees
nothing.

### Coordinates: camera pixels → table → projector pixels

Detectors publish in pixels of the raw camera image. The common currency is the **table plane in metres**: z = 0
of `world`, whose pose relative to the camera is `/brio_tf_publisher` in `par_setup.yaml`.
- camera pixels → table: `par_geometry.pixels_to_table` (undistorts with `camera_info`, intersects the rays with
  the plane via TF);
- table → projector pixels: the homography on the latched `/projection_mapping`
  (`par_framework_interfaces/ProjectionMapping`), applied with `par_geometry.table_to_projector` /
  `projector_to_table`.

Consumers convert locally with `par_geometry`, the one place for this math. They do not call a service per point,
and images never go through a service. The mapping comes from `projection_calibration.launch.py`: the projector
shows ArUco markers (ids 50–58, `marker_ids` in `par_setup.yaml`; not 90–98, the VIGITIA document pages use 96–99) at known pixels, `fiducials_detector` finds them, and `projection_calibrator` (in
`surface_selector`) fits the homography and sends it to `projection_calibration_server_node` (its own package in the
calibration repo, which also holds the
clicked projection corners), which stores
`config/calibration/extrinsics/projection_mapping_<camera>.yaml` (`brio` or `kinect`), next to the camera poses
(`camera_pose_<camera>.yaml`) and the projection corners. One file per camera, because
while the camera poses are placeholders each camera has its own table plane, so a mapping only fits the camera it was
calibrated with.

Because both steps use the same plane, projection accuracy does not depend on the camera pose being exact; the
metric scale in RViz does. Points above the table (hands) land offset by parallax: the homography only covers
the plane. A second run, `projection_calibration.launch.py camera:=kinect projector_center:=true`, adds the
projector's optical centre to the mapping (`projector_center`, valid when `projector_center_valid`): a board moved
through the projection, located in 3D by the depth camera, gives one projector ray per marker corner, and the rays
meet at the centre. With it, `par_geometry.project_to_table` moves a point above the table along its projector ray
onto the table, and the homography then gives the pixel that lights it. Re-running the homography clears the
centre (if the projector moved, the old one is wrong). The clicked `/projection_corners` are a manual fallback and are named in camera terms, not
projector terms.

### Projector masks

Two images in projector pixels (`sensor_msgs/Image`, mono8, the projector's resolution, BEST_EFFORT depth 1, like
frames). Apps that project content apply or publish them; the framework has no central projector window.
- `/projector/mask`, from `projection_mask` (capability repo): 255 where the light would hit a hand or an object
  higher than `min_height` above the table. An app applies it with `frame[mask > 0] = 0`. Needs a depth camera and
  the mapping; without the projector centre it assumes light straight down.
- `/projector/content_mask`, a convention only, published by apps: 255 where the app draws content, e.g.
  `frame.max(axis=2) > threshold`. Nothing consumes it yet; reading the screen instead was rejected (Wayland only
  allows it through the portal with user consent, not from a container, and with extra delay).

## Conventions in this repo

Shell scripts source `scripts/common.sh` for `step`/`ok`/`warn`/`die` logging and `ROS_DISTRO`; they run
under `set -euo pipefail`, so pipelines whose left side legitimately exits non-zero need explicit handling.
Every failure message should name the command that fixes it — `local_build.sh` is meant to be runnable by
someone sitting at a fresh computer.
