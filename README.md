# ROS2 Projected Augmented Reality Framework

> Readme written together with Claude Code. Comments in the Code indicate where Claude Code was used while creating this framework. 

## 1. Overview

A Framework for people who want to build their own Projected Augmented Reality (PAR) setups. 
It is currently developed mainly for PAR-Tabletops, but the projection surface can also be a wall, floor, etc., so ProCam systems in general.

It is built on the Robot Operating System 2 (ROS2). Most components are fully interchangeable ROS 2 packages that make it modular. 
This also allows you to access the large catalogue of publicly available ROS 2 packages. 

This repository contains the frameworks' core components. 
Depending on your hardware and use case, additional components are required (see list files in config/ folder).

## 2. Hardware

### 2.1 Minimum Hardware requirements
- A Projector
- A camera (Webcam is fine to get started)

Certain applications might require special camera types (e.g. Depth, IR, Thermal, ...) or multiple projectors (currently not yet supported).

### 2.2 Hardware setup

Camera and projector pointed at the same surface. Optimal: Camera sees the entire projected image.


## 3. Installation 

Currently, only manual installation of the frameworks' core components is supported.
The optional wizard (see below) can support you with further installation steps, system setup, calibration and application launching.

While most parts of the framework should run under Windows or MacOS, some parts currently do not. 
Support for Docker is work in progress and should close this gap.
Everything is currently tested on **Ubuntu 26.04**.

### Prerequisites

Install **ROS2**. Tested with `lyrical`: https://docs.ros.org/en/lyrical/Get-Started/Installation.html

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

The wizard will guide you then through all installation, setup and calibration steps. 
It also allows you to test components and run applications without typing in terminal commands.

### Manual installation

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

Run the calibration process (with several cameras, once per camera). See the file for further instructions:
```bash
ros2 launch projection_calibration projection_corners.launch.py
```
The calibration launch files are provided in their own repository: `ros2-par-framework-calibration` 
Its README lists all of them.

Launch the framework (the wizard will help you setup custom profiles. Without it, you need to update launch entries manually):
```bash
ros2 launch par_framework_core par.launch.py
```

### Profiles

The wizard allows creation of individual profiles (physical, e.g., a different hardware setup, or digital, e.g., different apps that should launch). You can create them manually as well (ROS 2 experience required).


### Repo structure

| Path | Contents |
|---|---|
| `config/required_repos.list` | ROS2 node repositories every installation needs |
| `config/catalog_repos.list` | ROS2 node repositories an installation can add: cameras, sensor nodes, apps (you can also add your own dependencies manually. All are just ROS 2 packages) |
| `config/installed_repos.list` | (gitignored) Repositories that this installation added |
| `config/installed_ros_packages.list` | (gitignored) Released packages this installation added (e.g. camera drivers) |
| `packages/` | This repo's own ROS packages, built together with `src/` |
| `packages/par-framework-core/` | Launch files and parameters (package `par_framework_core`) |
| `packages/par-framework-core/launch/` | ROS2 launch files |
| `packages/par-framework-core/par_framework_core/` | Shared Python modules: `launch_helpers.py` (launch arguments and actions), setup files, camera types, apps, sensor nodes |
| `packages/par_camera_adapters/` | Camera types and helpers for third-party drivers (currently: webcam, RealSense, Kinect, Blackfly, event camera) |
| `packages/par_geometry/` | Helper functions for transformations: camera pixels → surface (m) → projector pixels |
| `packages/rviz_bridge/` | A ROS2 node that converts framework specific messages (e.g. `/objects`, `/fiduicals`, `/hand_landmarks`) into something RViz can display|
| `scripts/` | Setup and helper scripts |
| `setup_wizard/` | Setup wizard: Flutter app and FastAPI backend helps with setup, profile creation, calibration, as well as debugging and starting of apps |
| `src/` | Installed ROS 2 Node repositories |
| `utils/` | Helper code, e.g. for creating a calibration chessboard pattern |

## Nodes written for the ROS 2 PAR-Framework

The goal of this project is to provide reusable ROS 2 nodes for tasks essential to PAR-Applications: Projector-Camera-Calibration, processing of sensor data (object, hands, gesture, ... detection; interaction workflows, support for different input devices, tangibles, etc.).
Those custom nodes can be used alongside existing nodes of the publicly available ROS 2 catalogue (for now mainly camera drivers, but not limited to them).

Alongside them, multiple PAR-Apps are currently under development that use are built with the framework.

TODO: Add list

---

## Design decisions and conventions

### Camera conventions

**`FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA`.** Cameras are an essential part of PAR-setups. A raw 1080p frame is ~6 MB. With ROS 2's Fast DDS's default transports , most frames are lost on the way. 
This setting fixes it. It must be identical for **every** ROS 2 process: 
if only the publisher or only the subscriber has it, they don't connect at all and  nothing arrives (measured between two nodes).

**Per-setup values are parameters, not constants.** Which `/dev/video*` the camera is and which display the
projector is on differ per machine and sometimes even after a restart, so they are ROS parameters: each node declares
its defaults in its code, a camera type for a third-party driver brings its driver defaults as `parameters_file` (see `packages/par_camera_adapters`), and  a profile overrides them; the launch files pass the parameter files to the nodes.

