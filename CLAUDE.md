# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Core repository of a projected augmented reality (PAR) framework on ROS 2 — a camera and a projector aimed at
the same surface. It contains **no node source**. Nodes live in their own private repos under
`github.com/vigitia` or are from other public GitHub repos; this repo declares which ones make up the framework, provides the container they run in,
and provides the launch files and per-setup parameters that compose them.

The one ROS package it does ship is `bringup/` (package `par_framework_bringup`) — launch files and
`config/par_setup.yaml` only, no nodes.

## Commands

```bash
./setup.sh                          # full bootstrap; safe to re-run, also pulls node updates
./setup.sh --skip-clone --no-cache  # rebuild image without touching src/

./scripts/shell.sh                  # shell in the container (ROS + workspace sourced)
./scripts/build_workspace.sh [pkg]  # colcon build --symlink-install, optionally one package
./scripts/launch.sh [name] [args]   # ros2 launch par_framework_bringup <name>.launch.py
./scripts/launch.sh calibration display_id:=1
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
dependency steps are generic. A node repo must be an `ament_python` package with `package.xml`, plus
`requirements.txt` at its root for PyPI deps. Every repo currently puts its package at the root; staging also
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
`bringup/config/par_setup.yaml`, keyed by node name, and are handed to nodes by the launch files. Hardware
constants belong there, not in node source.

**Node package convention** (followed by both current nodes, worth keeping): `<pkg>/<pkg>_node.py` holds the
`rclpy.node.Node` subclass — topics, `declare_parameter` with `ParameterDescriptor`, and the `main()` that
`setup.py` exposes as a `console_scripts` entry point; `<pkg>/<pkg>.py` holds device/algorithm logic free of
ROS plumbing.

### Current pipeline

`logitech_brio` publishes `sensor_msgs/Image` on `/camera/generic_webcam_frame_full` (plus `CameraInfo` on
`/camera/generic_webcam_info`), converted with `cv_bridge`; `surface_selector` consumes frames to mark the
projection area. The image `frame_id` doubles as the camera name used to find `calibration/<CameraName>.yaml`.

**QoS is a trap here.** Frames are published BEST_EFFORT / KEEP_LAST depth 1. A subscriber on the default
reliable profile — including the shorthand of passing an int depth as `qos_profile` — is QoS-incompatible and
receives nothing, silently and without error. New image subscribers must request
`QoSReliabilityPolicy.BEST_EFFORT` explicitly. (`surface_selector_node.py` currently passes an int; if that
node appears to receive no frames, this is why.)

## Container constraints

Load-bearing settings in `docker-compose.yaml`, not conveniences: `network_mode: host` (DDS discovery uses UDP
multicast, which does not traverse the bridge network), `privileged: true` + `/dev:/dev` (USB cameras plugged
in after start), X11 socket + `$XAUTHORITY` mounts (RViz and the fullscreen projector window; the container
runs as root, so the host needs `xhost +local:root` — `setup.sh` does this).

`.env` is machine-local and gitignored; `setup.sh` generates it from `.env.example` and fills in `DISPLAY` /
`XAUTHORITY`. `ROS_DISTRO` there drives both the base image tag and the compose image tag.

## Conventions in this repo

Shell scripts source `scripts/common.sh` for `step`/`ok`/`warn`/`die` logging and `in_container`; they run
under `set -euo pipefail`, so pipelines whose left side legitimately exits non-zero need explicit handling.
Every failure message should name the command that fixes it — `setup.sh` is meant to be runnable by someone
sitting at a fresh computer.
