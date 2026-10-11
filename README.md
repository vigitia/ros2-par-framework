# ros2-par-framework

Current version written together with Claude Code

Core repository of a **projected augmented reality (PAR)** framework built on ROS 2.

A PAR setup is a camera and a projector pointed at the same physical surface: the camera observes what is on
the table, ROS 2 nodes interpret it, and the projector draws back onto it. This repository is the piece that
holds such a system together — it does not contain the nodes themselves. Each node lives in its own
repository; this one describes which nodes make up the framework, provides the container they all run in, and
provides the launch files and per-setup parameters that compose them into a running system.

## Quick start on a new computer

Requires Docker, git, an SSH key registered with GitHub (the node repos are private), and a graphical session.

```bash
git clone git@github.com:vigitia/ros2-par-framework.git
cd ros2-par-framework
./setup.sh
```

`setup.sh` checks the prerequisites and tells you how to fix whatever is missing, then clones every node,
builds the image, starts the container and builds the workspace. It is safe to re-run — that is also how you
pull node updates.

```bash
./scripts/launch.sh calibration    # mark the projection surface (once per setup)
./scripts/launch.sh                # run the framework
./scripts/shell.sh                 # shell inside the container
./scripts/build_workspace.sh       # rebuild after editing node code
```

## Testing nodes locally without Docker

Requires ROS 2 installed on the host, in the same distro as `ROS_DISTRO` in `.env`, and `src/` already
cloned (`./scripts/sync_nodes.sh` or `./setup.sh`). Run the commands in **bash**, because ROS's setup scripts
don't source in fish or other shells. Stop the container first (`docker compose down`): it shares the host
network, so both copies of a node would publish on the same topics.

`./scripts/local_build.sh [pkg...]` does the cloning plus the rosdep, venv and build steps below in one go
(no Docker involved). The manual steps:

```bash
source /opt/ros/lyrical/setup.bash     # the distro from ROS_DISTRO in .env

# apt dependencies from every package.xml; --ignore-src skips packages that are in the workspace,
# --skip-keys K4A the Azure Kinect SDK, which rosdep cannot install (see notes below)
rosdep install --from-paths src packages --ignore-src -y --skip-keys K4A

# PyPI dependencies go into one shared venv in the repo root (gitignored).
# --system-site-packages keeps rclpy, cv_bridge and colcon from apt importable.
python3 -m venv --system-site-packages .venv
touch .venv/COLCON_IGNORE
source .venv/bin/activate
pip install $(printf -- '-r %s ' src/*/requirements.txt packages/*/requirements.txt)

# build through the venv's python, so node executables run with the venv's packages
python -m colcon build --symlink-install --base-paths src packages
source install/setup.bash

# Fast DDS transport for large messages, otherwise most camera frames get lost (see notes below)
export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA

ros2 launch par_framework_core calibration.launch.py
ros2 run logitech_brio logitech_brio --ros-args --params-file packages/par-framework-core/config/par_setup.yaml
```

In every new terminal, source `/opt/ros/<distro>/setup.bash`, `.venv/bin/activate` and
`install/setup.bash`, in that order, and run `export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA`. After editing node
code, re-run the `colcon build` line.

A few notes:
- **One venv on purpose.** Like the image, it puts every node's `requirements.txt` into one `pip install`, so
  conflicting version pins fail here too.
- **`python -m colcon`, not `colcon`.** Plain `colcon` builds node executables for the system Python, which
  can't see the venv, so they fail with e.g. `No module named cv2`.
- **Build output.** `build/`, `install/` and `log/` land in the repo root (gitignored). They are separate from
  the container's Docker volumes.
- **`FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA`.** A raw 1080p frame is ~6 MB. With Fast DDS's default transports
  most of these best-effort frames are lost on the way: measured on the host, only 59–160 of ~850 frames arrived
  in 15 s, while with `LARGE_DATA` 791–792 arrived at the same ~12 ms latency. The setting must be identical for
  **every** ROS process: if only the publisher or only the subscriber has it, they don't connect at all and
  nothing arrives (measured between two nodes). `ros2` CLI tools and RViz take part in DDS the same way, so they
  should need it too (not tested). The `ros2` daemon keeps the environment it was started with, so
  run `ros2 daemon stop` after changing it. The container sets it in `docker-compose.yaml`, so host terminals
  that talk to container nodes need it too. In fish, use
  `set -gx FASTDDS_BUILTIN_TRANSPORTS LARGE_DATA` instead.
