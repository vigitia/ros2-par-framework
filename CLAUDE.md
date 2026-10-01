# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Core repository of a projected augmented reality (PAR) framework on ROS 2 — a camera and a projector aimed at
the same surface. It contains **no node source, except framework glue**: nodes that only make sense inside this
framework, because they are built on its messages, topic names and frame conventions (currently `rviz_bridge`,
which turns framework outputs into RViz markers). Every other node — anything useful on its own, like a camera driver
or a detector — lives in its own private repo under
`github.com/vigitia` or comes from another public GitHub repo; this repo declares which ones make up the framework, provides the container they run in,
and provides the launch files and per-setup parameters that compose them.

This repo's own ROS packages live under `packages/`, which the build scripts and the container take as a whole, so a
new package there needs no path changes. `packages/par-framework-core/` (package `par_framework_core`) holds the
launch files and `config/par_setup.yaml` only, no nodes. Glue nodes get their own package directory next to it.

## Commands

```bash
./setup.sh                          # full bootstrap; safe to re-run, also pulls node updates
./setup.sh --skip-clone --no-cache  # rebuild image without touching src/

./scripts/shell.sh                  # shell in the container (ROS + workspace sourced)
./scripts/build_workspace.sh [pkg]  # colcon build --symlink-install, optionally one package
./scripts/launch.sh [name] [args]   # ros2 launch par_framework_core <name>.launch.py
./scripts/launch.sh calibration display_id:=1

./scripts/local_build.sh [pkg]      # host-only: clone nodes, rosdep, .venv, colcon build -- no Docker; preferred for locally testing the nodes 
./scripts/wizard.sh                 # host-only: setup wizard (profile, projector, camera, calibration, nodes, start)
```

Tests are the standard `ament` lint suite each package carries (`test_flake8`, `test_pep257`,
`test_copyright`) — linting *is* the test suite here:

```bash
./scripts/shell.sh
colcon test --packages-select logitech_brio
colcon test-result --all --verbose        # colcon test's own exit status hides failures; read results here
colcon test --packages-select logitech_brio --pytest-args -k flake8
```

## Architecture

**Source on the host, dependencies in the image.** `scripts/sync_nodes.sh` clones each entry of
`config/nodes.list` into `src/`, bind-mounted at `/ros2_ws/src`; each node stays its own git repo. The image
copies only the `package.xml` / `requirements.txt` of every package (staged into `docker/deps/`) and resolves
them with `rosdep` plus one `pip` call. Consequences worth preserving:

- Editing node code needs `./scripts/build_workspace.sh`, **not** an image rebuild.
- Changing a *declared dependency* does need a rebuild (`./setup.sh` handles both).
- All `requirements.txt` go into a single `pip install` on purpose: conflicting pins fail the build instead of
  one node silently overwriting another's.
- `build/`, `install/`, `log/` are named volumes, so no root-owned artefacts appear in the working tree.

**Adding a node** = one line in `config/nodes.list`, then `./setup.sh`. Nothing else — the Dockerfile and the
dependency steps are generic. A node repo needs a colcon-buildable package with a `package.xml` that declares
all its dependencies — `ament_python` or `ament_cmake` both work (`custom_interfaces` and
`azure_kinect_ros_driver` are CMake). Our own nodes are `ament_python` by convention (see below); third-party
repos keep whatever they use, but one written for an older distro may not build on this one without a fork.
PyPI deps go in an optional `requirements.txt` at the repo root. Every repo currently puts its package at the root; staging also
tolerates a package one level down, or several per repo, keying each by the declared `<name>` rather than the
directory name.

### Custom interfaces

All `.msg`, `.srv` and `.action` definitions live in one package, `custom_interfaces`, from
`ros2-par-framework-interfaces`. It is `ament_cmake` because `rosidl_generate_interfaces()` is a CMake macro —
interfaces **cannot** be generated from an `ament_python` package, so they can never be folded into a node.
The name is carried over from the older VIGITIA framework, where `from custom_interfaces.msg import ...`
appears throughout; keeping it lets those nodes port over unchanged.

Adding an interface means three edits, and the third is the one that gets forgotten:
1. the `.msg`/`.srv`/`.action` file;
2. its path in the `rosidl_generate_interfaces()` list in `CMakeLists.txt`;
3. any newly referenced external package in **both** `DEPENDENCIES` in `CMakeLists.txt` **and** as `<depend>`
   in `package.xml`. The image resolves dependencies from `package.xml` alone, so a package declared only in
   CMake builds by luck — it works while the `ros-desktop` base happens to ship it and breaks on a slimmer base.

