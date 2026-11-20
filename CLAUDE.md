# CLAUDE.md

<!-- Co-authored by Claude Code -->

Guidance for Claude Code (claude.ai/code) in this repository.

## What this repository is

Core repo of a projected augmented reality (PAR) framework on ROS 2: a camera and a projector aimed at the same
surface. It declares which repos make up a setup (`config/required_repos.list` for every installation,
`config/catalog_repos.list` for the optional ones) and holds the launch files, the per-setup parameters and the
source every setup builds.

**Where a package belongs** (first yes decides):

1. Useful outside the framework (camera driver, detector)? → own repo, or a public third-party repo.
2. Shared library or setup/inspection tooling (`par_geometry`, `rviz_bridge`)? → this repo, its own directory under
   `packages/` (`local_build.sh` takes `packages/` as a whole, no path changes needed).
3. Otherwise a framework capability (calibration, projection mask) → own repo, listed in
   `config/required_repos.list` if every setup needs it, else in `config/catalog_repos.list`. Nothing here declares
   it as a dependency; `par.launch.py` starts it only when installed (`has_resource('packages', …)`), otherwise it
   logs which repo to add.

`packages/par-framework-core/` (package `par_framework_core`) holds launch files and `config/par_setup.yaml` only,
no nodes and no camera types. Camera types for third-party drivers are in `packages/par_camera_adapters/`
(kept in this repo for now; one repo per camera type, like `logitech_brio`, is the alternative).

**Calibration is optional.** The framework runs uncalibrated, in camera pixels. Camera pose, projection corners,
projection mapping and the server that publishes them latched live in `ros2-par-framework-calibration` (packages
`projection_calibration`, `camera_pose_calibrator`, `projection_calibration_server`, one level down); the calibration
launch files here need that repo. A node that can work without calibration must: publish camera pixels always, add
table or projector coordinates only when calibrated (e.g. `gesture_detector`: `pixel` always, `position` with
`position_valid`). Camera intrinsics are not part of this split, they belong to the camera (`camera_info`), so
`launch_helpers` (`camera_info_url`) and `scripts/run_cameracalibrator.sh` stay here.

## Commands

