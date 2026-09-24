# Claude Code usage documentation

Changes made with Claude Code in this repository and the decisions behind them.

## 2026-09-17: ignore `.venv/` for host-side testing

**What changed:** `.gitignore` now ignores `/.venv/`.

**Why:** To test the nodes in `src/` without Docker, you build with host ROS (`/opt/ros/lyrical`) plus one
venv in the repo root for the PyPI dependencies. Ubuntu 26.04 blocks system-wide `pip install`. Without this
entry the venv shows up as untracked in `git status`.

**Decisions:**
- *One shared venv instead of one per node repo.* It matches the image, which installs every
  `requirements.txt` in a single `pip install`, so version conflicts show up locally too. A launch file also
  runs all nodes in one environment, so separate venvs per node wouldn't work at runtime.
- *`--system-site-packages`* so the venv can import `rclpy`, `cv_bridge` and colcon from apt.
- *Build with `python -m colcon` from the activated venv* so the node startup scripts use the venv's Python.
  The alternative, `pip --break-system-packages`, was rejected because it mixes PyPI packages into the
  system Python.
- *Anchored `/.venv/`* to match the style of the other root-level entries (`/build/` etc.).

## 2026-09-17: README section "Testing nodes locally without Docker"

**What changed:** `README.md` has a new section, right after the quick start, with the host-side workflow:
rosdep, the shared venv, `python -m colcon build`, launching, and which scripts to source in a new terminal.

**Decisions:**
- *Placed after the quick start instead of in a separate doc,* because it is an alternative way to run the
  same framework, and readers look for it next to the Docker commands.
- *`src/*/requirements.txt` instead of listing today's two nodes,* so the section stays correct when nodes are
  added to `config/nodes.list`. `printf -- '-r %s '` turns each file into a `-r <file>` argument for a single
  `pip install`.
- *Literal `/opt/ros/lyrical` with a comment pointing to `.env`, not `$ROS_DISTRO`.* The variable is only set
  by sourcing that same script, so in a fresh shell it would be empty.
- *Only notes that apply long-term.* Machine-specific issues from this session (a root-owned empty
  `src/par_framework_bringup`, possibly compiling pygame from source on Python 3.14) were left out.
- *No new script* (e.g. `scripts/local_build.sh`). The steps are few and mostly run once. A script is worth
  adding if the steps get repeated often.

## 2026-09-18: ignore `/models/`

**What changed:** Added `/models/` to `.gitignore`.

**Why:** `object_detector` now keeps its YOLO weights in `<framework root>/models` by default (created
automatically, overridable with its `models_dir` parameter). Custom-trained `best.pt` files are specific
to one physical setup and must not be committed. The official `yolo11n-seg.pt` is downloaded there
automatically, so there is nothing worth versioning either.

**Alternatives considered:** Git LFS or a release asset for the weights. Both were rejected: the models are
per setup, not a shared artifact.

**Open:** the container does not see this folder yet. It needs a bind mount `./models:/ros2_ws/models` in
`docker-compose.yaml`, and `setup.sh` should `mkdir -p models` before `compose up`, because Docker creates a
missing bind-mount source as a root-owned folder that host-side runs then cannot write to.

## 2026-09-24: `scripts/local_build.sh` for host-side builds without Docker

**What changed:** New `scripts/local_build.sh` clones all nodes and builds the workspace on the host: rosdep,
the shared `.venv`, `python -m colcon build`, optionally only the packages you name. `sync_nodes.sh` got a
`--clone-only` flag that skips staging manifests into `docker/deps/`. README and CLAUDE.md point to the script.

**Why:** Requested: one command for local testing that doesn't touch Docker. This replaces the earlier
"no new script" decision.

**Decisions:**
- *Reuse `sync_nodes.sh` via a flag instead of copying its clone loop.* A copy would have to keep in sync
  the protection for dirty/diverged checkouts and the empty-repo detection.
- *Distro read from `.env`, falling back to `.env.example`,* so the host build uses the same distro as the
  image, even before `setup.sh` has ever run.
- *Call `.venv/bin/python` directly instead of activating the venv.* Same `sys.executable` for colcon, and no
  need to source another script under `set -u`. ROS's `setup.bash` is sourced with `set +u` because it reads
  unset variables.
- *No sourcing for the caller's shell.* A script can't change its parent shell's environment. It prints the
  source/export lines instead.

## 2026-09-24: surface_selector receives Brio frames again