Consumers declare `<depend>custom_interfaces</depend>` and import `from custom_interfaces.msg import Object`.
Changing an existing definition needs only `./scripts/build_workspace.sh` (colcon rebuilds dependents in
order); pulling in a new *external* message package changes a declared dependency and so needs `./setup.sh`.

**Per-setup values are parameters.** Camera index, resolution, projector display live in
`packages/par-framework-core/config/par_setup.yaml`, keyed by node name, and are handed to nodes by the launch files. Hardware
constants belong there, not in node source. A node in a namespace (the Brio sets `/camera/brio` in code) must
be keyed by its full name, e.g. `/camera/brio/logitech_brio_node` — a bare name is silently ignored.

**Node package convention** (followed by both current nodes, worth keeping): `<pkg>/<pkg>_node.py` holds the
`rclpy.node.Node` subclass — topics, `declare_parameter` with `ParameterDescriptor`, and the `main()` that
`setup.py` exposes as a `console_scripts` entry point; `<pkg>/<pkg>.py` holds device/algorithm logic free of
ROS plumbing.

### Current pipeline

`logitech_brio` publishes `sensor_msgs/Image` on `/camera/brio/image_raw` (plus `CameraInfo` on
`/camera/brio/camera_info`; the node sets its `/camera/brio` namespace in code), converted with `cv_bridge`; `surface_selector` consumes frames to mark the
projection area. `page_locator` turns `/fiducials` into `/pages` (`custom_interfaces/PageList`, every frame, corners
in camera pixels): sheets with markers `4n .. 4n+3` in their corners, located by one homography to the printed layout,
so the `marker_*` layout in `par_setup.yaml` must match the paper (default: the VIGITIA document pages, ids 96-99;
`make_page_template` prints matching pages). The image `frame_id` doubles as the camera name used to find `calibration/<CameraName>.yaml`.

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
  (`custom_interfaces/ProjectionMapping`), applied with `par_geometry.table_to_projector` /
  `projector_to_table`.

Consumers convert locally with `par_geometry`, the one place for this math. They do not call a service per point,
and images never go through a service. The mapping comes from `projection_calibration.launch.py`: the projector
shows ArUco markers (ids 50–58, `marker_ids` in `par_setup.yaml`; not 90–98, the VIGITIA document pages use 96–99) at known pixels, `fiducials_detector` finds them, and `projection_calibrator` (in
`surface_selector`) fits the homography and sends it to `projection_mapping_node`, which stores
`config/projection_mapping_<camera>.yaml` (`brio` or `kinect`) next to `par_setup.yaml`. One file per camera, because
while the camera poses are placeholders each camera has its own table plane, so a mapping only fits the camera it was
calibrated with.

Because both steps use the same plane, projection accuracy does not depend on the camera pose being exact; the
metric scale in RViz does. Points above the table (hands) land offset by parallax: the homography only covers
the plane. The clicked `/projection_corners` are a manual fallback and are named in camera terms, not
projector terms.

## Container constraints

Load-bearing settings in `docker-compose.yaml`, not conveniences: `network_mode: host` (DDS discovery uses UDP
multicast, which does not traverse the bridge network), `privileged: true` + `/dev:/dev` (USB cameras plugged
in after start), X11 socket + `$XAUTHORITY` mounts (RViz and the fullscreen projector window; the container
runs as root, so the host needs `xhost +local:root` — `setup.sh` does this).

The image has no Azure Kinect SDK (`K4A` has no rosdep rule, and there are no packages for current Ubuntu), so
`rosdep` runs with `--skip-keys K4A` and `build_workspace.sh` skips `azure_kinect_ros_driver`: the Kinect runs on the
host (`local_build.sh`), and nothing in `par_framework_core` may declare the driver, or a Brio-only build breaks.

`.env` is machine-local and gitignored; `setup.sh` generates it from `.env.example` and fills in `DISPLAY` /
`XAUTHORITY`. `ROS_DISTRO` there drives both the base image tag and the compose image tag.

## Conventions in this repo

Shell scripts source `scripts/common.sh` for `step`/`ok`/`warn`/`die` logging and `in_container`; they run
under `set -euo pipefail`, so pipelines whose left side legitimately exits non-zero need explicit handling.
Every failure message should name the command that fixes it — `setup.sh` is meant to be runnable by someone
sitting at a fresh computer.