Camera frames are published **best-effort, keep-last-1** — a late frame is worthless when a newer one
already exists. Any subscriber must explicitly request `BEST_EFFORT` too; a subscriber left on the default
reliable profile is QoS-incompatible and silently receives nothing.

### Custom messages, services and actions shared between the nodes of the PAR-Framework

They all live in one package, `par_framework_interfaces`, in its own repository.

Nodes declare `<depend>par_framework_interfaces</depend>` and import `from par_framework_interfaces.msg import Object`.
When adding a definition, register it in `rosidl_generate_interfaces()` in `CMakeLists.txt`, and declare any
newly referenced external package (`std_msgs`, `geometry_msgs`, …) in **both** the CMake `DEPENDENCIES` list
**and** `package.xml` — `rosdep` installs dependencies from `package.xml` only.

### Coordinate systems

Four coordinate systems:

| System | Unit | Origin and axes | Used for |
| --- | --- | --- | --- |
| Camera pixels | px | raw, distorted `image_raw` of the camera: origin top left, x right, y down | everything detectors find (object, contours, fiducials, hand landmarks, gestures, etc.) |
| Camera optical frame (for depth cameras) | m | the image's `header.frame_id`; x right, y down, z forward | what a depth camera measures. This data can be added to pixel coordinate outputs by the detectors. |
| Surface (projection surface), frame `world` | m | z = 0 is the surface, z points up | each camera's `projection_mapping`, the RViz output, etc. |
| Projector pixels | px | origin top left of the projected image, at the projector's resolution | what an app draws on the surface |

**`world` is the primary projection surface.** 
The surface is the plane z = 0 of `world` (on a PAR tabletop: the table), in metres, with z pointing away from it. 
Every node that needs surface coordinates uses the frame name `world`. 
The TF tree is `world` → the camera's body frame (the mount transform) → its optical frame (published by the driver). 
The camera pose calibration measures height and tilt; x, y and the rotation about the vertical come from the placeholder in `par_setup.yaml`, so the origin is the point on the surface below the camera. 
Until the poses of several cameras are measured in one common `world` (WIP!), each camera's placeholder makes its own surface plane, so every camera has its own projection mapping.

**Messages stay in the frame they were measured in.** Detectors publish camera pixels and optical-frame points,
with the image's `stamp` and `frame_id` copied into their header, and leave conversion to the consumer. 
A node that also offers surface coordinates adds them next to the pixels instead of replacing them.

**Conversions happen locally, with help from the core package `par_geometry`** (see `packages/par_geometry`).
Nodes call it on their own data:

| From → to | Function | How |
|---|---|---|
| camera pixels → surface | `camera_pixels_to_surface` | Undistorts with the camera's `camera_info` and intersects each pixel's ray with z = 0, using the camera pose from TF |
| optical frame → surface | `depth_image_to_surface` | For a whole depth image; for single points, use the pose from TF directly |
| surface → projector pixels | `surface_to_projector_pixels` | Homography from the camera's latched `projection_mapping` |
| projector pixels → surface | `projector_pixels_to_surface` | Inverse of the same homography |
| above the surface → surface | `follow_projector_rays_to_surface` | Moves a point along its projector ray onto z = 0, so `surface_to_projector_pixels` then gives the pixel that lights it |

**The surface plane links camera and projector.** The homography is fitted from markers that `camera_pixels_to_surface`
placed on the same plane, so projection accuracy does not depend on an exact camera pose.

---

## Development instructions:

### Adding a node

1. Create the repository containing your new ROS2 package. The package may sit at the repo root or in a subdirectory.
2. Add the new repository to `config/catalog_repos.list` (or to `config/required_repos.list` if every installation needs it), and to your `config/installed_repos.list`.
3. Re-run `./scripts/local_build.sh`, this will clone the repo to `src/`.

Adding a repo can also be accomplished with the wizard.

### Adding a camera

The framework knows no camera by name. It starts every camera through a **camera type**, which consists of:

- an **entry**: a small YAML file that says what the camera offers and which launch file starts it,
- a **launch file** that starts the camera's driver so that its topics end up where the framework expects them,
- optionally, a **parameter file** with driver settings the framework needs.

Nothing in `par_framework_core` or in the nodes that read the camera has to change. Once the type is built, the setup
wizard lists it and `par.launch.py` can start it.

**Where the camera type goes:**

- The driver is a third-party ROS 2 package (released or on GitHub): add the type to
  `packages/par_camera_adapters/` in this repo. This is the usual case. The steps below follow it.
- The driver is written for the framework: the driver's own repo ships the
  type. The steps are the same, with two differences listed at the end.

`packages/par_camera_adapters/` already has five types (`webcam`, `realsense`, `kinect`, `blackfly`, `event`). Copy
the closest one and adapt it: `webcam` for a simple colour camera, `realsense` or `kinect` for a depth camera. The
examples below use a new type `mycam` whose driver is the package `mycam_driver`.