**What changed:** In `bringup/config/par_setup.yaml`, `surface_selector_node.topic_name_frame` is now
`/camera/brio/image_raw`. CLAUDE.md's "Current pipeline" now lists the Brio's current topics and no longer
has the note about `surface_selector` passing an int QoS. The matching fix is in the node repo
(`src/surface_selector`, on `main`): it subscribes BEST_EFFORT / KEEP_LAST / depth 1 and defaults to the
new topic.

**Why:** Two separate faults, each enough to block all frames. The Brio moved to the `/camera/brio`
namespace (`image_raw`), but the YAML still pointed at `/camera/generic_webcam_frame_full`. The subscriber
also used a reliable profile, which is incompatible with the Brio's best-effort publisher. DDS doesn't
connect incompatible QoS and reports no error.

**Decisions:**
- *Depth 1 instead of the previous queue of 10.* It matches the publisher, and the selector only cares
  about the newest frame. A deeper queue would only keep stale frames around.
- *The QoS profile is defined in the node, not imported from `logitech_brio`.* That would make the
  subscriber depend on one specific camera package, while `topic_name_frame` is meant to allow any
  camera.

## 2026-09-24: CLAUDE.md no longer requires node repos to be `ament_python`

**What changed:** CLAUDE.md's "Adding a node" paragraph now says any colcon-buildable package with a complete
`package.xml` works, `ament_python` or `ament_cmake`. `ament_python` is only the convention for our own nodes,
and `requirements.txt` is optional.

**Why:** The old wording contradicted `config/nodes.list`, which already lists C++ packages
(`azure_kinect_ros_driver`, and `custom_interfaces` is `ament_cmake`). The build doesn't depend on the build
type: staging reads any `package.xml`, and the image already compiles `custom_interfaces`, so compilers and
CMake are present.

**Decisions:** Added a note that third-party repos written for an older distro may need a fork to build. That,
not the build type, is what actually limits adding GitHub nodes. `README.md` makes the same `ament_python`
claim in its "Adding a node" steps and was left unchanged for now.

## 2026-09-24: Brio compatibility modes, and `par_setup.yaml` reaches the Brio again

**What changed:** The Brio node (`src/logitech_brio`, on `main`) has two new read-only parameters:
`qos_reliability` (`best_effort` by default, or `reliable`) for all its publishers, and `encoding` (`bgr8` by
default, or `rgb8`) for the raw and rectified topics. In this repo, `bringup/config/par_setup.yaml` now keys the
Brio by its full name `/camera/brio/logitech_brio_node` and sets both parameters. CLAUDE.md documents the switch
and the rule for namespaced keys.

**Why:** So that third-party nodes that subscribe reliably, or expect RGB, work without patching them. While
testing, it turned out that the YAML key `logitech_brio_node` never reached the node, because the node sets its
namespace `/camera/brio` in code. A test node with that name and namespace read `camera_fps = -1` instead of
`60`. So camera_id, resolution and fps from the YAML were silently ignored as well, and new parameters would
have been too. With the full key, all values arrive.

**Decisions:**
- *One `qos_reliability` switch instead of ROS's built-in `qos_overrides` parameters.* The built-in
  mechanism needs one long parameter per topic and policy (four topics here). One switch covers what
  compatibility actually needs. Depth stays 1 in both modes, so reliable mode doesn't build a backlog.
- *`camera_info` follows the same reliability,* because consumers pair it with the image and need both to
  connect.
- *Colour is swapped once, right after decoding,* so raw and rectified frames match. The compressed topic stays
  the camera's JPEG, because decoders take the channel order from its format string. Greyscale stays `mono8`.
- *Read-only parameters,* because publishers get their QoS when they are created: a runtime change would be
  accepted and have no effect. Invalid values stop the node at startup with the allowed values.
- *Fixed the YAML key instead of setting `namespace=` in the launch files.* The key is one line in one
  file, while the namespace would have to be set in both launch files and repeat what the node already sets.

**Tested:** without a camera, with a stubbed capture: `reliable`/`rgb8` gave a RELIABLE publisher, and a red
JPEG frame arrived at a reliable subscriber as `rgb8` with red in channel 0. An invalid value was rejected, and
the defaults stay best-effort/`bgr8`. Not yet tested with a real Brio.

## 2026-09-24: add the fiducials detector to `nodes.list`

