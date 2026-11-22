# CLAUDE.md

<!-- Co-authored by Claude Code -->

Guidance for Claude Code (claude.ai/code) in this repository.

## What this repository is

Core repo of a projected augmented reality (PAR) framework on ROS 2: one or multiple cameras and a projector aimed at the same surface. It declares which repos make up a setup (`config/required_repos.list` for every installation, `config/catalog_repos.list` for the optional ones) and holds the launch files, the per-setup parameters and the source every setup builds.

**Where a package belongs** (first yes decides):

1. Useful outside the framework (camera driver, detector)? → own repo, or a public third-party repo.
2. Shared library or setup/inspection tooling (`par_geometry`, `rviz_bridge`)? → this repo, its own directory under
   `packages/` (`local_build.sh` takes `packages/` as a whole, no path changes needed).

3. Otherwise a framework capability (calibration, projection mask) → own repo, listed in
   `config/required_repos.list` if every setup needs it, else in `config/catalog_repos.list`. Nothing here declares
   it as a dependency; `par.launch.py` finds what is installed through the ament index (see "Ament index entries"
   below; the projection calibration server through `has_resource('packages', …)`) and otherwise logs which repo to
   add.

<!-- Written with the help of Claude Code -->
`packages/par-framework-core/` (package `par_framework_core`) holds `launch/par.launch.py`, `config/par_setup.yaml`
and the Python modules the launch files of every repo share, no nodes and no camera types. `launch_helpers` is the
only module that reads the launch context; the logic lives in modules that import nothing from `launch`:
`setup_files` (config paths, parameter files), `par_launch_cameras`, `camera_types`, `camera_poses`, `par_apps`,
`sensor_nodes`, `connected_displays` (finds the projector by its EDID). Camera types for third-party drivers are in
`packages/par_camera_adapters/` (kept in this repo for now; one repo per camera type, like `logitech_brio`, is the
alternative). `setup_wizard/` is the setup wizard (Flutter app + FastAPI backend, started by
`scripts/start_setup_wizard.sh`): installation, profiles, calibration, starting apps.

<!-- Written with the help of Claude Code -->
Two `config/` folders: the repo root's `config/` holds only the `*.list` files; parameters, profiles and calibrations
are in `packages/par-framework-core/config/` (`setup_files.get_path_in_config_folder`). Below, `config/profiles/` and
`config/calibration/` mean the latter.

**Calibration is optional.** The framework runs uncalibrated, in camera pixels. Camera pose, projection corners,
projection mapping and the server that publishes them latched live in `ros2-par-framework-calibration` (packages
`projection_calibration`, `camera_pose_calibrator`, `projection_calibration_server`, one level down), together with
the calibration launch files (`projection_corners.launch.py` and `projection_calibration.launch.py` in
`projection_calibration`, `camera_pose_calibration_{sheet,depth}.launch.py` in `camera_pose_calibrator`); they build on
`launch_helpers`. A node that can work without calibration must: publish camera pixels always, add
surface or projector coordinates only when calibrated (e.g. `gesture_detector`: `pixel` always, `position` with
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
ros2 launch projection_calibration projection_corners.launch.py projector_display_id:=1
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

<!-- Written with the help of Claude Code -->
**Ament index entries.** The framework finds cameras, sensor processing nodes and apps by the marker file they install
under `share/ament_index/resource_index/<type>/` (source: `resource/<type>/<name>`, listed in `setup.py`
`data_files`), whose content is a YAML entry: `par_framework_cameras` (camera types, e.g. `brio`, `kinect`),
`par_framework_sensor_nodes` (detectors, `page_locator`, `projection_mask`; key `required_sensor_nodes`) and
`par_framework_apps` (e.g. `demo_app`, the rendering manager; keys such as `inputs`, the camera topics it reads).
Entry formats: `packages/par-framework-core/README.md`. A sensor node's package name is its `par_launch` switch.

**Released packages** (`v4l2_camera`, `realsense2_camera`, `spinnaker_camera_driver`) are not cloned: they are rosdep
keys in the gitignored `config/installed_ros_packages.list` (this installation's camera drivers; the wizard writes
the `required_packages` of a chosen camera type that no catalog repo provides), turned into a generated `package.xml`
by `write_ros_packages_manifest` in `scripts/common.sh`. There is no required list for released packages: one every
installation needs goes into the `package.xml` of the package that uses it. So camera drivers stay optional and `par_framework_core`
declares none. The Kinect SDK is installed by hand; the driver fork's `package.xml` does not declare it (rosdep has
no rule for `K4A`), so core needs no `--skip-keys`. Nothing in core may declare the Kinect driver, or a Brio-only
build breaks. `spinnaker_camera_driver` brings its own copy of the Spinnaker
SDK. `metavision_driver` (event camera) brings OpenEB; a SilkyEvCam's plugin is installed by hand and found through
`MV_HAL_PLUGIN_PATH` (README, "Event camera").