- **Azure Kinect: host only.** Its driver needs the Azure Kinect Sensor SDK (`libk4a1.4` and its `-dev`
  headers, plus the udev rule `99-k4a.rules` for access without root). rosdep has no rule for it, and Microsoft
  only publishes packages for older Ubuntu releases, so it is installed by hand on the host. The Docker image
  does not have it: `./scripts/build_workspace.sh` skips the driver, and a Brio-only setup never needs it. The
  driver clone in `src/azure_kinect_ros_driver` carries local, uncommitted patches for this ROS distro (see
  `claude_usage_documentation.md`); deleting the clone loses them.

## Setup wizard (host, no Docker)

After `./scripts/local_build.sh`, the wizard walks through a setup in a desktop window (written with the help of
Claude Code):

```bash
./scripts/wizard.sh
```

1. **Profile:** a profile is one parameter file, `par_setup.yaml` (default) or `profiles/<name>.yaml` below it
   (gitignored). *Start selected profile* (or a double-click) starts it right away; *Next* sets it up. *New profile*
   starts from the defaults in `par_setup.yaml` with nothing chosen yet (display, camera, nodes), so the wizard
   asks everything anew. *Delete profile* removes one (not the default; the calibrations stay, all profiles share
   them). *Rebuild workspace* runs `local_build.sh`.
2. **Projector:** the display the projector is on, as pygame counts them (`display_id`), each with its connector,
   model, resolution, refresh rate, position and whether it is the primary one. *Identify* shows each display's
   number on it, *Show test pattern* a grid on the chosen one.
3. **Camera:** Brio or Azure Kinect (one at a time), with a live preview; for the Kinect also its settings
   (resolution, depth mode, fps, colour controls, point cloud).