**What changed:** `config/nodes.list` has a new entry `fiducials_detector`
(`ros2-par-framework-fiducials`, branch `main`).

**Why:** The node now subscribes to the Brio's `/camera/brio/image_raw` with best-effort QoS (branch `rework`
in its repo), so it can join the pipeline.

**Decisions:**
- *Directory `fiducials_detector`, the package name,* following the file's convention, rather than the repo
  name `ros2-par-framework-fiducials` that the existing local checkout uses. A checkout under the old name
  would be cloned a second time, and colcon fails when two packages share a name, so the local
  directory has to be renamed once.
- *Branch `main`, like the other nodes.* The compatibility changes are still on `rework`, but `sync_nodes.sh`
  never touches a checkout on a different branch, so the local `rework` checkout is safe until it is merged.

### Brio calibration URL in `par_setup.yaml` (2026-09-24)

**What:** `/camera/brio/logitech_brio_node` gets
`camera_info_url: file:///ros2_ws/src/logitech_brio/calibration/${NAME}.yaml`. The stale comment on
`undistort_frame` (which pointed to the old cwd-relative `calibration/<CameraName>.yaml`) now says it needs a
calibration from that URL.

**Why:** the Brio node now loads its calibration through `camera_info_manager_py`, and cameracalibrator's
COMMIT writes to the same URL. The node's default, `~/.ros/camera_info/`, is inside the container and
disappears with it, while `src/` is bind-mounted from the host and survives rebuilds. The path is a per-setup
value, so it lives here and not in node source.

**Alternatives:**
- *`package://logitech_brio/...`:* resolves to the install space, a named volume that isn't in version control.
- *A bind mount for `/root/.ros`:* one more compose entry, and the file would sit outside every repo.

Verified on the host: with `--params-file` the node logs
`camera calibration URL: file:///ros2_ws/src/logitech_brio/calibration/Logitech_Brio.yaml`.

### `FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA` in the container (2026-09-24)

**What:** `docker-compose.yaml` sets `FASTDDS_BUILTIN_TRANSPORTS=${FASTDDS_BUILTIN_TRANSPORTS:-LARGE_DATA}` in the
service environment. The README no longer says it is unset in the container, and instead notes that host terminals
talking to container nodes need it too.

**Why:** raw 1080p frames (~6 MB) mostly get lost with Fast DDS's default transports (measured on the host), and
it previously had to be exported by hand in every `./scripts/shell.sh`, e.g. for the camera calibration run.
Set on the service, every process in the container inherits it, including the `ros2` daemon.

**Alternatives:**
- *Fixed `LARGE_DATA`:* the `${…:-LARGE_DATA}` form, like `ROS_DOMAIN_ID`, follows a host or `.env` value if one is
  set. Both sides must match, or nodes don't connect.
- *`ENV` in the Dockerfile:* a transport choice is runtime configuration, and changing it would need an image
  rebuild.
- *Export in `scripts/shell.sh`:* `docker exec` from anywhere else would still miss it.

**Verified:** `docker compose config` renders `FASTDDS_BUILTIN_TRANSPORTS: LARGE_DATA`. Not yet measured inside the
container. It takes effect when the container is recreated (the next `./setup.sh` does that).

### RViz view with the Brio frustum, and a working Brio mount transform (2026-09-24)

**What:**
- New `bringup/config/par_framework.rviz`: Fixed Frame `world`, Grid, TF, a **CameraInfo** display on
  `/camera/brio/camera_info` (`Far clip` 1 m) and an Image display on `/camera/brio/image_raw`. Both Brio topics
  are subscribed Best Effort, depth 1.
- `par_framework.launch.py`:
  - new `rviz` argument (default `false`) that starts `rviz2 -d <that config>`;
  - `brio_tf_publisher` is now created in an `OpaqueFunction`. It reads the pose from `params_file` and passes
    it to `static_transform_publisher` as `--x/--y/--z/--qx/--qy/--qz/--qw` plus `--frame-id world
    --child-frame-id brio_link`.
- `bringup/setup.py` installs `config/*.rviz`. `bringup/package.xml` declares `python3-yaml`, `tf2_ros`, `rviz2`,
  `rviz_default_plugins`. The `par_setup.yaml` comment on the pose now says the launch file passes it as flags.

**Why:**
- The frustum: rviz2 on lyrical has a built-in `rviz_default_plugins/CameraInfo` display that draws it from the
  camera's `CameraInfo`. That replaces the planned frustum marker in the Brio node, so there's no node code.