#### 1. Find out what the driver does

Start the driver on its own and note:

- its package, executable and the parameters it needs (`ros2 param list`),
- the topics and services it creates (`ros2 topic list`, `ros2 service list`), e.g. `/mycam/image_raw` or a
  `/set_camera_info` at the root,
- the TF frames it publishes (`ros2 run tf2_tools view_frames`), and whether a parameter sets their names,
- whether it publishes its own factory intrinsics on `camera_info`, and whether it can open a unit by serial.

#### 2. Write the entry

Create `packages/par_camera_adapters/resource/par_framework_cameras/mycam`. The file name is the type's name, used
in `camera:=mycam` and in profiles:

```yaml
display_name: My camera                       # shown in the setup wizard
description: Colour camera through mycam_driver.
package: par_camera_adapters                  # where the launch file is installed
launch_file: camera_mycam.launch.py
parameters_file: config/mycam.yaml            # optional, see step 4
required_packages: [mycam_driver]             # the driver; the type counts as installed when it is
body_frame: link                              # the camera's TF frame is <camera>_link
streams: [image_raw, camera_info, set_camera_info]
intrinsics: calibratable                      # or factory (driver publishes them) or none
serial: none                                  # or typed / listed: several units per setup
```

`streams` lists only what the camera really offers, using the framework's names (`CAMERA_STREAM_NAMES` in
`camera_types.py`). The framework uses them to configure the detectors, e.g. a camera with
`depth_registered/image_raw` gets `use_depth`. Every key and its allowed values are explained in
`packages/par-framework-core/README.md` ("Camera types"). A wrong or unknown key stops the launch with a message
that names the fix.

#### 3. Write the launch file

Create `packages/par_camera_adapters/launch/camera_mycam.launch.py`, best as a copy of `camera_webcam.launch.py`.
The framework includes it once per camera and passes `namespace` (e.g. `/cameras/overhead`), `camera_name`
(`overhead`), `serial`, `camera_info_url` and `params_files`. The helpers in `par_framework_core.launch_helpers`
declare and read these arguments for you (`create_camera_launch_arguments`, `read_camera_launch_arguments`).

The launch file has to:

- start the driver in `namespace` and pass it `params_files`, so every topic ends up below the camera's namespace;
- remap the driver's names onto the framework's stream names, e.g. `<namespace>/mycam/image_raw` to
  `<namespace>/image_raw`, or a root `/set_camera_info` to `<namespace>/set_camera_info`;
- name the TF frames after `camera_name` (`<camera_name>_link`, `<camera_name>_optical_frame`) through the driver's
  frame parameter. If the driver publishes no optical frame, `create_optical_frame_tf_publisher` adds it;
- pass `serial` and `camera_info_url` to the driver under its own parameter names, if the driver has them.

#### 4. Add the default parameters (optional)

If the framework needs driver settings that differ from the driver's defaults (e.g. colour images in `bgr8`, a
resolution), put them into `packages/par_camera_adapters/config/mycam.yaml` and name the file in `parameters_file`.
Use `/cameras/*/<driver node name>` as the key, so the settings apply to every camera of this type:

```yaml
/cameras/*/mycam_node:
  ros__parameters:
    output_encoding: bgr8
```

`par_setup.yaml` and the profile are loaded after this file, so a profile can change any value for one setup.

#### 5. Make the driver installable

- **Released driver** (`sudo apt install ros-<distro>-mycam-driver` exists): nothing else to do. The setup wizard adds
  the packages from `required_packages` to `config/installed_ros_packages.list` when the camera is chosen. Without the
  wizard, add the line `mycam_driver` to that file yourself.
- **Driver from source** (only on GitHub): add its repo to `config/catalog_repos.list`, and to your
  `config/installed_repos.list` (the wizard does that when it installs the repo).

Do not add the driver to `package.xml` of `par_camera_adapters`: every installation would then have to install it.

#### 6. Build and try it

`setup.py` of `par_camera_adapters` already installs every entry, launch file and parameter file in these folders,
so it needs no change.

```bash
./scripts/local_build.sh
source install/setup.bash
ament_index par_framework_cameras mycam                                   # prints your entry
ros2 launch par_framework_core par.launch.py camera:=mycam rviz:=true     # the camera is named "mycam"
```

Check that it works:

- `ros2 topic list | grep /cameras/mycam/` shows the streams from your entry;
- `ros2 run tf2_ros tf2_echo world mycam_optical_frame` prints a transform;
- RViz shows the camera image.

With `intrinsics: calibratable`, calibrate the camera once with `scripts/run_cameracalibrator.sh` (usage at the top
of the script).

#### For a driver written for the framework

The driver's repo holds the entry, the launch file and its default parameters, with two differences:

- `package` in the entry is the driver's own package, and its `setup.py` installs the entry (or `CMakeLists.txt` for a
  C++ package; both shown at the top of `packages/par-framework-core/README.md`). The driver declares its
  defaults in its code, so it needs no `parameters_file`.
- The launch file imports nothing from `par_framework_core`, so the driver's repo builds without the framework. It
  declares the five launch arguments itself.