**Interfaces.** All `.msg`/`.srv`/`.action` live in `par_framework_interfaces` (repo `ros2-par-framework-interfaces`),
which is `ament_cmake` because `rosidl_generate_interfaces()` is a CMake macro, so interfaces can never move into a
Python node. Nodes ported from VIGITIA import it as `custom_interfaces`; rename those imports and `<depend>` entries.
Adding an interface takes three edits: (1) the file, (2) its path in `rosidl_generate_interfaces()`, (3) any newly
referenced external package in **both** `DEPENDENCIES` in `CMakeLists.txt` **and** `<depend>` in `package.xml`. The
third gets forgotten: rosdep reads only `package.xml`, so a CMake-only dependency builds by luck. Changing a
definition or adding an external dependency needs `./scripts/local_build.sh`.

**Per-setup values are parameters**, never hardware constants in node source. Each node declares its defaults in its
own code (`declare_parameter` with a `ParameterDescriptor`); a camera type for a third-party driver brings the driver
defaults the framework needs as its entry's `parameters_file` (`packages/par_camera_adapters/config/`), loaded before
`packages/par-framework-core/config/par_setup.yaml`, which holds only the framework's own `par_launch` and
`placeholder_camera_pose`. A profile overrides any of them, keyed by node name.
<!-- Written with the help of Claude Code -->
A namespaced node needs its full name: `/cameras/*/<node>` for every camera, `/cameras/<camera>/<node>` for one
(e.g. `/cameras/overhead/fiducials_detector_node`); a bare name is silently ignored. Another physical setup is a **profile** (`profile:=<name>`): `config/profiles/<name>.yaml`
(gitignored) holds only the keys that differ, nodes get `[params_file, profile]` (ROS merges, later wins), and what
the launch files read themselves (`par_launch`, placeholder poses) goes through `setup_files.read_merged_parameters`.
Calibrations are per profile: extrinsics in `calibration/extrinsics/<profile>/`, intrinsics in
`calibration/intrinsics/<profile>/`, named per camera unit (a Brio with `serial`: `camera_info_brio_<serial>.yaml`;
a profile pins its camera's serial). Launch code takes parameter files from `get_params_file_paths`, never from
`params_file` alone.

**Node package convention:** `<pkg>/<pkg>_node.py` does only the ROS work (the `Node` subclass, topics, services,
`declare_parameter` with `ParameterDescriptor`, message conversion, `main()` as `console_scripts` entry point). All
other logic lives in other modules (`<pkg>/<pkg>.py` or more) that import nothing from `rclpy` or message packages and
take plain Python/NumPy values, so it is testable with plain pytest and reusable outside the node.

### Cameras

<!-- Written with the help of Claude Code -->
A setup has one or more **named cameras**: `par_launch.cameras` maps a name to a unit, `<type>[:<serial>]` (e.g.
`{overhead: 'blackfly:22260470'}`); the first is the main camera (RViz's image). `camera:=` starts one camera instead
of all: a name from that list, or `<type>[:<serial>]` for a unit the profile does not name (e.g. `camera:=kinect`).
`camera_only:=true` starts just the cameras and their mount transforms. Each camera runs in `/cameras/<name>/`, and its
outputs and calibration live there too.

Every camera offers its streams under the same names relative to its namespace (`CAMERA_STREAM_NAMES` in
`camera_types.py`): `image_raw`, `camera_info`, `set_camera_info`, optionally `image_raw/compressed`, from a depth
camera `depth_registered/image_raw` (depth on the colour image's pixel grid), from a camera with infrared on that grid
`ir/image_raw` (the Kinect's driver transforms its infrared onto the colour grid, `ir_to_rgb/image_raw`, computed only
while subscribed). A depth camera's own infrared and depth, unregistered and aligned pixel by pixel, are
`depth_sensor/ir/image_raw`, `depth_sensor/depth/image_raw` and `depth_sensor/camera_info`; its pose relative to the
colour camera is in TF (`hand_landmarks` with `use_ir` detects there and moves the landmarks into the colour image).
The camera's entry lists the streams it offers (`streams`).

Nodes use **relative** topic names (`image_raw`, `fiducials`, `projection_mapping`). `par.launch.py` starts each sensor
node once per camera its `par_launch` key lists (e.g. `fiducials_detector: [overhead]`), as `<package>_node` in that
camera's namespace, where the names resolve to that camera's streams (`/cameras/overhead/image_raw`) and its outputs
become the camera's (`/cameras/overhead/fiducials`). Nodes started outside a camera namespace (the camera pose
calibrators) get `launch_helpers.create_camera_stream_remappings`. Apps read cameras through their entry's `inputs`,
bound per app with `par_launch.app_inputs`. One `rviz_bridge` per camera puts every camera's detections into the
same RViz displays. Another topic is chosen by remapping, never by parameter.

`par.launch.py` sets `use_compressed` (`object_detector`, `fiducials_detector`, `page_locator` take
`image_raw/compressed`) for a camera whose `streams` include `image_raw/compressed`, and `use_depth` for one with
`depth_registered/image_raw` (`DETECTOR_PARAMETER_BY_CAMERA_STREAM`). Drivers keep their own topics; the camera type's
launch file maps them onto the stream names below the camera's namespace. A new camera = a camera type (entry +
launch file, format in `packages/par-framework-core/README.md`) in the driver's repo, or in
`packages/par_camera_adapters/` for a third-party driver. The event camera (type `event`) has no frames:
`event_camera_renderer` collects its events into `image_raw`, the raw events are on `events`, and there is no
`camera_info`.

<!-- Written with the help of Claude Code -->
Intrinsics: per unit, `config/calibration/intrinsics/<profile>/camera_info_<type>[_<serial>].yaml` (gitignored;
without a profile the shared `calibration/intrinsics/`), set as `camera_info_url` by
`launch_helpers.get_camera_info_url` for camera types whose entry says `intrinsics: calibratable`, written by
`scripts/run_cameracalibrator.sh`. Cameras with `intrinsics: factory` (Kinect, RealSense) publish their own.

`page_locator` turns `fiducials` into `pages` (`PageList`, corners in camera pixels, clockwise from the top left)
for sheets with markers `4n .. 4n+3`; the `marker_*` parameters must match the paper (default:
upright markers, `4n + k` in page corner `k` clockwise from the top left; `make_page_template` prints them; old
VIGITIA sheets need their own parameters, see page_locator's README).

**QoS traps:**
- Frames are BEST_EFFORT / KEEP_LAST depth 1. A reliable subscriber (including passing an int depth as
  `qos_profile`) silently receives nothing; request `QoSReliabilityPolicy.BEST_EFFORT`. For third-party subscribers
  that can't be changed, set the Brio's `qos_reliability: reliable` (and `encoding: rgb8`) in the profile.
<!-- Written with the help of Claude Code -->
- Each camera's `projection_corners` and `projection_mapping` (`/cameras/<name>/…`, one projection calibration server
  per camera) are latched (RELIABLE + TRANSIENT_LOCAL, depth 1). Subscribers must request
  `QoSDurabilityPolicy.TRANSIENT_LOCAL`, or a node started later sees nothing.

### Coordinates: camera pixels → surface → projector pixels

Detectors publish raw camera pixels. The common currency is the **surface plane in metres**, z = 0 of `world` (each
camera's pose: measured `camera_pose_<camera>.yaml`, else `placeholder_camera_pose` in `par_setup.yaml`). Consumers
convert locally with `par_geometry`, the one place for this math (no service per point, no images through services):
- camera pixels → surface: `camera_pixels_to_surface` (undistorts with `camera_info`, intersects the rays with the plane via TF);
<!-- Written with the help of Claude Code -->
- surface ↔ projector pixels: `surface_to_projector_pixels` / `projector_pixels_to_surface`, with the homography on the camera's latched
  `projection_mapping` (`ProjectionMapping`).

<!-- Written with the help of Claude Code -->
The mapping comes from `ros2 launch projection_calibration projection_calibration.launch.py` (with several cameras,
`camera:=<name>` picks the one to calibrate): the projector shows
ArUco ids 0–8 (`marker_ids`; must not clash with the document pages' 96–99), `fiducials_detector` finds them,
`projection_calibrator` (in `projection_calibration`) fits the homography, and `projection_calibration_server_node`
stores it as `config/calibration/extrinsics/<profile>/projection_mapping_<camera name>.yaml`, next to
`camera_pose_<camera name>.yaml` and the projection corners (`setup_files.get_extrinsics_relative_path`). One file per
camera, named after the camera, not the unit (the pose belongs to the mount), because while the poses are placeholders
each camera has its own surface plane.

Both steps use the same plane, so projection accuracy does not depend on an exact camera pose (RViz's metric scale
does). Points above the surface (hands) land offset by parallax. A second run,
`projection_calibration.launch.py camera:=kinect projector_center:=true`, adds the projector's optical centre
(`projector_center`, valid when `projector_center_valid`) from marker rays located in 3D by the depth camera; with it,
`par_geometry.follow_projector_rays_to_surface` moves a raised point along its projector ray onto the surface. Re-running the homography
clears the centre. The quick path, `projection_corners.launch.py` (`projection_corner_selector`), stores the clicked
`projection_corners` (camera pixels, the projector image's top left first) and a mapping computed from them, exact
at the four corners only. Whichever ran last owns the mapping; the calibration repo's README lists the levels.

### Projector masks

<!-- Written with the help of Claude Code -->
mono8 images in projector pixels, BEST_EFFORT depth 1 (`projector/mask` at the projector's resolution, the content
mask downscaled). Apps apply `projector/mask` themselves.
- `/cameras/<name>/projector/mask` (from the `projection_mask` sensor node on that camera): 255 where the light would
  hit something higher than
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
