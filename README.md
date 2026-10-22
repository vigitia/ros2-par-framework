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
