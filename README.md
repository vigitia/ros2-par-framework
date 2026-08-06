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

## Layout

```
setup.sh                    bootstrap everything on a new machine
config/nodes.list           which node repositories make up the framework
docker/Dockerfile           runtime environment (ROS + dependencies, no node source)
docker-compose.yaml         how the container is run: devices, X11, networking
bringup/                    ROS package: launch files + parameters (par_framework_bringup)
  launch/                   par_framework.launch.py, calibration.launch.py
  config/par_setup.yaml     camera id, resolution, projector display — edit this per setup
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
projector is on differ per machine, so they live in `bringup/config/par_setup.yaml` and are passed to nodes by
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
| `logitech_brio` | `ros2-logitech-brio` | publishes camera frames on `/camera/generic_webcam_frame_full` (+ `CameraInfo`) |
| `surface_selector` | `ros2-par-framework-calibration` | subscribes to frames, lets you mark the projection area |
| `par_framework_bringup` | this repo | launch files and per-setup parameters |

Camera frames are published **best-effort, keep-last-1** — a late frame is worthless because a newer one
already exists. Any subscriber must explicitly request `BEST_EFFORT` too; a subscriber left on the default
reliable profile is QoS-incompatible and silently receives nothing.