4. **Calibration:** first *automatic* or *manual*, then the steps for that choice, each with its status and *Run*:
   - automatic: the Kinect pose measured from the clear table (the Brio's pose is entered by hand), then the
     projector mapping from projected markers;
   - manual: the camera's distance to the table and its angle, then clicking the four corners;
   - with the Brio, its checkerboard intrinsics come first.
5. **Nodes:** which detectors and whether RViz run.
6. **Start:** runs `par.launch.py` with the profile; closing the wizard stops everything.

Every page stores its choices in the profile when you press *Next*, comments kept. The camera and the nodes go
into the `par_launch` section that `par.launch.py` reads, so a profile also starts without the wizard:
`ros2 launch par_framework_core par.launch.py params_file:=<profile>`.

## Layout

```
setup.sh                    bootstrap everything on a new machine
config/nodes.list           which node repositories make up the framework
docker/Dockerfile           runtime environment (ROS + dependencies, no node source)
docker-compose.yaml         how the container is run: devices, X11, networking
packages/                   this repo's own ROS packages, built together with src/
  par-framework-core/       launch files + parameters (package par_framework_core)
    launch/                 par.launch.py (the framework: camera and nodes from the profile's par_launch
                            section, each overridable per run, e.g. camera:=kinect rviz:=true),
                            calibration.launch.py, projection_calibration.launch.py,
                            camera_pose_calibration_kinect.launch.py
    config/par_setup.yaml   camera id, resolution, projector display — edit this per setup
    par_framework_core/     launch_helpers.py: node start functions shared by the launch files
  par_geometry/             library: camera pixels -> table (m) -> projector pixels
  projection_corners/       node: holds the projection corners, publishes them on /projection_corners
  projection_mapping/       node: holds the table-to-projector homography, publishes /projection_mapping
  rviz_bridge/              node: framework outputs RViz cannot show (e.g. /objects) as markers
  par_setup_wizard/         desktop setup wizard (PySide6), started with scripts/wizard.sh
scripts/                    the individual steps setup.sh runs, usable on their own
src/                        node repositories, cloned by setup.sh (not tracked here)
```

## How it fits together

**Node source lives on the host.** `scripts/sync_nodes.sh` clones each entry of `config/nodes.list` into
`src/`, which is bind-mounted at `/ros2_ws/src`. Each node stays a normal git repository you edit in your IDE
and commit from; changing node code needs `./scripts/build_workspace.sh`, never an image rebuild.

**The image holds dependencies only.** The build copies just the `package.xml` and `requirements.txt` of each
package (staged into `docker/deps/`) and resolves them with `rosdep` and a single `pip` invocation. Editing
code therefore does not invalidate those slow layers — only changing a declared dependency does. The single
pip call is deliberate: if two nodes pin conflicting versions, the build fails instead of one node silently
overwriting the other's pin.

**Per-setup values are parameters, not constants.** Which `/dev/video*` the camera is and which display the
projector is on differ per machine, so they live in `packages/par-framework-core/config/par_setup.yaml` and are passed to nodes by
the launch files.

### Adding a node

1. Create the node repository (an `ament_python` package with a `package.xml`, and a `requirements.txt` at its
   root for PyPI dependencies). The package may sit at the repo root or in a subdirectory.
2. Add one line to `config/nodes.list`.
3. Re-run `./setup.sh`.

### Custom messages, services and actions

They all live in one package, `custom_interfaces`, in its own repository. It has to be `ament_cmake`:
`rosidl_generate_interfaces()` is a CMake macro, so interface generation is not possible from an
`ament_python` package and cannot be added to a node package.

Nodes declare `<depend>custom_interfaces</depend>` and import `from custom_interfaces.msg import Object`.
When adding a definition, register it in `rosidl_generate_interfaces()` in `CMakeLists.txt`, and declare any
newly referenced external package (`std_msgs`, `geometry_msgs`, …) in **both** the CMake `DEPENDENCIES` list
**and** `package.xml` — the container image installs dependencies from `package.xml` only.

### Current packages

| Package | Repository | Role |
| --- | --- | --- |
| `custom_interfaces` | `ros2-par-framework-interfaces` | shared message, service and action definitions |
| `logitech_brio` | `ros2-logitech-brio` | publishes camera frames on `/camera/brio/image_raw` (+ `/compressed`) and `CameraInfo` on `/camera/brio/camera_info`; the launch files remap them onto the framework's `/camera/...` topics |
| `surface_selector` | `ros2-par-framework-calibration` | subscribes to `/camera/image_raw`, lets you mark the projection area; `projection_calibrator` calibrates the table-to-projector mapping automatically from projected ArUco markers seen on `/fiducials` |
| `object_detector` | `ros2-par-framework-object-detection` | detects objects in `/camera/image_raw/compressed` (raw image for cameras without JPEGs), publishes them in image pixels on `/objects` |
| `fiducials_detector` | `ros2-par-framework-fiducials` | detects fiducial markers in `/camera/image_raw`, publishes them on `/fiducials` |
| `hand_landmarks` | `ros2-par-framework-hand-landmarks` | tracks hands in `/camera/image_raw` with MediaPipe, publishes their landmarks in image pixels on `/hand_landmarks` |
| `par_framework_core` | this repo | launch files and per-setup parameters |
| `par_geometry` | this repo | library: `pixels_to_table`, `table_to_projector`, `projector_to_table` — the coordinate conversions every node shares |
| `projection_mapping` | this repo | stores the homography from `projection_calibrator` in `config/calibration/extrinsics/projection_mapping_<camera>.yaml` (one per camera), publishes it latched on `/projection_mapping` |
| `projection_corners` | this repo | stores the corners from `surface_selector` in `config/calibration/extrinsics/projection_corners_<camera>.yaml`, publishes them latched on `/projection_corners` |
| `par_setup_wizard` | this repo | desktop wizard: projector display, camera, calibration, nodes and start, stored in named profiles of `par_setup.yaml` |
| `rviz_bridge` | this repo | projects `/objects`, `/hand_landmarks`, `/fiducials`, `/projection_corners` and `/projection_mapping` onto the table as `/objects/markers`, `/hand_landmarks/markers`, `/fiducials/markers`, `/projection_corners/markers` and `/projection_mapping/markers` for RViz |

Camera frames are published **best-effort, keep-last-1** — a late frame is worthless because a newer one
already exists. Any subscriber must explicitly request `BEST_EFFORT` too; a subscriber left on the default
reliable profile is QoS-incompatible and silently receives nothing.