Everything runs on the host, in bash (ROS's setup scripts only source there).

```bash
./scripts/local_build.sh [pkg]      # clone nodes, rosdep, .venv, colcon build --symlink-install; safe to re-run

# by hand, in each new bash terminal:
source /opt/ros/lyrical/setup.bash && source .venv/bin/activate && source install/setup.bash
export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA
ros2 launch par_framework_core par.launch.py camera:=kinect rviz:=true   # one entry point; args override par_launch per run
ros2 launch par_framework_core calibration.launch.py display_id:=1
```

Tests are the `ament` lint suite each package carries (`test_flake8`, `test_pep257`, `test_copyright`):

```bash
colcon test --packages-select logitech_brio
colcon test-result --all --verbose        # colcon test's own exit status hides failures; read results here
colcon test --packages-select logitech_brio --pytest-args -k flake8
```

## Architecture

**Build.** `scripts/sync_nodes.sh` clones each entry of `config/required_repos.list` and of the gitignored
`config/installed_repos.list` (this installation's choice from the catalog) into `src/` (each stays its own git repo).
`local_build.sh` resolves every `package.xml` with rosdep, installs all `requirements.txt` in **one** `pip` call into
`.venv` (`--system-site-packages`, so apt's rclpy stays importable) so conflicting pins fail instead of silently
overwriting each other, then builds with `.venv/bin/python -m colcon`.

**Adding a node** = one line in `config/catalog_repos.list` (or `config/required_repos.list` if every setup needs it),
installed by the setup wizard or by copying the line into `config/installed_repos.list`, then
`./scripts/local_build.sh`. The repo needs a colcon-buildable package whose `package.xml` declares all dependencies
(`ament_python` or `ament_cmake`; our own are `ament_python`), PyPI deps in an optional root `requirements.txt`.
Packages may sit at the root, one level down, or several per repo; each is keyed by its `<name>`. A third-party repo
written for an older distro may need a fork.

**Released packages** (`v4l2_camera`, `realsense2_camera`, `spinnaker_camera_driver`) are not cloned: they are rosdep
keys in `config/required_ros_packages.list` (every installation) and the gitignored
`config/installed_ros_packages.list` (this installation's camera drivers), turned into a generated `package.xml` by
`write_ros_packages_manifest` in `scripts/common.sh`. So camera drivers stay optional and `par_framework_core`
declares none. The Kinect SDK (`K4A`) is installed by hand (rosdep runs with `--skip-keys K4A`); nothing in core may
declare the Kinect driver, or a Brio-only build breaks. `spinnaker_camera_driver` brings its own copy of the Spinnaker
SDK. `metavision_driver` (event camera) brings OpenEB; a SilkyEvCam's plugin is installed by hand and found through
`MV_HAL_PLUGIN_PATH` (README, "Event camera").

**Interfaces.** All `.msg`/`.srv`/`.action` live in `par_framework_interfaces` (repo `ros2-par-framework-interfaces`),
which is `ament_cmake` because `rosidl_generate_interfaces()` is a CMake macro, so interfaces can never move into a
Python node. Nodes ported from VIGITIA import it as `custom_interfaces`; rename those imports and `<depend>` entries.
Adding an interface takes three edits: (1) the file, (2) its path in `rosidl_generate_interfaces()`, (3) any newly
referenced external package in **both** `DEPENDENCIES` in `CMakeLists.txt` **and** `<depend>` in `package.xml`. The
third gets forgotten: rosdep reads only `package.xml`, so a CMake-only dependency builds by luck. Changing a
definition or adding an external dependency needs `./scripts/local_build.sh`.

**Per-setup values are parameters** in `packages/par-framework-core/config/par_setup.yaml`, keyed by node name, never
hardware constants in node source. A namespaced node needs its full name (e.g. `/camera/brio/logitech_brio_node`); a
bare name is silently ignored. Another physical setup is a **profile** (`profile:=<name>`): `config/profiles/<name>.yaml`
(gitignored) holds only the keys that differ, nodes get `[params_file, profile]` (ROS merges, later wins), and what
the launch files read themselves (`par_launch`, placeholder poses) goes through `launch_helpers.read_merged_parameters`.
Calibrations are per profile: extrinsics in `calibration/extrinsics/<profile>/`, intrinsics in
`calibration/intrinsics/<profile>/`, named per camera unit (a Brio with `serial`: `camera_info_brio_<serial>.yaml`;
a profile pins its camera's serial). Launch code takes parameter files from `get_params_file_paths`, never from
`params_file` alone.

**Node package convention:** `<pkg>/<pkg>_node.py` does only the ROS work (the `Node` subclass, topics, services,
`declare_parameter` with `ParameterDescriptor`, message conversion, `main()` as `console_scripts` entry point). All
other logic lives in other modules (`<pkg>/<pkg>.py` or more) that import nothing from `rclpy` or message packages and
take plain Python/NumPy values, so it is testable with plain pytest and reusable outside the node.

### Cameras

Framework nodes subscribe to neutral names: `/camera/image_raw`, `/camera/camera_info`, `/camera/set_camera_info` and,
from a depth camera, `/camera/depth_registered/image_raw` (depth on the colour image's pixel grid), and from a camera
with infrared on that grid, `/camera/ir/image_raw` (the Kinect's driver transforms its infrared onto the colour grid,
`ir_to_rgb/image_raw`, computed only while subscribed). A depth camera's own infrared and depth, unregistered and
aligned pixel by pixel, are `/camera/depth_sensor/ir/image_raw`, `/camera/depth_sensor/depth/image_raw` and
`/camera/depth_sensor/camera_info`; its pose relative to the colour camera is in TF (`hand_landmarks` with `use_ir`
detects there and moves the landmarks into the colour image).
`object_detector` and `fiducials_detector` with `use_compressed` take `/camera/image_raw/compressed` instead
(`par.launch.py` sets it for the Brio, the only driver publishing JPEGs). Drivers keep their own topics; launch files
remap them with `launch_helpers.CAMERA_DRIVER_REMAPPINGS`, the only place that knows them. A new camera = a camera
type (entry + launch file, `templates/par_camera/`) in the driver's repo, or in `packages/par_camera_adapters/`
for a third-party driver. Nodes hard-code the neutral names; another topic is chosen by
remapping, not by parameter. The event camera (`camera:=event`) has no frames: `event_camera_renderer` collects its
events into `/camera/image_raw`, the raw events are on `/camera/events`, and there is no `camera_info`.

Intrinsics: `config/calibration/intrinsics/<profile>/camera_info_<camera>.yaml` (gitignored; without a profile the
shared `calibration/intrinsics/`), set as `camera_info_url` by `launch_helpers.get_camera_info_url`, written by
`scripts/run_cameracalibrator.sh`. The Kinect publishes its factory calibration instead.

`page_locator` turns `/fiducials` into `/pages` (`PageList`, corners in camera pixels, clockwise from the top left)
for sheets with markers `4n .. 4n+3`; the `marker_*` layout in `par_setup.yaml` must match the paper (default:
upright markers, `4n + k` in page corner `k` clockwise from the top left; `make_page_template` prints them; old
VIGITIA sheets need their own parameters, see page_locator's README).

**QoS traps:**
- Frames are BEST_EFFORT / KEEP_LAST depth 1. A reliable subscriber (including passing an int depth as
  `qos_profile`) silently receives nothing; request `QoSReliabilityPolicy.BEST_EFFORT`. For third-party subscribers
  that can't be changed, set the Brio's `qos_reliability: reliable` (and `encoding: rgb8`) in `par_setup.yaml`.
- `/projection_corners` and `/projection_mapping` are latched (RELIABLE + TRANSIENT_LOCAL, depth 1). Subscribers must
  request `QoSDurabilityPolicy.TRANSIENT_LOCAL`, or a node started later sees nothing.

### Coordinates: camera pixels → table → projector pixels

Detectors publish raw camera pixels. The common currency is the **table plane in metres**, z = 0 of `world` (each
camera's pose: measured `camera_pose_<camera>.yaml`, else `placeholder_camera_pose` in `par_setup.yaml`). Consumers
convert locally with `par_geometry`, the one place for this math (no service per point, no images through services):
- camera pixels → table: `pixels_to_table` (undistorts with `camera_info`, intersects the rays with the plane via TF);
- table ↔ projector pixels: `table_to_projector` / `projector_to_table`, with the homography on the latched
  `/projection_mapping` (`ProjectionMapping`).

The mapping comes from `projection_calibration.launch.py`: the projector shows ArUco ids 0–8 (`marker_ids`; must
not clash with the document pages' 96–99), `fiducials_detector` finds them, `projection_calibrator` (in
`projection_calibration`) fits the homography, and `projection_calibration_server_node` stores it as
`config/calibration/extrinsics/projection_mapping_<camera>.yaml`, next to `camera_pose_<camera>.yaml` and the
projection corners. One file per camera, because while the poses are placeholders each camera has its own table plane.

Both steps use the same plane, so projection accuracy does not depend on an exact camera pose (RViz's metric scale
does). Points above the table (hands) land offset by parallax. A second run,
`projection_calibration.launch.py camera:=kinect projector_center:=true`, adds the projector's optical centre
(`projector_center`, valid when `projector_center_valid`) from marker rays located in 3D by the depth camera; with it,
`par_geometry.project_to_table` moves a raised point along its projector ray onto the table. Re-running the homography
clears the centre. The quick path, `calibration.launch.py` (`projection_corner_selector`), stores the clicked
`/projection_corners` (camera pixels, the projector image's top left first) and a mapping computed from them, exact
at the four corners only. Whichever ran last owns the mapping; the calibration repo's README lists the levels.

### Projector masks

mono8 images in projector pixels, BEST_EFFORT depth 1 (`/projector/mask` at the projector's resolution, the content
mask downscaled). Apps apply `/projector/mask` themselves.
- `/projector/mask` (from the `projection_mask` capability): 255 where the light would hit something higher than
  `min_height`; apply with `frame[mask > 0] = 0`. Needs a depth camera and the mapping; without the projector centre
  it assumes light straight down.
- `/projector/content_mask` (optional, from `rendering_manager_bridge` with `content_mask_enabled`): 255 where the
  projector sends light, 0 where the output is black, read back by the rendering manager from the frame it draws.
  Downscaled: one pixel per `content_mask_downscale_factor` projector pixels in each direction, so scale coordinates by
  the mask's size, not the projector's. Stamped when the frame was drawn; the projector shows it later (delay not
  measured yet). Nothing consumes it yet. Reading the screen from outside was rejected (Wayland allows it only through
  the portal with user consent, not from a container, and with extra delay).

## Conventions

Shell scripts source `scripts/common.sh` (`step`/`ok`/`warn`/`die`, `ROS_DISTRO`) and run under `set -euo pipefail`,
so pipelines whose left side may legitimately exit non-zero need explicit handling. Every failure message names the
command that fixes it: `local_build.sh` must work for someone at a fresh computer.

Python lines may be up to **99 characters** in every package of the framework (`ament_flake8`'s default, which each
package's `test_flake8` checks). Use that width: never wrap or reformat code to a shorter limit (79, 88), and don't
run a formatter that does.