- The TF fix: the previous launch passed the pose as parameters, and `static_transform_publisher` on lyrical
  ignores them. Without `--frame-id` it exits with "Frame id must not be empty". With the frame flags, the flags'
  zero defaults override the parameter file (tested: identity instead of `0, 0, 1`). So `world → brio_link`
  never existed.

**Alternatives:**
- *Frustum as a `visualization_msgs/Marker` from the Brio node:* the CameraInfo display already does it from data
  the node publishes.
- *Pose hard-coded as flags in the launch file:* per-setup values belong in `par_setup.yaml`.
- *Mount pose published by the Brio node:* the node would own per-setup world knowledge.
- *RViz always on:* headless runs and the container without X would fail.

**Tested (host):**
- In an isolated `ROS_DOMAIN_ID=42`: `ros2 launch ... rviz:=true`, with a stand-in `camera_info` (values from
  `Logitech_Brio.yaml`) and the optical TF, since the real Brio was busy. `tf2_echo world brio_optical_frame` gave
  translation `0, 0, 1` and roll 180° (looking down), and RViz showed Global Status OK with the frustum pyramid
  from 1 m down to the grid.
- Separately, against the live Brio node, the Image display showed the camera picture (Best Effort works).
- flake8 is clean. The two pep257 findings on the module docstring (D213, D301) were already in the committed
  version.

### `camera_info_url` launch argument for host runs (2026-09-24)

**What:** `par_framework.launch.py` has a `camera_info_url` argument (default empty). The Brio node is now created
in an `OpaqueFunction` (`logitech_brio_node`). It gets `params_file`, plus `{'camera_info_url': ...}` on top only
when the argument is non-empty. The module docstring shows the host call:
`camera_info_url:="file://$PWD/src/logitech_brio/calibration/\${NAME}.yaml"`.

**Why:** `par_setup.yaml` points the calibration at the container path `/ros2_ws/...`. On the host that path
doesn't exist, so a host launch ran uncalibrated and RViz drew no frustum.

**Alternatives:**
- *Always passing the argument as a parameter:* an empty default would override `par_setup.yaml` with `''`, which
  the node reads as `~/.ros/camera_info/`.
- *Two Brio `Node`s with opposite conditions:* duplicates the whole block.
- *A `package://` URL that works in both:* COMMIT would then write into the install space, which isn't in git and
  is lost on a clean build.

**Tested (host, isolated domain):** without the argument the node logs the container URL and "not calibrated".
With it, the host URL, and it loads `Logitech_Brio.yaml` (no warning). flake8 is clean.

### `bringup` renamed to `par-framework-core` / `par_framework_core` (2026-09-24)

**What:**
- The directory `bringup/` is now `par-framework-core/`, and the ROS package `par_framework_bringup` is now
  `par_framework_core`. Inside the package that covers `package.xml`, `setup.py`, `setup.cfg`, the module folder,
  the `resource/` marker, and `PACKAGE_NAME` in both launch files.
- Updated references: the mount in `docker-compose.yaml` (`./par-framework-core:/ros2_ws/src/par_framework_core`);
  `scripts/launch.sh`; `scripts/local_build.sh` (rosdep and colcon paths); `scripts/sync_nodes.sh` (the path it
  stages `package.xml` from, and a comment); `setup.sh` (message); `README.md`; `CLAUDE.md`.
- Moved with plain `mv`, not `git mv`, so the index stayed as you had it. The host's stale
  `build/`/`install/par_framework_bringup` was deleted.

**Why:** your request. The directory takes the hyphenated name you gave. The package name can't: REP 144 allows only
lowercase letters, digits and underscores in ROS package names, so the package is `par_framework_core`.

**Alternatives:**
- *Underscores for the directory too:* consistent with the package, but not the name you asked for. The node repos
  already use hyphenated repo names with underscore package names.
- *Keeping the stale install:* `ros2 launch par_framework_bringup ...` would silently keep working with outdated
  files.

**Tested (host):** `grep -i bringup` finds nothing outside this log. flake8 is clean on the launch files and
`setup.py`. `colcon build` builds `par_framework_core`, and `ros2 pkg prefix par_framework_bringup` says "Package
not found". In an isolated domain, `ros2 launch par_framework_core par_framework.launch.py` started the Brio
(calibrated, 60 fps) and the TF publisher (`0, 0, 1`), and nothing was left running afterwards.
