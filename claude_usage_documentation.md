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

### Architecture rule: framework glue nodes may live in the core repo (2026-09-24)

**What:** `CLAUDE.md` changed from "contains **no node source**" to "**no node source, except framework glue**": nodes
that only make sense inside this framework, because they are built on its messages, topic names and frame
conventions. The first one planned is `rviz_bridge`. Every other node keeps its own repo. `par-framework-core/` stays
launch files and parameters only, and glue nodes get their own top-level package directory next to it.

**Why:** your decision. `rviz_bridge` (framework outputs such as `/objects` → RViz markers) is framework glue: it
depends on `custom_interfaces`, the topic names, the `world` frame and the table-plane assumption, and it changes
together with `par_framework.rviz` and the launch file. The rule is changed explicitly, so the next "sort of core"
case has a test to apply instead of a quiet precedent.

**Alternatives:**
- *Its own repo `ros2-par-framework-rviz-bridge`:* keeps the old rule intact, but costs a GitHub repo, a `nodes.list`
  entry, and two-repo commits for every new display.
- *Inside `par-framework-core/`:* colcon doesn't look for packages inside another package's directory.

### `packages/` folder for this repo's own ROS packages (2026-09-24)

**What:** `par-framework-core/` moved to `packages/par-framework-core/`, and `packages/rviz_bridge/` is to follow.
Everything now points at `packages/` as a whole:
- `scripts/local_build.sh`: `--base-paths src packages`, `rosdep --from-paths src packages`.
- `scripts/sync_nodes.sh`: stages every `packages/*/package.xml`.
- `docker-compose.yaml`: one mount, `./packages:/ros2_ws/src/packages`.
- Paths updated in `README.md` (commands and layout block), `CLAUDE.md` (rule text and `par_setup.yaml` path) and
  the `setup.sh` message.

**Why:** your decision. colcon finds every package under a base path recursively, so the next core package (the
bridge, and later ones) needs no path changes in scripts or the container. The package name `par_framework_core` is
unchanged.

**Alternatives:** *a second top-level folder per package:* every new core package would repeat the script,
compose and README edits.

**Tested (host):** `bash -n` passes on both scripts, and the staging `find` finds
`packages/par-framework-core/package.xml`. The old symlinked build output pointed into the moved folder, so it was
removed and rebuilt; the installed `par_setup.yaml` now resolves into `packages/`. `ros2 launch par_framework_core
par_framework.launch.py` in an isolated domain started the calibrated Brio (60 fps) and the TF publisher (`0, 0, 1`),
and nothing was left running.

### `rviz_bridge`: detected objects on the table in RViz (2026-09-24)

**What:**
- New package `packages/rviz_bridge/` (node `rviz_bridge_node`, executable `rviz_bridge`). It subscribes to `/objects`
  (`custom_interfaces/ObjectList`, image pixels) and `/camera/brio/camera_info` (Best Effort), looks up
  `world ← <ObjectList frame>` in TF, and publishes `/objects/markers` (`MarkerArray` in `world`). The array holds a
  `DELETEALL` first, then per object a closed `LINE_STRIP` (hull, falling back to the contour, then the center) 2 mm
  above the table, plus a `TEXT_VIEW_FACING` label `class#id`.
- `rviz_bridge/rviz_bridge.py` holds the ROS-free math: `cv2.undistortPoints` turns pixels into rays, which are
  rotated into `world` and intersected with z = 0 (rays that miss the table are dropped), plus a quaternion → matrix
  helper. `test/test_rviz_bridge.py` checks it against a camera 1 m up looking down; `test_flake8`/`test_pep257` as
  in the other packages.
- Wiring:
  - the launch file starts the bridge with `rviz:=true`;
  - `par_framework.rviz` gets an **Objects** MarkerArray display;
  - `par_framework_core` declares `rviz_bridge`;
  - `local_build.sh` and the README pip command also read `packages/*/requirements.txt`, which the bridge's
    `opencv-python` pin needs;
  - README layout and packages table, and `CLAUDE.md` (glue node "currently" rather than "planned").

**Why:** RViz cannot draw `/objects`: there's no display plugin for the custom type, and its coordinates are pixels
without depth. Projecting onto the table plane (assumption: the table is world z = 0) with the calibration and TF
gives metric positions under the frustum. The detector stays unchanged, per your decision.

**Decisions:**
- Topic names and `world` are constants, not parameters, because they don't vary per setup.
- The TF is looked up with `Time()` (latest), because it is static.
- Warnings about missing calibration or TF are throttled to one per 5 s.
- `setup.py` declares `extras_require={'test': ['pytest']}`; without it, `colcon test` fell back to unittest and ran
  0 tests.
- Labels have no space (`cup#3`): RViz rendered the space in `cup #3` several text heights wide.

**Alternatives:**
- *Markers from inside the detector:* rejected by you, to keep the detector unchanged.
- *A C++ RViz plugin for `ObjectList`:* much more work.
- *An annotated 2D image:* not in the 3D scene.
- *`vision_msgs/Detection3DArray`:* needs an extra RViz plugin package.

**Tested (host):**
- `colcon test`: 5 tests, 0 failures (3 projection, flake8, pep257).
- End to end in an isolated domain: `ros2 launch par_framework_core par_framework.launch.py rviz:=true` with the
  calibration, plus a stand-in `/objects` (a 200×200 px square around 960/540). `/objects/markers` had `DELETEALL`,
  an outline of 0.115 × 0.116 m (expected ~0.116 at fx ≈ 1724, 1 m) and a `cup#3` label. The RViz screenshot shows
  the outline and label on the grid under the frustum, with Global Status OK.
- Not yet run with the real object detector.

### README package table corrected (2026-09-24)

**What:** in `README.md` → "Current packages":
- the `logitech_brio` row names `/camera/brio/image_raw` (+ `/compressed`) and `/camera/brio/camera_info`
  instead of the outdated `/camera/generic_webcam_frame_full`;
- `surface_selector` names its input topic;
- rows added for `object_detector` (`/camera/brio/image_raw/compressed` → `/objects`, image pixels) and
  `fiducials_detector` (`/camera/brio/image_raw` → `/fiducials`), which are in `config/nodes.list` but were missing.

**Why:** your request. The topics were checked against the node sources in `src/`. Neither node sets a namespace,
so the outputs are `/objects` and `/fiducials`. `surface_selector` defines a `surface_corners` topic name but
creates no publisher, so no output is listed for it.

### `projection_corners`: owner of the projection corners (2026-09-24)

**What:**
- New package `packages/projection_corners/` (node `projection_corners_node`). At startup it loads the YAML file
  from the parameter `projection_corners_file`. It publishes the corners on `/projection_corners`
  (`custom_interfaces/ProjectionCorners`, RELIABLE + TRANSIENT_LOCAL, depth 1). It offers `/set_projection_corners`
  (`SetProjectionCorners`), which validates, saves and republishes.
- `projection_corners/projection_corners.py` holds the ROS-free `load`/`save`/`validate`: all corners inside the
  image, non-zero area (shoelace formula), non-empty image size. `test/test_projection_corners.py` covers them.
- Both launch files start it through an `OpaqueFunction`. The file is `projection_corners.yaml` next to the
  **real** `par_setup.yaml` (`os.path.realpath` follows the `--symlink-install` links into
  `packages/par-framework-core/config/`), so the path is correct on the host and in the container.
  `par_framework_core` declares the dependency.
- `CLAUDE.md` has a note on the Transient Local trap; the README layout and package table list the new package.

**Why:** your decision after reviewing the old approach. `surface_selector` wrote its corners to a private INI
file in the install space: lost on a clean build, not in git, unreachable for other nodes. The new split mirrors
the camera calibration: a light node owns and distributes the data, and the interactive tool (`surface_selector`,
reworked next) only sends new corners through a service. You chose option 2, the file next to `par_setup.yaml`,
because the corners describe the physical setup like the camera pose and need no host/container launch argument.

**Decisions:**
- A plain file-path parameter, not a `file://` URL: the launch file computes it, and nobody types it.
- One set of corners, not one per camera: the framework has one camera; a second would get a namespaced node.
- Stored corners are stamped with the publish time: no image belongs to them.

**Alternatives:**
- *The path in `par_setup.yaml` plus a host launch argument, like `camera_info_url`:* an argument to pass on every
  host run.
- *Letting `surface_selector` publish latched itself:* the corners would vanish whenever the calibration tool isn't
  running.

**Tested (host):**
- `colcon test`: 5 tests, 0 failures.
- End to end in an isolated domain with `par_framework.launch.py`:
  - a valid `ros2 service call` wrote `packages/par-framework-core/config/projection_corners.yaml`;
  - an invalid one was rejected with "top_right (2000.0, 241.0) lies outside the 1920x1080 image";
  - a Transient Local subscriber started afterwards still received the corners;
  - after a restart the node loaded them from the file and a late subscriber got them again.
- The test file was deleted afterwards, and nothing was left running.

### `projection_corners.yaml` gitignored (2026-09-24)

**What:** `.gitignore` ignores `/packages/par-framework-core/config/projection_corners.yaml`.

**Why:** your request. Like the Brio's calibration file, the corners belong to one physical setup and are written by a
node, not edited as part of the framework. `par_setup.yaml` next to it stays tracked (checked with
`git check-ignore`).

### `rviz_bridge`: projection area on the table (2026-09-24)

**What:**
- `rviz_bridge_node` subscribes to `/projection_corners` (RELIABLE + TRANSIENT_LOCAL) and publishes
  `/projection_corners/markers`: ns `projection_area`, id 0 is a closed blue `LINE_STRIP`, id 1 a 25 %-opaque
  `TRIANGLE_LIST` fill (two triangles TL-TR-BR and TL-BR-BL), 1 mm above the table, below the 2 mm object outlines.
- A 1 s timer redraws the area, and so does each new corners message.
- If the corners' `image_width`/`image_height` differ from the current `camera_info`, the bridge warns and draws
  nothing; it also skips the area when not all four corners hit the table plane.
- The calibration/TF lookup now sits in one helper, `__projection()`, shared with the objects display; the objects
  behaviour is unchanged.
- `par_framework.rviz` gets a **Projection area** MarkerArray display; the README table mentions the new topics.

**Why:** your request, to see the area selected with `surface_selector` next to the camera and the objects. The
corners arrive once (latched) but the calibration or TF may arrive later, so drawing only on arrival could miss
them; a 1 s redraw is the simplest thing that catches every order.

**Alternatives:**
- *Retry only while something is missing:* more state for the same result.
- *A latched marker publisher:* RViz subscribes Volatile by default, so it would need a config change as well, and
  a new calibration would still need a redraw.
- *Scaling the corners to another resolution:* only valid for the same aspect ratio and sensor crop (see the Brio's
  resolution warning).

**Tested (host):**
- `colcon test`: 5 tests, 0 failures.
- End to end in an isolated domain: `par_framework.launch.py rviz:=true`, stand-ins for the Brio's `camera_info` and
  optical TF (the camera was held by another process), corners stored through `/set_projection_corners`, plus a
  stand-in object.
- `/projection_corners/markers` held a 5-point closed outline and a 6-point fill (about 0.36 × 0.64 m at the
  placeholder pose). The RViz screenshot shows the blue area with the green object on top, Global Status OK.
- The test corners file was deleted, and no test processes were left.

## Framework-wide switch from opencv-python to opencv-contrib-python

**What changed:** every `requirements.txt` in the framework pins `opencv-contrib-python==4.11.0.86` instead of
`opencv-python==4.11.0.86`: `packages/rviz_bridge` here, plus `surface_selector`, `fiducials_detector` and
`object_detector` and `logitech_brio` in their own repos. The comment in
`packages/rviz_bridge/package.xml` says why.

**Why:** the new `hand_landmarks` node needs `mediapipe`, and `mediapipe` (1.0.1) depends on `opencv-contrib-python`.
Both OpenCV distributions install into the same `cv2/` directory, so with both in one environment whichever is
installed last silently wins, and uninstalling one breaks the other. The contrib build is the same OpenCV version
plus the extra modules, so nothing the existing nodes use changes. The `cp37-abi3` wheel covers Python 3.14 (Lyrical).

**Alternatives:**
- *Install mediapipe with `--no-deps`:* conflicts with the single `pip install` over all `requirements.txt`, which
  exists precisely so conflicting pins fail the build.
- *Only hand_landmarks pins contrib:* both packages would end up installed, the silent-shadowing case above.

## hand_landmarks joins the framework, hands in RViz

**What changed:**
- `config/nodes.list`: `hand_landmarks` (`ros2-par-framework-hand-landmarks`, branch `main`). The README's package
  table lists it.
- `rviz_bridge` subscribes to `/hand_landmarks` (`HandLandmarksList`) and publishes `/hand_landmarks/markers`: per
  hand a `SPHERE_LIST` of the 21 joints, a `LINE_LIST` of the bones and a `Left#<id>` / `Right#<id>` label above
  the wrist, coloured by handedness, with a `DELETEALL` first like the objects. The landmarks are projected onto
  the table with the existing `pixels_to_table`.
- `par_framework.rviz` has a **Hands** MarkerArray display; README row of `rviz_bridge` updated.

**Why:** to see the hand_landmarks node's output on the real setup, next to the objects and the projection area.

**Decisions:**
- *Projected onto the table:* the landmarks are 2D pixels; without depth, the ray's hit on the table is the only
  position available, so a raised hand shows as its footprint straight below the camera, not at its height. Enough
  to check detection, tracking ids and alignment with the table; real 3D needs the depth path (item 13).
- *All 21 rays must hit the table, else the hand is skipped:* `pixels_to_table` drops misses, which would shift
  the ids the bones refer to. With the camera looking down at the table this does not happen in practice.
- *Bone list copied from mediapipe's `HAND_CONNECTIONS`* instead of importing it: `rviz_bridge` would otherwise
  need mediapipe as a dependency for a list of 21 index pairs.
- *`hand_landmarks` not added to `par_framework.launch.py`:* the processing nodes (`object_detector`,
  `fiducials_detector`) are started separately too; the launch file only brings up the camera, TF, corners and RViz.

**Tested (host, ROS Lyrical, isolated domain):** stand-in static TF (camera 1 m above `world`, looking down), the
Brio's real calibration as `CameraInfo`, and one fake hand of 21 pixel landmarks. `/hand_landmarks/markers` held
`DELETEALL`, 21 joints, 42 bone points and the label `Left#7`; the wrist, near the principal point, landed at
(0.031, -0.001) m. `ament_flake8` and `ament_pep257` pass for `rviz_bridge`. Not tested yet: RViz itself and the
real camera.

### Container mount of `packages/` moved out of `src/` (2026-09-24)

**What:** `docker-compose.yaml` mounts `./packages` at `/ros2_ws/packages` instead of `/ros2_ws/src/packages`. The
empty, root-owned `src/packages/` that the old mount had created on the host was removed (`rmdir`).

**Why:** your request. A bind mount inside another bind mount (`./src` at `/ros2_ws/src`) makes Docker create the
mount point in the outer source, so every container start left an empty root-owned `src/packages/` on the host,
which then looked like a node repository in `src/`.

No build change was needed: `scripts/build_workspace.sh` runs `colcon build` in `/ros2_ws` without
`--base-paths`, and colcon searches it recursively, skipping `build/`, `install/` and `log/` (`COLCON_IGNORE`).

**Alternatives:**
- *Keep the mount and add `src/packages` to a cleanup step:* it would come back on every start.
- *Mount the whole repo:* would expose host build output and `.venv` inside the container.

**Tested (host):**
- `docker compose config` resolves `./src` → `/ros2_ws/src` and `./packages` → `/ros2_ws/packages`.
- `colcon list` without `--base-paths` from the repo root (same layout as `/ros2_ws`) finds all packages in
  `src/` and `packages/`; the extra `docker/deps/` copies only exist on the host.
- Not run in the container.

### `camera_info_url` argument for `calibration.launch.py` (2026-09-24)

**What:** `calibration.launch.py` declares `camera_info_url` (default empty) and starts the Brio through the same
`logitech_brio_node` `OpaqueFunction` as `par_framework.launch.py`. The override is only added when set. The module
docstring shows the host call.

**Why:** your request. `par_setup.yaml` points the calibration into the container, so on the host the calibration
run's Brio was uncalibrated. That didn't matter for the corners (raw pixels), but it was inconsistent with the main
launch.

**Decisions:** the function is duplicated (identical, checked with `diff`) rather than shared, like
`projection_corners_node` already is. Sharing would need a small helper module in the `par_framework_core` Python
package; not done unasked.

**Tested (host, isolated domain, a `par_setup.yaml` copy with `display_id: 99` so no window opened):**
- without the argument the Brio logs the container URL and "not calibrated";
- with it, the host URL and no warning;
- `surface_selector` stopped with "Could not get the resolution of display 99";
- nothing was left running.

### `rviz_bridge`: fiducials on the table (2026-09-24)

**What:**
- `rviz_bridge_node` subscribes to `/fiducials` (`custom_interfaces/FiducialsList`, pixels of the raw image) and
  publishes `/fiducials/markers` in `world`:
  - `DELETEALL` first;
  - then per fiducial a closed yellow outline (ns `fiducial_outline`), a line from the centre to the middle of edge
    0→1 (ns `fiducial_direction`), and a label `#<id>` (ns `fiducial_label`), all with `id` = marker id.
- A fiducial is skipped when not all four corner rays hit the table, as the hands do with their landmarks.
- `par_framework.rviz` gets a **Fiducials** MarkerArray display; the README table lists the topics.

**Why:** your request, next after objects, hands and the projection area. The corner order is OpenCV's (clockwise
from the marker's top left), which `fiducials_detector` passes through unchanged and computes its `angle` from
edge 0→1. So the direction line shows the same rotation the detector reports, which matters for fiducials used as
tangibles.

**Decisions:**
- Built on the committed hands code (`on_hands`) and in its style.
- Yellow, because orange is already the left hand.
- The centre is the mean of the projected corners, not the projected `x/y_centroid` pixel: under perspective they
  differ slightly, and the corners are what is drawn.

**Tested (host):**
- `colcon test`: 5 tests, 0 failures.
- End to end in an isolated domain: `par_framework.launch.py rviz:=true`, with stand-ins for `camera_info` and the
  optical TF and a stand-in fiducial (id 7, 150 px, rotated 20°).
- `/fiducials/markers` held `DELETEALL`, a 5-point closed outline with ~0.087 m sides (150 px at fx ≈ 1724, 1 m),
  the direction line and `#7`. The RViz screenshot shows the rotated yellow marker inside the projection area,
  Global Status OK.
- Nothing was left running.

### Table → projector mapping, the ROS way (2026-09-24)

**What (plan steps 1–4, approved):**
- **`packages/par_geometry/`** (new library, no node): `rotation_matrix` and `pixels_to_table` moved here unchanged
  from `rviz_bridge/rviz_bridge.py` (checked with `diff`), plus `apply_homography`, `table_to_projector`,
  `projector_to_table` and `homography_from_msg`. Its test absorbed the old `test_rviz_bridge.py` and adds a
  homography round trip. `rviz_bridge_node.py` imports from `par_geometry`.
- **`packages/projection_mapping/`** (new glue node), built like `projection_corners`:
  - loads `projection_mapping.yaml` from `projection_mapping_file`;
  - publishes latched `/projection_mapping` (`custom_interfaces/ProjectionMapping`, RELIABLE + TRANSIENT_LOCAL);
  - `/set_projection_mapping` validates (non-empty frame, projector size > 0, 9 finite values, |det| ≥ 1e-12),
    saves and republishes.
  - `.gitignore` ignores its file.
- **Launch:**
  - the start functions moved into `par_framework_core/launch_helpers.py`, since a third launch file needed them;
    `next_to_params_file()` is the shared realpath trick;
  - new `projection_calibration.launch.py` starts the Brio, `brio_tf_publisher`, `fiducials_detector`,
    `projection_mapping` and `projection_calibrator`, and ends via `on_exit=Shutdown()` once the calibrator is done;
  - `par_framework.launch.py` also starts `projection_mapping`.
- **`par_setup.yaml`:** new `projection_calibrator_node` block (display, projector resolution, dictionary, marker
  ids 90–98, size, error threshold).
- **`par_framework_core/package.xml`:** declares `projection_mapping`, `fiducials_detector` and `surface_selector`
  (the latter was launched but never declared).
- **`rviz_bridge`:** subscribes `/projection_mapping` and draws the projector's four corner pixels, mapped back with
  `projector_to_table`, as a magenta outline on `/projection_mapping/markers` (redrawn every second);
  `par_framework.rviz` gets a "Projector (calibrated)" display.
- **Docs:** `CLAUDE.md` has a section on the coordinate chain and the latched mapping; README layout and table.

**Why:** your request after reviewing VIGITIA's `homography_service`. It served a camera → projector homography
from clicked corners through four services (per-point round trips, whole images per frame), on distorted pixels,
with orientation hacks, and named the corners in camera terms. Now the table plane in metres is the common
currency: detections reach it through `par_geometry` (undistorted, via TF), the projector through one latched
homography, and consumers convert locally. Corner identity comes from the projector's side (marker ids), so no
orientation flags are needed. Your decisions: the calibrator lives in `surface_selector`; `projection_corners` and
the click tool stay as a fallback.

**Deviations from the plan:**
- `table_to_projector`/`projector_to_table` take the 3×3 matrix, and `homography_from_msg` builds it, so the
  functions also work without a message (the calibrator uses them that way).
- The synthetic test ran the nodes individually instead of through the launch file, so the stand-in data couldn't
  mix with real detector output.

**Tested (host, isolated domain 42):**
- `colcon test`: `par_geometry` 7/7, `projection_mapping` 5/5, `rviz_bridge` 2/2; `surface_selector` all 6 logic
  tests pass, and its lint failures are only the known old findings in `display_info.py` and
  `show_white_fullscreen.py`.
- All three launch files load (`--show-args`).
- **Synthetic end to end:**
  - a "true" mapping from your stored projection corners, the Brio calibration and the placeholder pose;
  - stand-in `/fiducials` = the marker corners projected into the camera with `cv2.projectPoints`, including
    distortion;
  - the real calibrator fitted 9 markers / 1080 corners at 0.0006 px RMS, stored through the real owner (exit 0);
  - a late Transient Local subscriber received the mapping;
  - the stored homography deviates from the true one by at most 0.0005 px over all 36 marker corners.
- RViz: the magenta calibrated outline lies exactly on the blue clicked area, Global Status OK.
- The test files lived in a temporary directory; no repo file was written, and nothing was left running (the domain
  42 `ros2` daemon was stopped).
- Not yet run with the real projector.

### Azure Kinect launch files (2026-09-25)

**What:**
- **`par_framework_kinect.launch.py`** (new): starts the Azure Kinect driver, `world -> camera_base`, `object_detector`,
  `fiducials_detector`, `hand_landmarks`, `projection_corners`, `projection_mapping`, `rviz_bridge` and RViz
  (always on, since this launch exists to show the setup) with the new `par_framework_kinect.rviz`.
- **`projection_calibration_kinect.launch.py`** (new): `projection_calibration.launch.py` with the Kinect instead of
  the Brio. It needs no `camera_info_url`, because the Kinect publishes its factory calibration.
- **`par_framework_kinect.rviz`** (new): a copy of `par_framework.rviz` with the Kinect's topics and a `PointCloud2`
  display on `/points2` (RGB8, Best Effort).
- **`launch_helpers.py`:**
  - `brio_tf_publisher` became `mount_tf_publisher(context, name, child_frame_id)`, and both Brio launch files call it
    with `args=['brio_tf_publisher', 'brio_link']`;
  - new `KINECT_REMAPPINGS` maps the Brio's image, compressed image and camera_info topics to the Kinect's
    `/rgb/...` topics.
- **`par_setup.yaml`:** `k4a_ros_device_node` (1080P bgra colour, NFOV_UNBINNED depth, 30 fps, coloured cloud in the
  depth frame) and `/kinect_tf_publisher` (the same placeholder pose as the Brio).
- **`package.xml`:** declares `object_detector`, `hand_landmarks` and `compressed_image_transport`. README layout
  updated.

**Why:**
- **Remapping instead of parameters or code changes:** `hand_landmarks`, `rviz_bridge` and `projection_calibrator`
  hard-code `/camera/brio/camera_info`, so only a remapping reaches them without edits in three node repos.
  - Alternative: namespace the driver as `/camera/brio`. Rejected, because it would present the Kinect as the Brio,
    and the detectors' optional depth topic `/depth_to_rgb/image_raw` expects the driver without a namespace.
- **Driver started as a plain `Node` with `params_file`,** not through Microsoft's `driver.launch.py`:
  - its settings then live in `par_setup.yaml` like every other hardware constant;
  - its `robot_state_publisher`/`joint_state_publisher` only draw a 3D model of the camera;
  - there is no `name=` override, because the driver runs several rclcpp nodes in one process and would rename all
    of them.
- **`compressed_image_transport`:** `object_detector` subscribes to `CompressedImage`, but the driver publishes raw
  frames (bgra, needed for the coloured cloud). With the plugin installed, the driver's `image_transport` also offers
  `/rgb/image_raw/compressed`.
  - Alternative: `color_format: jpeg`. Rejected: then no raw image is published for the other detectors, and there
    is no coloured cloud.
- **Point cloud in the depth frame, NFOV_UNBINNED:** about 370k points instead of about 2M per frame, and 30 fps;
  WFOV_UNBINNED is limited to 15 fps.
- **`azure_kinect_ros_driver` not declared in `package.xml`:** it does not build on lyrical yet (see below), and
  colcon would then skip `par_framework_core`, breaking the Brio launch files too.

**Tested:**
- All four launch files parse (`--show-args`).
- `ament_flake8` is clean on the changed files.
- `mount_tf_publisher` produces the expected flags for the Brio and the Kinect.
- **Not run with the camera:** the driver fails to build on lyrical (`Unknown CMake command
  "ament_target_dependencies"` in `CMakeLists.txt:49`; upstream `foxy-devel` targets older distros).
  `src/azure_kinect_ros_driver` also has no `.git`, so `sync_nodes.sh` cannot update it.

### Azure Kinect driver: extended repo, branch fix (2026-09-25)

**What:** `config/nodes.list` now fetches `azure_kinect_ros_driver` from branch `main` instead of `foxy-devel`. You had
already switched the URL to `nlouman/azure_kinect_ros_driver_extended`, and that repo has only `main`, so
`sync_nodes.sh` would have failed on the old branch name.

**Why this repo:** it adds live-adjustable colour controls (exposure, white balance, gain, ...) to Microsoft's
driver. Your decision: use it without a fork for now.

**Local patches in the clone** (in `src/azure_kinect_ros_driver`, not in this repository; lost when the clone is
deleted). They are needed on lyrical:
1. `CMakeLists.txt`: `ament_target_dependencies` (removed) → `target_link_libraries` with exported targets.
2. The `tf2`/`cv_bridge` includes `.h` → `.hpp`, because the `.h` headers were removed.
3. `k4a_ros_device.cpp`: `ImageTransport(static_cast<rclcpp::Node::SharedPtr>(this))` → `ImageTransport(*this)`.
   The `shared_ptr` owned the node, and newer image_transport releases it at once, which deleted the driver
   mid-construction.
4. `CMakeLists.txt`: install the executable only to `lib/azure_kinect_ros_driver`. With the old double destination,
   `--symlink-install` put it in `bin/`, where `ros2 run` does not look.

**Tested with the Kinect** (isolated domain 42, `par_setup.yaml` settings):
- `/rgb/image_raw` at 30.1 Hz, 1920 wide;
- `/points2` at 28.7 Hz in `depth_camera_link`;
- `/rgb/camera_info` in `rgb_camera_link` with the factory `rational_polynomial` calibration;
- TF `camera_base -> rgb_camera_link` is published;
- the log has only the driver's normal time-sync warnings.

### Kinect: object_detector on raw frames (2026-09-25)

**What:**
- `par_framework_kinect.launch.py` passes `object_detector` `topic_name_frame: /rgb/image_raw`. `framework_node`
  takes optional parameter overrides for that.
- `KINECT_REMAPPINGS` lost the `/compressed` rule.
- `package.xml` lost `compressed_image_transport` and the comment about the undeclared driver.

**Why:** `object_detector` now accepts raw `Image` topics (a change in its repo), so the driver no longer has to JPEG
every 1080p frame for it. The plugin was only there for that.

**Tested:** driver plus detector live, `/objects` at 27.3 Hz; `ament_flake8` is clean.

### Kinect: driver declared, full launch tested (2026-09-25)

**What:** `par_framework_core/package.xml` declares `azure_kinect_ros_driver`, which builds now thanks to the local
patches in its clone.

**Tested:** `par_framework_kinect.launch.py` live with the Kinect and RViz (domain 42).
- All nodes start, and RViz subscribes to `/points2`.
- Measured rates: `/rgb/image_raw` 18.6 Hz, `/points2` 13.4 Hz, `/hand_landmarks` 7.5 Hz, `/hand_landmarks/markers`
  14.1 Hz. `/objects` and `/fiducials` were published, but `ros2 topic hz` got no reading on the loaded machine.
- **The CPU is saturated:** driver 214 %, `fiducials_detector` 201 %, `object_detector` 116 %, RViz 106 %,
  `hand_landmarks` 101 %; memory was 11 of 14 GB. Run alone, the driver and `object_detector` reach 30 and 27 Hz.
  Not changed yet; the options are listed in the reply.
- `rviz_bridge` warns every second that `world <- brio_optical_frame` is missing: the stored `projection_corners.yaml`
  was clicked in the Brio image and does not apply to the Kinect.

### Kinect point cloud off, projector on display 3 (2026-09-25)

**What:**
- `par_setup.yaml`: `point_cloud` and `rgb_point_cloud` are `false`, and the RViz "Kinect point cloud" display is
  disabled. `rgb_point_cloud` requires `point_cloud`, and an enabled display without a topic shows a permanent error.
- `display_id: 3` for `surface_selector_node` and `projection_calibrator_node`, since both drive the same projector.

**Why:** your request. The coloured cloud was the largest part of the driver's CPU load while everything ran
together, and it is not needed for detection. You named display 3 as the projector; pygame lists it at
1920x1080, which matches `projector_width`/`projector_height`.

### Per-camera projector mapping, Kinect optional for the build, wrong-intrinsics warning (2026-09-25)

**What:**
- **One mapping file per camera:**
  - `projection_mapping_node(context, camera)` stores `config/projection_mapping_<camera>.yaml`; the Brio launch
    files pass `brio`, the Kinect ones `kinect`;
  - the existing file (the Kinect calibration from 15:07) was renamed to `projection_mapping_kinect.yaml`;
  - `.gitignore` covers `projection_mapping_*.yaml`; `CLAUDE.md`, the README and the launch docstrings were updated.
- **The Kinect no longer breaks the build:**
  - `azure_kinect_ros_driver` is no longer declared in `par_framework_core/package.xml`;
  - `rosdep` runs with `--skip-keys K4A` in `docker/Dockerfile`, `scripts/local_build.sh` and the README's manual
    steps;
  - `scripts/build_workspace.sh` (the container build) passes `--packages-skip azure_kinect_ros_driver`;
  - the README gets a "host only" note (SDK, udev rule, local patches in the clone), and `CLAUDE.md` gets a sentence
    in its container section.
- **Wrong-intrinsics warning:** `rviz_bridge`'s `__projection` warns (throttled) when `camera_info.header.frame_id`
  differs from the pixels' frame. `projection_calibrator` got the same check (in `surface_selector`, see that
  repo's log). Both carry on after warning.

**Why:**
- **Mapping:** with placeholder poses, each camera's `world` plane is its own, so one shared file would have
  silently mis-projected after switching cameras.
  - Alternative: recalibrate on every switch. Rejected: easy to forget.
  - Alternative: measure both poses. Rejected for now: effort, and it adds a source of error.
- **Build:** `K4A` has no rosdep rule, so `rosdep install` failed for everyone (confirmed with `--simulate`).
  - The image cannot build the driver at all without the SDK, and the declaration made colcon skip
    `par_framework_core`, the Brio launch files included.
  - Alternative: install the SDK in the image. Rejected: Microsoft only packages it for old Ubuntu releases.
- **Warning:** it catches intrinsics from the wrong camera (e.g. a forgotten remapping) wherever pixels become
  table points, not only in today's launch files.

**Tested:**
- `rosdep install --simulate --skip-keys K4A` exits 0. `bash -n` passes on both scripts, all four launch files
  parse, `rviz_bridge` passes 2/2 tests, and `ament_flake8` is clean on the changed files. `surface_selector` fails
  only on the known old findings in `display_info.py`/`show_white_fullscreen.py`.
- Fake mismatch (camera_info `brio_optical_frame`, fiducials `rgb_camera_link`): the warning fires.
- Kinect live:
  - `/projection_mapping` carries 1.6889 px, i.e. the renamed Kinect file;
  - the warning fires only for the projection area, a true positive: its corners were clicked in the Brio image;
  - there is no warning for objects, hands or fiducials.
- **Not tested:** the Docker image build and the Brio live (not connected).
- **Found:** the Kinect driver aborts intermittently on Ctrl-C (1 of 3 runs): its camera thread calls
  `count_subscribers()` after the context is shut down. This is in the driver, not fixed.

### Hands in 3D in RViz (2026-09-25)

**What:**
- **`rviz_bridge` `on_hands`:** hands with 21 `hand_landmarks_3d` (`hand_landmarks` with `use_depth`) are drawn
  where they were measured, moved from the optical frame into `world` with the same TF pose (`p @ R.T + t`).
  - Landmarks without depth (`z <= 0`, the message's -1) are left out, together with their bones.
  - Without 3D positions (e.g. the Brio), the hands are projected onto the table as before.
  - The label sits `LABEL_HEIGHT` above the wrist (or the first landmark with a position) instead of at a fixed
    height.
- **`par_framework_kinect.launch.py`:** `hand_landmarks` gets `use_depth: true`.

**Why:** your request, hand landmarks in 3D. The driver only computes `/depth_to_rgb/image_raw` while it has a
subscriber, so it costs nothing without depth. The 3D math lives in `hand_landmarks`, which has the depth image,
while `rviz_bridge` only transforms. `par_geometry` stays the place for pixel-to-table math.

**Tested:** `rviz_bridge` passes 2/2 tests including flake8. Live, the pipeline runs (about 10 hand messages/s); a
hand's 3D markers are not tested yet (no hand in view).

**Live test with a hand (2026-09-25):** RViz draws the hands in 3D. Joint markers are 0.04-0.35 m above `world`
(median 0.24 m), where before they were all at 3 mm. The heights depend on the Kinect pose in `par_setup.yaml`,
which is still the placeholder.

### Fiducials in 3D in RViz (2026-09-25)

**What:**
- **`rviz_bridge` `on_fiducials`:** fiducials with four `corners_3d` (fiducials_detector with `use_depth`) are moved
  from the optical frame into `world` (`p @ R.T + t`) and drawn there: outline, direction line, and the label
  `LABEL_HEIGHT` above the centre.
  - Without 3D, they are projected onto the table as before, now through the same code (`hits`, z = `OUTLINE_HEIGHT`).
- **`par_framework_kinect.launch.py`:** `fiducials_detector` gets `use_depth: true`. `projection_calibration_kinect`
  stays without depth: the calibrator needs only the pixel corners.

**Why:** your request, markers in 3D like the hands.

**Tested:** `rviz_bridge` passes 2/2 tests including flake8, and the Kinect launch parses. Live test pending.

### Kinect frustum reaches the table (2026-09-25)

**What:** `par_framework_kinect.rviz`: the frustum's `Far clip` goes from 1 to 1.5, the Kinect's height in
`/kinect_tf_publisher`.

**Why:** with the Kinect at 1.5 m, RViz drew the 1 m frustum ending 0.5 m above the table. `Far clip` is the frustum's
length from the camera, so it has to follow the mount height. (The same edit is on branch
`projector-res-from-display`.)

**Tested:** the installed config (symlink-install) reads `Far clip: 1.5`.

### Kinect height measured: 0.97 m (2026-09-25)

**What:** `/kinect_tf_publisher` `translation.z` goes from 1.5 to 0.97 in `par_setup.yaml`, and `Far clip` in
`par_framework_kinect.rviz` goes to 0.97 as well.

**Why:**
- 1.5 m was the projector's height, entered as the Kinect's.
- With `use_depth`, hand landmarks are placed at `configured height − measured depth`, so a hand on the table
  floated about 0.5 m above it.
- The projector's height appears nowhere in the config: the homography covers it. The Kinect mapping has to be
  recalibrated with the new pose.

**Tested:** the installed config reads 0.97 for both values. **Not tested:** live in RViz.

### Stale Brio projection corners moved aside (2026-09-25)

**What:** `config/projection_corners.yaml` was renamed to `config/projection_corners_old_brio.yaml`.

**Why:** the corners were clicked in the Brio image of the old setup (`frame_id: brio_optical_frame`). The Kinect launch
republished them, and `rviz_bridge` rightly warned about Kinect intrinsics with Brio pixels. Without the file,
`projection_corners_node` publishes nothing. Projection itself uses the homography and is unaffected.
- Alternative: stop starting `projection_corners_node` in the Kinect launch files. Deferred: that file holds
  uncommitted `use_depth` work.

### Objects in 3D (2026-09-29)

**What:**
- **`rviz_bridge` `on_objects`:** objects with `hull_contour_3d` (object_detector with `use_depth`) are drawn as their
  top outline where it was measured, moved from the optical frame into `world` (`p @ R.T + t`). Without it, they are
  projected onto the table as before. The label sits `LABEL_HEIGHT` above the outline's centre.
- **`par_framework_kinect.launch.py`:** `object_detector` gets `use_depth: True`.
- **`par_setup.yaml`:** new `object_detector_node` entry with `min_object_height: 0.0`, the optional filter for flat
  detections (e.g. pictures projected onto the table), off by default.
- `custom_interfaces` gets `Object.center_3d` / `hull_contour_3d`. The detector work is on branch `object-depth` in
  `src/object_detector`; both repos have their own log entries.

**Why:** your request, depth for objects like the markers and hands.
- The detector computes the 3D values, as the other two detectors do, and `rviz_bridge` only transforms them.
- The flat-object threshold is a per-setup value (depth-camera noise), so it lives in `par_setup.yaml`.
- Alternatives (a separate node, per-point depth, 3D boxes) are in `src/object_detector`'s log.

**Tested:** `rviz_bridge` passes 2/2 tests including flake8, and the Kinect launch parses. **Not tested:** live
(Kinect not connected).

### Projector calibration pattern at 4K (2026-09-30)

**What:** `par_setup.yaml`, `projection_calibrator_node`: new `projector_width: 3840` / `projector_height: 2160`, and
`marker_size_px` 250 -> 500.

**Why:** the projector is now a 4K one on display 2 (`HDMI-1`, 3840x2160 per `xrandr --listmonitors` and pygame). The
calibrator renders its marker pattern at `projector_width` x `projector_height`, which default to 1920x1080 and were
not set: on the 4K display the pattern would fill only the top-left quarter, and the stored mapping would carry the
wrong resolution and be fitted from one corner of the projection. 500 px keeps the markers as large on the table as
250 px was at 1080p.
- Alternative: read the resolution from the display instead of parameters. That is what the `projector-res-from-display`
  worktree in `src/surface_selector` is for; not touched here.
- Alternative: keep `marker_size_px: 250`. Rejected: half the physical size, harder for the 1080p colour camera to
  decode.

**Not tested:** the calibration itself has not been run with these values yet.

### camera_pose_calibrator no longer exhausts the memory (2026-09-30)

**What:** `camera_pose_calibrator.py`, `fit_table_plane`: both `np.linalg.svd` calls get `full_matrices=False`.

**Why:** with the Kinect in WFOV the calibrator froze the machine ("device memory is nearly full"). NumPy's default
`full_matrices=True` also computes the N x N matrix `U`, of which nothing is used: about 8.4 GB for the ~32 000
sampled points of a 1080p depth image, on a 14 GB machine. In NFOV only about half the pixels have depth (~2.4 GB), so
it was slow but survived. The normal is a row of the 3 x 3 `Vt`, which is the same either way.
- Alternative: a 3 x 3 covariance matrix and `np.linalg.eigh`. Same result and even less work, but a larger change
  than one argument, and the reduced SVD already needs under 1 MB. It is also what `object_detector`'s `depth.py` does.
- Alternative: a coarser `SAMPLE_STEP_PX`. Rejected: hides the problem, memory would still grow with N squared.

**Tested:** the package's 4 math tests pass under a 4 GB memory limit, peak 244 MB, about 1 s.

### camera_pose_calibrator finds the table next to floor (2026-09-30)

**What:** `camera_pose_calibrator.py`, `fit_table_plane`: the trimmed fit now starts from the points on the best of
200 planes through 3 random points (RANSAC, seeded, band `RANSAC_BAND_M` = 2 cm) instead of from all points. The
trimming loop after it is unchanged. New test `test_floor_beside_the_table_is_ignored`.

**Why:** with the Kinect moved and in WFOV, the calibrator refused an empty table: "only 2 % of the image is table".
38 % of the depth points were the shelf and floor around the table, 10-80 cm lower. The first plane, fitted through
all points, came out tilted 21 degrees and matched neither surface, so the 5 cm band around it kept 3.5 % of the points
and the trimming never recovered. A trimmed least-squares fit only works while the table is nearly everything in view
(NFOV, the old tests).
- Alternative: a wider first band. Rejected: any start from all points has the same weakness, it only moves the limit.
- Alternative: only use the image centre. Rejected: assumes where the table is, and measures tilt from a smaller area.
- Alternative: `cv2`/scikit RANSAC helpers. Not needed: 10 lines of NumPy, no new dependency.
- The seed makes the result repeatable: the same depth image gives the same pose.

**Tested:** the new test fails without the change (0.98 m instead of 0.93 m) and passes with it; 5/5 math tests pass.
On a frame from the real setup: 61.4 % table, RMS 1.8 mm, 0.958 m, tilt 8.7 degrees, 0.07 s, matching an independent
RANSAC fit.

### The measured camera pose is used, and the "clear table" check means what it says (2026-09-30)

**What:**
- **`launch_helpers.py` `mount_tf_publisher`:** uses `config/camera_pose_<camera>.yaml` next to `par_setup.yaml` while
  it exists (`<camera>` is the publisher's name without `_tf_publisher`, so `kinect` / `brio`), otherwise the
  placeholder under `/<name>` in `par_setup.yaml` as before. Prints which file the pose came from. All four launch
  files go through this function, so none of them changed.
- **`.gitignore`:** `config/camera_pose_*.yaml`, like the other calibration results of a physical setup.
- **`par_setup.yaml`:** the comment of `/kinect_tf_publisher` says it is the placeholder and what overrides it.
- **`camera_pose_calibrator.py`:** `fit_table_plane` also returns the share of points above the plane. New
  `MAX_ABOVE_FRACTION = 0.1`; `MIN_TABLE_FRACTION` 0.5 -> 0.25. The file header says where the file has to be to be
  used, and no longer exceeds the line length (the package's flake8 test passes again).
- **`camera_pose_calibrator_node.py`:** refuses on the share above the table as well, and the median over the frames is
  a masked median instead of `nanmedian`.
- **Tests:** `test_only_what_is_above_the_table_counts_against_it`.

**Why:**
- The pose file's header claimed it was used instead of the placeholder, but nothing read it: the values had to be
  copied into `par_setup.yaml` by hand.
  - Alternative: only correct the header. Rejected: keeps the manual copy, and a measured pose pasted over the
    placeholder cannot be told from one typed in.
  - Alternative: a launch argument for the pose file. Rejected: a convention next to `par_setup.yaml` needs no
    argument, as `projection_mapping_<camera>.yaml` already shows.
- "At least 50 % table" left little margin in WFOV (61 % with an empty table), because the floor around the table
  counts against it although it is harmless. What makes a measurement unreliable is what lies *above* the table:
  clutter, or a plane below the table being the largest one. So that is measured directly.
  - Alternative: only lower the limit. Rejected: with more floor than table in view the floor would be accepted as
    the table. With the new check the table then counts as "above" and the measurement is refused.
  - 0.25 stays as a lower limit so the tilt is measured from enough of the table.
- `np.errstate` does not silence `nanmedian`'s "All-NaN slice" warning (it is a Python warning), printed for pixels
  that never have depth. The masked median gives the same values (checked on random data) without it.

**Tested:** 8/8 tests of `camera_pose_calibrator` incl. flake8; `launch_helpers.py` flake8-clean; `mount_tf_publisher`
called with and without a pose file returns the measured pose and the placeholder; real frame: 61.4 % table, 0.3 %
above. **Not tested:** the launch files themselves with the pose file in place.

### Timestamp in the projection mapping file (2026-09-30)

**What:** `projection_mapping.py` `save()` adds `measured: '<ISO time, to the second>'` to
`projection_mapping_<camera>.yaml`. The round-trip test checks it.

**Why:** your request: the same key and format as in `camera_pose_<camera>.yaml`, so it is visible when each
calibration was made. The mapping depends on the camera pose, so a mapping older than the pose file is stale.
- In `save()`, not in the node or the `ProjectionMapping` message: it is the time the file was written, and the
  message, the calibrator and `custom_interfaces` stay unchanged.
- Loading ignores the key (the node reads the keys it knows), and files without it still load.
- Alternative: a comment line in the file header. Rejected: the pose file has it as a key, and a key can be read back.

**Tested:** `projection_mapping` 5/5 tests incl. flake8. **Not tested:** a real calibration run writing the file.

### Objects' measured centre in RViz (2026-10-01)

**What:** `rviz_bridge_node.py` `on_objects`: objects with depth (`hull_contour_3d`) also get a sphere marker
(namespace `center`, diameter `CENTER_SIZE` = 1.5 cm, the outline's green) at `center_3d`, moved from the optical frame
into `world` with the same transform as the outline. Objects without depth get none: they have no `center_3d`.

**Why:** your request, to see where the detector measured each object's depth (the centre of its top).
- Own namespace `center`: it can be switched off in RViz's MarkerArray display on its own.
- Alternative: anchor the label at `center_3d` instead of adding a marker. Rejected: not asked for, and the label sits
  5 cm above the point, so it would not show where the point is.
- Alternative: a POINTS marker. Rejected: a sphere has a size in metres and stays visible from every angle.

**Tested:** `rviz_bridge` 2/2 tests incl. flake8; the node, fed a camera 1 m above the table looking straight down and
an object top at 0.95 m depth, publishes the sphere at world z = 0.05, and none for an object without depth. **Not
tested:** live in RViz.

### RViz Kinect view: Views panel and docked camera image (2026-10-01)

**What:** `config/par_framework_kinect.rviz`: the `Views` panel is added to `Panels`, and a new `Window Geometry`
section docks Displays on the left, Views on the right and the "Kinect image" pane below Views.

**Why:** your request, the Views panel and the colour camera's image always visible by default.
- The config had no `Views` panel and no saved layout, so RViz arranged the docks itself on every start. Its default
  for new panes is `floating = true` (`addPane` in `rviz_common`), so the image pane can come up as a loose window.
  In the run I screenshotted it happened to be docked; with the saved layout it no longer depends on that.
- `QMainWindow State` is Qt's binary dock layout as hex. It was generated with PyQt6 (RViz uses Qt 6) from a window
  with docks named like RViz's (RViz names a dock after its panel, and `restoreState` matches by that name).
  - Alternative: arrange the panels in RViz by hand and save. Same result, but needs the GUI; documented in the file
    for future changes.
- No `X`/`Y`/`Width`/`Height`: the projector is the display at 0,0, so a saved position could open RViz on it.
- Only the Kinect config: `par_framework.rviz` (Brio) is unchanged.

**Tested:** RViz started with the old and the new config and screenshotted: the new one shows Displays, Views and the
Kinect image docked, with no floating windows.

### RViz Kinect view opens maximised (2026-10-01)

**What:** `config/par_framework_kinect.rviz`, `Window Geometry`: `Width: 1920`, `Height: 1080`, still no `X`/`Y`.

**Why:** your request: RViz maximised on start, on the screen being worked on (the one with the terminal that started
it), not as a floating window.
- RViz has no "maximised" option, only `--fullscreen` (no title bar, not what was asked).
- A Wayland terminal's position cannot be read by other programs, so "the terminal's screen" is approximated by where
  GNOME puts new windows: the current monitor. That only works without a fixed `X`/`Y`.
- GNOME's `auto-maximize` (on here) maximises a new window that opens at about the size of its monitor, so the
  monitor size in the config is enough.
- Tested three variants, all came up maximised: `Width`/`Height` in the config and `--qwindowgeometry 1920x1080`
  opened on the same monitor; `--qwindowgeometry 10000x10000` (meant to fit any monitor size) on a different one, so
  it was rejected. The config variant won over the command-line one: same result, one file.
- Limit: tuned to 1920x1080 monitors (all non-projector screens here). On a much larger monitor the window may not
  count as monitor-sized and stay unmaximised.

**Tested:** RViz started with the config: `_NET_WM_STATE_MAXIMIZED_HORZ/VERT` set, 1861x1043 on DP-1.

### Projector resolution read from the display (2026-10-01)

**What:** `par_setup.yaml`, `projection_calibrator_node`: `projector_width` / `projector_height` removed again; the
`display_id` comment says the resolution is read from that display.

**Why:** your request to move the projector-res worktree onto `rework` in `src/surface_selector`: the calibrator now
asks the display for its resolution, so the two parameters (added on 2026-09-30 for the 4K projector) are no longer
read. Left in, they would look authoritative while doing nothing.
- `marker_size_px: 500` stays: it is still in projector pixels and was chosen for the 4K projector. On a 1080p
  projector the markers are twice as large on the table.

### Calibration launch docstring, and the framework's projector-res worktree removed (2026-10-01)

**What:**
- `projection_calibration.launch.py`: the docstring says the projector resolution is read from the display; it still
  named `projector_width` / `projector_height`.
- The framework repo's own agent worktree `.claude/worktrees/projector-res` (branch `projector-res-from-display`,
  uncommitted changes from 2026-09-25) and its branch are removed.

**Why:** the docstring was outdated by moving the resolution lookup onto `rework` in `src/surface_selector`. The
worktree was the second one of that name: one existed in `src/surface_selector` (removed earlier today) and one here,
which kept appearing in PyCharm. Its other changes were already in place (Kinect height, frustum `Far clip`, removed
resolution parameters) or were dropped at your choice:
- `display_id` once under `/**` in `par_setup.yaml` (plus a note in `CLAUDE.md`): dropped. One value for both nodes,
  but less obvious which nodes read it; `display_id` stays under each node.
- Its 4 log entries described those changes and are dropped with them.

### Setup wizard (2026-10-01, branch `setup-wizard`)

**What:**
- **`packages/par_setup_wizard`** (new, ament_python, PySide6), started with **`scripts/wizard.sh`**, which sources
  ROS, `.venv` and `install/` in bash, exports `FASTDDS_BUILTIN_TRANSPORTS`, and names `local_build.sh` when
  nothing is built. The pages:
  1. profile: choose, create (a copy), quick start, rebuild the workspace;
  2. projector: `display_id`, with *Identify* and a test pattern;
  3. camera: Brio or Kinect, with a live preview;
  4. calibration: the steps that apply to the camera, with status and Run/Stop;
  5. nodes;
  6. start/stop.

  All process output goes into one log below the pages.
  - `profiles.py`: profiles are `par_setup.yaml` ("default") and `par_setup_<name>.yaml`, edited with `ruamel.yaml`
    round-trip. Also the Brio pose ↔ height/tilt conversion.
  - `hardware.py`: the Brio via `/dev/v4l/by-id/*BRIO*`, the Kinect via USB id `045e:097c` in sysfs, without ROS.
  - `displays.py`: the pygame side (display list, number, grid), run as a subprocess and reusing
    `surface_selector`'s `display_info` and `display_image`.
  - `preview.py`: rclpy subscription on its own thread. It keeps the newest frame, and a Qt timer draws it.
  - `par_setup_wizard.py`: the pages, plus `Processes` (`QProcess`; stop = SIGINT like Ctrl-C, kill after 10 s;
    everything stops when the wizard closes).
- **`par_framework_core`:**
  - `par.launch.py` (new): starts the camera and nodes named in the profile's new **`par_launch`** section, with the
    Kinect's topics, depth and remappings as in `par_framework_kinect.launch.py`. `camera_only:=true` starts just
    the camera and its TF.
  - `camera_pose_calibration_kinect.launch.py` (new): the Kinect driver and `camera_pose_calibrator`, writing
    `camera_pose_kinect.yaml`, then `Shutdown`.
  - `calibration.launch.py`: new argument `camera:=brio|kinect`.
  - `launch_helpers.py`: new `kinect_driver_node`, `camera_nodes`, `read_launch_section`.
  - `par_setup.yaml`: the `par_launch` section (Kinect, all nodes on, as in `par_framework_kinect.launch.py`).
  - `package.xml`: declares `camera_pose_calibrator`.
- `.gitignore`: `par_setup_*.yaml`. README: a wizard section, the layout and the package table. CLAUDE.md: the
  command.

**Why (your decisions in planning, unless noted):**
- *PySide6:* already installed through ROS (rqt), and `QWizard` provides the pages. Alternatives were Tkinter (no
  wizard widget), a web UI (new dependencies, a server, streaming for the preview) and a TUI (no images).
- *One new launch file instead of the wizard starting nodes itself:* it also works without the wizard, and what
  starts with which camera stays in launch files. The two existing framework launch files are unchanged.
  Suggestion: replace them with `par.launch.py` later.
- *Settings in the profile, comments kept:* `par_setup.yaml` stays the one source of truth. ruamel comes from apt
  (rosdep key `python3-ruamel.yaml`), not pip, so rosdep installs it like every other declared dependency.
- *`par_launch` with one bool per node (my choice):* every node parses the whole parameter file, and an empty list
  has no type rcl could infer, so `nodes: []` would have stopped every node from starting.
- *pygame in subprocesses (my choice):* SDL and Qt in one process compete for the window system. *Identify*
  exists because pygame reports only display sizes (three identical 1920x1080 here), which can't be matched to
  Qt's names (`DP-2`, `HDMI-1`, `eDP-1`).
- *One camera at a time;* multi-camera setups come later. The data model has one `camera` key for now.
- *Named profiles* for quick starts.
- *The projector page writes only `display_id`:* since commit 110f3cd the calibrator reads the resolution from the
  display.

**Tested:**
- The ruamel round trip of `par_setup.yaml` is byte-identical. The height/tilt conversion gives the existing
  placeholder at 0° and round-trips at 15°.
- All launch files parse. `par.launch.py` live: with a Brio profile it started exactly the Brio, its TF,
  fiducials and the projection nodes (the Brio itself was unplugged at that moment). With the Kinect,
  `camera_only:=true` started only the driver and its TF, with the measured pose, at 15 Hz.
- The wizard driven offscreen through all pages with the Kinect:
  - it listed the 3 displays;
  - it detected the Kinect and its serial, and showed the Brio as not connected;
  - the preview received frames;
  - the calibration rows showed the right status;
  - Start ran exactly the camera, TF and projection nodes; Stop ended with exit code 0;
  - `par_launch` was written to the profile.
- flake8 and pep257 are clean on all new code.
- **Not tested:** Identify and the test pattern on the real screens, the calibration runs from the wizard, the Brio
  path end to end, and the New profile / Rebuild buttons.

### Setup wizard: your feedback round (2026-10-01, branch `setup-wizard`)

**What:**
- **Profile page:** the profiles are shown in a list. *Start selected profile* (or a double-click) jumps to the
  Start page and starts the framework there.
- **Camera page:** the preview scales to fit its label (size policy `Ignored`, scaled with `KeepAspectRatio`)
  instead of being cropped.
  - With the Kinect it shows its settings: resolution, depth mode, fps, the colour controls of the extended
    driver, and the point clouds. They go into `k4a_ros_device_node` of the profile, typed as the driver
    declares them.
  - Combinations the Kinect can't run are blocked: 30 fps with `WFOV_UNBINNED` or `3072P`, manual values only in
    manual mode, and the RGB point cloud only with the point cloud.
- **Calibration page:** asks *automatic* or *manual* first, and the steps appear only after the choice.
  - Manual: the camera's distance and angle, then the four corners in `surface_selector`.
  - The distance/angle form now writes `camera_pose_<camera>.yaml`, marked `entered`, for both cameras. It asks
    before it replaces a measured pose.
  - The status shows measured or entered.
- **Timestamps:** "2 hours ago (today at 17:16)".
- **Log:** an "Output" heading and a placeholder text while it is empty.
- **`profiles.py`:**
  - `current_pose` / `save_manual_pose`.
  - `set_value` moves the comment that ruamel attaches to a section's last key over to a newly appended key.
    Without that, new keys landed between the next section's heading comment and that section.
  - New sections are `CommentedMap`s.
- **`surface_selector`** (its own repo, branch `rework`): `display_image` opens a real fullscreen window. See
  that repo's log.
- README: the wizard section is updated.

**Why:**
- *The pose form writes the pose file instead of the profile (my choice):* `mount_tf_publisher` prefers the pose
  file. If a manual pose went into the profile, an existing measured Kinect pose would silently override it. This
  way the file is the one current pose, whoever produced it. The pose files are shared by all profiles, like the
  mappings.
- *Fullscreen fixed in `surface_selector`, not just in the wizard (your choice):* the calibrator's markers go
  through the same function. With the top bar covering or shifting them, the mapping could come out wrong.
- *Manual still produces no table-to-projector mapping;* only `/projection_corners`, as before (you chose the
  corners plus distance and angle).

**Tested:**
- The pattern window is `_NET_WM_STATE_FULLSCREEN` (xprop, display 2), and SIGINT ends it with exit code 0.
- The wizard was driven offscreen with the Kinect:
  - the profile list, and *Start* directly from page 1, then Stop;
  - the Kinect settings (30 fps disabled with WFOV_UNBINNED, enabled with NFOV_UNBINNED), and the driver started
    with the stored settings;
  - the preview at 630x354 in a 630x428 label;
  - no calibration steps before the choice, the right rows for automatic and manual, and the status texts;
  - the timestamps;
  - the manual-pose round trip, on a throwaway camera name.
- The profile round trip is still byte-identical, new keys sit before the next section's comment, and a new
  section takes several keys. flake8 and pep257 are clean.
- **Not tested:** the fullscreen look on the screen itself (it needs your eyes), the pose form's Save and the
  replace question in the window, and running the corner clicking from the wizard.

### Setup wizard: new profiles start fresh, no Cancel button (2026-10-01, branch `setup-wizard`)

**What:**
- *New profile* copies `par_setup.yaml` (no longer the selected profile) and unsets the wizard's choices:
  `display_id: -1` for both projector nodes, `par_launch.camera: ''` and all nodes off.
  - The projector and camera pages preselect nothing then, and Next stays disabled until a choice is made
    (`isComplete`).
  - The Kinect settings appear only once the Kinect is chosen.
  - The calibration mode is asked anew for every profile.
  - *Start selected profile* refuses a profile that isn't set up yet and says why.
- The Cancel button is gone (`QWizard.NoCancelButton`); the window's close button still ends the wizard and stops
  what it started.
- `Profile.set_value` writes strings as ruamel `PlainScalarString`. With `preserve_quotes`, a replaced value kept
  the quotes of the old one (`camera: 'kinect'` after `''`).

**Why:** you expected a new profile to start from defaults, with the wizard asking everything anew; before, it
was a copy of the selected profile, so every page looked unchanged.
- *Explicit unset values instead of deleting keys (my choice):* ruamel attaches the comment lines above a key to
  the key before it, so deleting keys would have taken the next keys' comments with them.
- *Only the choices are unset;* camera tuning, QoS and the marker dictionary keep the defaults of `par_setup.yaml`.

**Tested (offscreen):**
- New profile → start refused with the message.
- Projector and camera pages: nothing selected, Next disabled, then enabled after a choice. The Kinect settings
  only appear for the Kinect.
- No calibration mode, all nodes off, and no Cancel button.
- The profile diff against `par_setup.yaml` shows only the choices and the stored Kinect settings.
- The unchanged round trip is still byte-identical, and `camera: kinect` is written unquoted. flake8 and pep257
  are clean.

### Setup wizard: delete profiles, Back only when it works (2026-10-01, branch `setup-wizard`)

**What:**
- **Delete profile…** on the first page: it asks with the file name, then `profiles.delete_profile` removes the
  file and the default is selected again. The button is disabled for the default profile, which
  `delete_profile` refuses as well.
- **Back** is shown only while it is enabled, i.e. hidden on the first page.

**Why:** your request.
- *The default can't be deleted:* `par_setup.yaml` is tracked in git and the template for new profiles.
- *The calibration files stay:* the pose, mapping and corner files sit next to the profiles and are shared by all
  of them.
- *Back:* QWizard can only enable or disable it, so its visibility follows the enabled state after every page
  change. That update is queued (`QTimer.singleShot(0)`) to run after QWizard's own button update.

**Tested (offscreen):**
- Back is hidden on page 0, shown on page 1, and hidden again after going back.
- Delete is disabled for the default and enabled for a test profile; after confirming, the file is gone and the
  default is selected.
- flake8 and pep257 are clean.

### Setup wizard: Ctrl+C ends it (2026-10-01, branch `setup-wizard`)

**What:** in `main()`:
- `rclpy.init(signal_handler_options=SignalHandlerOptions.NO)`;
- a SIGINT handler that closes the window;
- a 200 ms no-op `QTimer`.

**Why:** your report, Ctrl+C did nothing.
- Python only runs signal handlers between its own instructions, and Qt's event loop waits in C++. The timer hands
  control back to Python regularly.
- rclpy's own SIGINT handler only shut the ROS context down and left the window open.
- Closing the window takes the normal path: the preview and every process the wizard started are stopped. On
  Ctrl+C in a terminal the children get the SIGINT themselves as well, since they are in the same process group.

**Tested:** `./scripts/wizard.sh` offscreen in its own process group, then SIGINT to the whole group (as the
terminal sends it): the group was empty after 0.25 s; flake8 is clean.

### Manual corner calibration ends by itself (2026-10-01, branch `setup-wizard`)

**What:** `calibration.launch.py` gives the surface selector `on_exit=Shutdown`, like the projector calibration
launch files. The docstring says so, and the wizard's step text is now "click the four corners; Esc cancels".

**Why:** your report: after the four clicks the wizard still showed "Not done yet" and "Stop". The corners were
stored (`projection_corners.yaml`, 13:37), and the selector ended itself. But the camera and
`projection_corners_node` kept the launch running, so the wizard never saw the step end and never refreshed the
status. Ending the launch with the selector loses nothing: `projection_corners_node` writes the file before it
answers the selector, and the selector only ends after the answer. Esc (cancel) ends the launch the same way.

**Tested:** `calibration.launch.py camera:=kinect` live. After SIGINT to the surface selector (a clean exit), the
whole launch ended within a second, every process clean, exit code 0. **Not tested:** clicking the corners in the
wizard itself.

### Generic webcam as a third camera (2026-10-01, branch `setup-wizard`)

**What:** `camera: webcam` next to `brio` and `kinect`, backed by `v4l2_camera` (apt/rosdep
`ros-lyrical-v4l2-camera`, declared as `exec_depend` of `par_framework_core`).
- `launch_helpers.py`: `webcam_nodes()` starts `v4l2_camera_node` as `/camera/webcam/webcam_node`, plus a static
  TF `webcam_link -> webcam_optical_frame` (what the Brio node publishes itself). `camera_nodes()` adds the mount
  TF from `/webcam_tf_publisher` / `camera_pose_webcam.yaml`. `WEBCAM_REMAPPINGS` and a `CAMERA_REMAPPINGS` dict
  per camera.
- `par.launch.py`: per-camera detector overrides (`CAMERA_OVERRIDES`); the webcam points `object_detector` at the
  raw topic, as the Kinect does. New `par_framework_webcam.rviz` (the Brio config with the webcam topics).
- `calibration.launch.py`: `camera:=webcam`. `projection_calibration.launch.py`: new `camera` argument (brio or
  webcam) instead of a hard-coded Brio; the Kinect keeps its own file.
- `par_setup.yaml`: `/camera/webcam/webcam_node` (device, 640x480 YUYV, `bgr8`, frame id) and a placeholder
  `/webcam_tf_publisher`.
- Wizard: "Generic webcam" in the camera list. Detection = the first `/dev/v4l/by-id/*-video-index0` that is not
  the Brio or the Kinect's colour camera; choosing it stores that by-id path as `video_device`. The calibration
  page offers intrinsics (checkerboard), the pose by hand, and the projector mapping via
  `projection_calibration.launch.py camera:=webcam`.
- `src/logitech_brio/calibration/run_cameracalibrator.sh` (separate repo): optional `CAMERA_NAMESPACE`, default
  `/camera/brio`, so the wizard reuses it for the webcam.

**Why / alternatives:**
- A separate driver, not the Brio node: that node forces MJPEG, publishes undecoded JPEGs and sets Brio-only
  `v4l2-ctl` controls, which many laptop webcams don't support.
- `v4l2_camera` over `usb_cam` (your choice): fewer options to get right, camera controls as ROS parameters.
  It publishes RELIABLE, which the framework's BEST_EFFORT subscribers receive too.
- Calibration file `config/camera_info_webcam.yaml`, set by the launch helper, instead of camera_info_manager's
  default `~/.ros/camera_info/<card name>.yaml`: the wizard knows the path for its status, and it survives
  container rebuilds like the other calibrations.
- `CAMERA_NAMESPACE` in the existing calibrator script instead of a copy: the script holds four camera_calibration
  workarounds that would otherwise be duplicated. Passing a second `--ros-args -r` block would also work (rcl
  applies the first matching remap), but only through that rule, which nobody would guess from reading it.
- Default 640x480 YUYV: the size practically every UVC camera offers uncompressed; raise it in the profile.

### Setup wizard: details for each display (2026-10-01, branch `setup-wizard`)

**What:**
- `displays.py list` returns name, position and size per SDL display index. It calls `SDL_GetDisplayName` and
  `SDL_GetDisplayBounds` through `ctypes`, in the SDL library pygame loaded (found in `/proc/self/maps`). Without
  one, it falls back to the sizes as before.
- The projector page's `describe_display` adds Qt's model, refresh rate and primary flag for the screen at the same
  position, e.g. `Display 0: HDMI-1 24" · DELL U2419H · 1920 x 1080 @ 60 Hz · at 0,0`. The README says so.

**Why:** your request. `display_id` is SDL's index, and pygame exposes only sizes for it, so identical screens looked
the same.
- *The very library pygame loaded:* it guarantees the same display order `display_id` refers to. A separately
  loaded SDL could differ.
- *Matched to Qt by position, not by index:* SDL and Qt count the displays in different orders, but both use the
  same desktop coordinates.

**Tested:** on the two current screens, `list` gave `HDMI-1 24"` at 0,0 and `DP-1 24"` at 1920,0. Qt matched both
(DELL U2419H, 60 Hz; DP-1 primary). flake8 and pep257 are clean. **Not tested:** with the projector connected.

### page_locator in the framework (2026-10-01, branch `rework`)

**What:** the ported page tracker (`page_locator`, repo `ros2-par-framework-page-locator`, design notes in its own
`claude_usage_documentation.md`) is wired in:
- `config/nodes.list`: new entry, branch `main` like the others. `sync_nodes.sh` leaves an existing checkout on another
  branch untouched, so the `rework` checkout keeps working and the line needs no change after the merge.
- `par.launch.py`: `page_locator` joins the detector loop, switched by `par_launch.page_locator`. No camera overrides:
  it only reads `/fiducials`, which `fiducials_detector` publishes for every camera.
- `par_setup.yaml`: a `page_locator_node` block (page and marker size, `max_pages`, hold time, smoothing) and the
  `par_launch` switch. The setup wizard lists it as "Page locator (needs fiducials)".
- `rviz_bridge`: `/pages` → `/pages/markers`, outline + `page#<id>` label, through `pixels_to_table` like the 2D
  fiducials. The paper lies on the table, so the plane is where its corners are even with the Kinect. A "Pages"
  display was added to all three RViz configs.

**Why these choices:** page layout values are parameters of the printed sheets, so they belong with the other
per-setup values in `par_setup.yaml`, not in node code. `max_pages` keeps page marker ids (`0 .. 4 * max_pages - 1`)
below the projected calibration markers 90-98; the old node had a page group 96-99 that overlapped them.

**Alternatives:** have `par.launch.py` start `fiducials_detector` automatically when `page_locator` is on. Rejected
to keep one switch per node; the dependency is noted next to the switch and in the wizard label instead.

**Layout (later the same day):** the `page_locator_node` block also sets the page layout (`marker_margin_mm`,
`marker_corners`, `marker_quarter_turns`), set to the VIGITIA book pages with 20 mm markers, which page_locator now
uses as default. The reasoning is in page_locator's own documentation.

**Calibration marker ids and page layout (later the same day):** a live test showed that the printed VIGITIA
documents carry markers 96-99, which overlap the projected calibration markers 90-98. `projection_calibrator_node`
`marker_ids` in `par_setup.yaml` moved to 50-58: they are only used while calibrating, the stored
`projection_mapping_<camera>.yaml` stays valid. The calibrator's code default in `surface_selector` is still
`range(90, 99)`; every launch file passes `par_setup.yaml`, which overrides it. The `page_locator_node` block now
holds the documents' layout (measured: 20 mm markers, 5 mm margin, markers turned three quarters) and `max_pages: 25`.
- Alternative: reprint the documents with ids below 32 and keep 90-98. Rejected: the existing sheets would stop
  working.

### `par_framework.rviz` renamed to `par_framework_brio.rviz` (2026-10-01, branch `rename-brio-rviz`)

**What:** `git mv` of the Brio RViz config; `par.launch.py` (`RVIZ_CONFIGS`), `par_framework.launch.py` and the "copy
of" comments in the Kinect and webcam configs follow. `setup.py` installs `config/*.rviz` by glob and needs no change.

**Why:** the file only shows the Brio (its frustum, image and topics), and its siblings are already named by camera
(`_kinect`, `_webcam`), which `par.launch.py` picks by the camera key. The unsuffixed name dates from when the Brio was
the only camera.

**Alternatives:** also rename `par_framework.launch.py` to `par_framework_brio.launch.py` for full symmetry. Not done:
it is the documented entry point (`./scripts/launch.sh par_framework`), and the generic `par.launch.py` may replace
the per-camera launch files anyway. Earlier entries of this log keep the old name, as history.

**Note:** after pulling this, rebuild `par_framework_core` (`./scripts/build_workspace.sh par_framework_core` or
`./scripts/local_build.sh par_framework_core`), so the new name is installed; until then RViz finds no Brio config.

### Camera calibration shared by all cameras (2026-10-01, branch `rework`)

**What:**
- The Brio's intrinsics move from its driver repository (`src/logitech_brio/calibration/${NAME}.yaml`) to
  `config/camera_info_brio.yaml` next to `par_setup.yaml`, where the webcam's `camera_info_webcam.yaml` already was:
  `launch_helpers.logitech_brio_node` sets `camera_info_url` with `next_to_params_file`, like `webcam_nodes`.
- Removed: the `camera_info_url` launch argument of `par.launch.py`, `par_framework.launch.py`,
  `calibration.launch.py` and `projection_calibration.launch.py` with their host-run instructions, the container-only
  `camera_info_url` in `par_setup.yaml`, and the wizard's `LAUNCH_FILES_WITH_CAMERA_INFO_URL`. The wizard finds every
  camera's intrinsics as `camera_info_<camera>.yaml` in the config folder.
- The camera-agnostic tools move from the Brio repository to `scripts/`: `run_cameracalibrator.sh` (only its header
  changed), `generate_checkerboard.py` and `checkerboard.png`. Their earlier history stays in the Brio repository.
- `.gitignore`: `config/camera_info_*.yaml`, like the other calibration results of a physical setup.

**Why:** the calibration is data of one physical setup, which the framework keeps next to `par_setup.yaml`; a
driver repository should stay usable on its own without it. The old path also differed between the container
(`/ros2_ws/src/...`) and the host, which is what the `camera_info_url` launch argument in four launch files and the
wizard existed for. `next_to_params_file` resolves to the same source folder in both, so that plumbing goes away.

**Trade-offs:** a fixed file name per camera type instead of `${NAME}`, i.e. one Brio per setup, as the projection
mapping files and TF names already assume. A calibration saved from inside the container is a root-owned file on the
host, as with the projection mapping. Calibration results are not tracked by git (decision of the maintainer), so a
fresh clone needs a calibration run or a copied file.

**Alternatives:** keep the file in the driver repository and only move the tools (rejected: the host/container path
plumbing stays); track `camera_info_*.yaml` in git (rejected: the values belong to one camera unit and machine).

**Migration:** copy an existing `src/logitech_brio/calibration/Logitech_Brio.yaml` to `config/camera_info_brio.yaml`;
its `camera_name` stays `Logitech_Brio`, which the node still expects, so no recalibration is needed.

**Comments of `run_cameracalibrator.sh` (later the same day):** the header now describes the script as the framework's
calibrator for any camera node with `set_camera_info` (usage for the Brio and the webcam, where COMMIT writes the
result, that the Kinect needs none, and which QoS each camera needs), instead of a Brio tool. Comments only.

### Camera-generic calibration launches (2026-10-01, branch `rework`)

An audit for camera-specific code found three small spots, fixed here (a larger one, the Brio's topic names as the
framework's camera interface, is noted below as not done).

**Projection corners per camera:** `projection_corners_node(context, camera)` stores
`config/projection_corners_<camera>.yaml`, like `projection_mapping_<camera>.yaml`. The corners are pixels of one
camera's image; with one shared file, switching cameras republished the other camera's corners (this happened with
the Brio's corners under the Kinect). Callers: `par.launch.py` and `calibration.launch.py` pass their camera,
`par_framework.launch.py` / `par_framework_kinect.launch.py` their fixed one. The wizard checks the camera's file,
`.gitignore` ignores `projection_corners_*.yaml`. Migration: an existing `projection_corners.yaml` is renamed to the
camera it was clicked with (its `frame_id` tells: `brio_optical_frame`, `rgb_camera_link` = Kinect,
`webcam_optical_frame`).

**One projection calibration for all cameras:** `projection_calibration_kinect.launch.py` is deleted. It started
exactly what `projection_calibration.launch.py camera:=kinect` starts through `camera_nodes()` (driver, mount TF,
`KINECT_REMAPPINGS`, fiducials detector, mapping owner, calibrator); only the argument's description excluded the
Kinect. The wizard's Kinect branch is gone.

**Camera from the profile:** `calibration.launch.py` and `projection_calibration.launch.py` defaulted to
`camera:=brio`, while `par.launch.py` takes the camera from `par_launch`. By hand, a Kinect profile without
`camera:=kinect` silently started the Brio. Both now default to empty and use `launch_helpers.chosen_camera`: the
argument if given, else `par_launch.camera` from `params_file`; an unknown or empty camera stops with an error that
names the fix.
- Alternative: drop the argument and always use the profile. Rejected: the wizard and quick tests pass a camera
  explicitly, and the argument costs nothing.

**Not done (decision pending):** the consumer nodes subscribe to the Brio's topic names (`/camera/brio/...`), which
other cameras are remapped onto (`CAMERA_REMAPPINGS`). It works on every launch path; a neutral camera interface
would touch six node repositories. The per-camera launch files `par_framework*.launch.py` duplicate `par.launch.py`
but are the documented entry points.

### Neutral camera interface `/camera/...` (2026-10-01, branch `rework`)

**What:** the framework nodes subscribe to camera-neutral topics: `/camera/image_raw` (and the Brio's own JPEGs on
`/camera/image_raw/compressed`), `/camera/camera_info`, `/camera/set_camera_info`, and `/camera/depth_registered/image_raw`
(depth on the colour image's pixel grid, the usual ROS name for it). `launch_helpers.DRIVER_REMAPPINGS` remaps each
driver onto them where it is started (`logitech_brio_node`, `kinect_driver_node`, `webcam_nodes`, the driver in
`par_framework_kinect.launch.py`, and the wizard's direct Brio start for the intrinsics). The consumer remappings
(`CAMERA_REMAPPINGS`, `KINECT_REMAPPINGS`, `WEBCAM_REMAPPINGS`) and every `remappings=` on framework nodes are gone.
Changed to the neutral names: `rviz_bridge`, `camera_pose_calibrator`, the three RViz configs, `surface_selector_node`'s
`topic_name_frame` in `par_setup.yaml`, the object detector overrides in the launch files, the wizard's preview
(`hardware.IMAGE_TOPICS` removed) and `run_cameracalibrator.sh` (default namespace `/camera`, so no
`CAMERA_NAMESPACE` for the webcam any more). The node repositories `fiducials_detector`, `hand_landmarks`,
`object_detector` and `surface_selector` change their constants and defaults in their own branches.

**Why:** the Brio's names were the de facto interface: six consumers hard-coded `/camera/brio/...` and other cameras
were remapped *onto the Brio's names*, so a webcam setup subscribed to "brio" topics, and `camera_info` was not even a
parameter in some nodes. Now only the driver start knows a driver's names; a new camera needs a driver start and a
`DRIVER_REMAPPINGS` entry, and no consumer changes.

**Kept:** the drivers themselves, their node names (so the `par_setup.yaml` keys stay), TF frames and QoS (the Brio
still publishes best effort, see the QoS trap). `ros2 topic list` shows the neutral names while the framework runs;
a driver started by hand without the launch files publishes its own names.

**Alternatives:** put every driver directly into the `/camera` namespace instead of remapping (rejected: the Brio sets
its namespace in code and its node name is the key of its parameters in `par_setup.yaml`); make every topic a
parameter of every consumer (rejected: more configuration for a value that is the same for all of them).

### `par.launch.py` as the only framework entry point (2026-10-01, branch `rework`)

**What:** `par_framework.launch.py` (Brio) and `par_framework_kinect.launch.py` are deleted; `par.launch.py` starts the
framework for every camera. It takes the camera and the node switches from the profile's `par_launch` section, and
each can be overridden for one run with a launch argument: `camera:=` (through `launch_helpers.chosen_camera`) and
`object_detector:=`, `fiducials_detector:=`, `hand_landmarks:=`, `page_locator:=`, `rviz:=` (`true`/`false`, empty
= the profile's value; any other value stops with an error). `scripts/launch.sh` starts `par` by default (it started
`par_framework`); README, CLAUDE.md, a `par_setup.yaml` comment, the Kinect RViz config's header and the
projection_corners error message follow.

**Why:** three entry points had drifted apart: `par_framework.launch.py` started no detectors, the Kinect file always
started all of them with RViz, and `page_locator` existed only in `par.launch.py`. Every new node had to be added in
several places. The launch arguments keep the per-run convenience of the old files (`rviz:=true`) without editing the
profile.

**Equivalents:** the old Brio launch = `./scripts/launch.sh par camera:=brio object_detector:=false
fiducials_detector:=false hand_landmarks:=false page_locator:=false` (plus `rviz:=true` for its option); the old
Kinect launch = `./scripts/launch.sh par camera:=kinect page_locator:=false rviz:=true` with the other detectors on.

**Alternatives:** keep the old files as thin wrappers around `par.launch.py` (rejected: still several entry points to
document and keep in step, for names that only habit needs); no override arguments, the profile only (rejected: a
quick test would mean editing the YAML).

**Live test and a driver fix (later the same day):** with the Azure Kinect, the remapped driver advertised
`/camera/image_raw` but published nothing. The driver decides per frame whether to publish with
`count_subscribers("rgb/image_raw")`, and rclcpp resolves that name *without* the remap rules, while the publishers
were created with them: a remapped topic always counted zero subscribers. Verified A/B on the same device: 15 Hz
unremapped, 0 Hz remapped. The Brio is not affected (it asks its publisher, `get_subscription_count()`, which follows
remapping).
- Fix in `src/azure_kinect_ros_driver`, branch `remap-aware-subscriber-count`: a helper `countSubscribers()` resolves
  the name with the remap rules (`get_node_topics_interface()->resolve_topic_name()`) before counting; all 15 checks
  use it. The branch also carries the earlier, still uncommitted port fixes for this ROS distribution (cv_bridge
  header, `ImageTransport` constructor, CMake), which the driver needs to build here.
- The driver is a third-party fork (`nlouman/azure_kinect_ros_driver_extended`). To keep the fix: fork it to
  `github.com/vigitia`, push the branch there, and point the `azure_kinect_ros_driver` line in `config/nodes.list` at
  the fork. Until then a fresh `./setup.sh` clones the unpatched driver, and the Kinect publishes nothing.
- Verified live afterwards: `par.launch.py camera:=kinect` delivers about 15 Hz on `/camera/image_raw` and
  `/camera/depth_registered/image_raw`; with all detectors running, fiducials (with 3D corners), hands, objects, pages
  and rviz_bridge's markers all arrive through the neutral names.
- Alternatives: remap only the consumers for the Kinect (rejected: the interface would not be uniform again); a relay
  node per topic (rejected: copies every 1080p frame and the depth image once more).
- Note for `--symlink-install`: after deleting launch files, `build/` keeps dangling symlinks to them and the next
  build of `par_framework_core` fails ("can't copy ... doesn't exist"). `find build/par_framework_core
  install/par_framework_core -xtype l -delete` removes just those.

## 2026-10-08: RealSense driver in `config/nodes.list`

**What changed:** `config/nodes.list` lists `realsenseai/realsense-ros` under Sensors, checked out as
`src/realsense2_camera` on branch `ros2-master`.

**Why:** It adds support for Intel RealSense depth cameras as another camera option.

**Decisions:**
- *Branch `ros2-master` named explicitly* instead of `-`. It is the remote's current default, but naming it keeps a
  later upstream change of the default branch from silently switching what gets built, the same way the other
  entries name `main`.
- *Directory `realsense2_camera`*, after the main package, following the list's "use the ROS package name"
  convention. The repo also holds `realsense2_camera_msgs` and `realsense2_description`; staging finds all three
  one level down and keys them by their declared names.
- *No Docker workaround needed*, unlike the Kinect: `librealsense2` has a rosdep rule and a released apt package for
  this distribution, so the image resolves it through the normal `package.xml` path.
- *Alternative considered:* the driver is also released as an apt package (`ros-<distro>-realsense2-camera`), which
  would avoid building it from source. Kept as a source checkout because it was asked for this way, and because
  it allows patching the driver like the other nodes.

## 2026-10-08: RViz configs in `config/rviz/`

**What changed:** the three `par_framework_<camera>.rviz` files moved from `packages/par-framework-core/config/` to
`config/rviz/` (with `git mv`, so the history follows them). `setup.py` installs them with their own `data_files` entry
to `share/par_framework_core/config/rviz`, and `par.launch.py` adds `rviz` to the path it hands to `rviz2 -d`.

**Why:** your request: the config folder mixes per-setup parameters, machine-local calibrations and RViz layouts;
the layouts are a different kind of file and now sit apart.

**Decisions:**
- *A separate `data_files` entry instead of a recursive glob:* `data_files` installs a list of files into one target
  directory, so `config/*` cannot reproduce a subfolder; each installed folder needs its own entry. Without it the
  files would silently stop being installed and RViz would open with an empty layout.
- *Only the path in `par.launch.py` changed,* `RVIZ_CONFIGS` keeps the bare file names, so it stays the one place
  that maps a camera to its layout.

**Tested:** host build of `par_framework_core` (with `--base-paths src packages`, as `local_build.sh` does; without it
colcon also finds the staged manifest in `docker/deps/` and stops on a duplicate package name). All three files
resolve at the path `par.launch.py` builds. A `--symlink-install` tree keeps dangling links to the old locations
until they are removed (`find build/par_framework_core install/par_framework_core -xtype l -delete`), and the
container's build volumes need `./scripts/build_workspace.sh par_framework_core` once.

## 2026-10-11: Setup wizard lists the displays again

- **What:** `par_setup_wizard/displays.py` imports its display helpers from `surface_selector.utils`
  (`get_connected_displays`, `get_resolution_of_display_by_id`, `display_calibration_image`) instead of the
  modules `surface_selector.display_info` and `surface_selector.show_white_fullscreen`.
- **Why:** a cleanup in `surface_selector` merged those two modules into `utils.py` under new names. The
  display listing runs as a subprocess of the wizard, so the import error only killed that subprocess, and the
  projector page showed no displays instead of an error.
- **Alternatives:** restoring the old modules in `surface_selector` was rejected, it would undo that repo's
  cleanup for one caller. Copying the helpers into the wizard was rejected too: the projector calibration in
  `surface_selector` uses the same functions, so the wizard and the calibration count displays the same way only
  while they share them. Note that `display_calibration_image` raises on a size mismatch (display scaling not at
  100 %) where the old function only printed a warning, so the identify and grid views now end in that case.

## 2026-10-11: Camera pose calibration works with things standing on the table

- **What:** `camera_pose_calibrator.py`, `fit_table_plane`: RANSAC no longer takes the plane with the most points
  but the one nearest to the camera that holds at least `MIN_TABLE_FRACTION` (25 %) of the points and is tilted at
  most `MAX_TABLE_TILT_DEG` (45 degrees) against the view direction. `RANSAC_ITERATIONS` 200 -> 1000; a candidate
  farther away than the best so far is skipped before its points are counted. The share of points above the table
  and `MAX_ABOVE_FRACTION` are gone, `fit_table_plane` returns 4 values, 0 % table when no plane qualifies. The
  node refuses only on too little table or a non-flat one, with one message each. The test for the above-share is
  replaced by `test_cluttered_table_above_more_floor_is_found`.
- **Why:** a camera that sees much more than the projection area also sees a desk that cannot be cleared. The plane
  fit found the desk, but the measurement was refused because more than 10 % of the image was above it. That check
  was also the only guard against fitting the floor when more floor than free table is in view; choosing the nearest
  large plane replaces it: the floor is farther away, objects on the table are too small, a wall or a box side is
  tilted too far.
- **Alternatives:** raising `MAX_ABOVE_FRACTION` was rejected, it only moves the limit to the next more cluttered
  desk. Checking the measured height against the placeholder height in `par_setup.yaml` was rejected, it is only as
  good as a hand-entered value. Fitting only inside the projection corners was rejected, for a new setup they belong
  to the old one. Known limit: a flat surface above the desk that covers a quarter of the image (a large shelf) would
  be taken for the table.
- **Tested:** 6/6 math tests. The new test fails with the previous code (it fits the floor and refuses) and passes
  with this one. flake8 reports only the three errors already in `camera_pose_calibrator_node.py`.

## 2026-10-11: `marker_size_px` removed from the profiles

- **What:** the `projection_calibrator_node` section of the profiles in `packages/par-framework-core/config/`
  no longer has `marker_size_px`.
- **Why:** `surface_selector` now derives the size of the projected markers from the projector's resolution
  (largest size that fits the grid), and the node no longer declares the parameter. A leftover key would be
  ignored silently and suggest a setting that does nothing.
- **Alternatives:** keeping the key as an optional override was rejected: no setup needs a smaller pattern, and
  a wrong value is exactly what made the rows overlap before.

## 2026-10-11: camera pose placeholders marked as "do not edit"

- **What:** the comments on `/brio_tf_publisher`, `/webcam_tf_publisher` and `/kinect_tf_publisher` in
  `packages/par-framework-core/config/par_setup.yaml` now mark them as placeholders not to be edited, and name
  where the real pose comes from (`camera_pose_<camera>.yaml`, written by the setup wizard or
  `camera_pose_calibrator`). Values unchanged.
- **Why:** the entries look like the place to set the camera pose, and the Brio's comment even said "replace with
  measured values". But `launch_helpers.mount_tf_publisher` ignores them as soon as a pose file exists, and both
  pose tools copy what they do not set (x/y position, the Kinect's rotation about the vertical) from them, so an
  edit is either silently ignored or leaks into later measurements.
- **Alternatives:** moving the placeholder into `launch_helpers` as a Python constant was rejected: the launch
  files, the wizard (`profiles.current_pose`) and `camera_pose_calibration_kinect.launch.py` all read it from the
  profile, and hardware defaults belong in `par_setup.yaml` by the repo's convention. Removing the entries was
  rejected: launching without a pose file would then fail with a `KeyError`.

## 2026-10-11: named profiles moved to `config/profiles/<name>.yaml`

- **What:** the setup wizard's named profiles are now `config/profiles/<name>.yaml` instead of
  `config/par_setup_<name>.yaml` (`profiles.profiles_dir`, `profile_path`, `list_profiles`, `create_profile`, which
  creates the folder). The default stays `config/par_setup.yaml`. `launch_helpers.next_to_params_file` now resolves
  to the folder of the real default `par_setup.yaml` instead of the folder of `params_file`. `.gitignore` ignores
  `config/profiles/`. Docstrings, the wizard's subtitle and the README name the new path.
- **Why:** keeps the config folder readable: the tracked default and the shared calibrations on top, every
  machine-local profile below. The calibrations stay shared by all profiles (keyed by camera, as documented): with
  the old `next_to_params_file`, a launch with a profile from the subfolder would have written its calibrations
  into `config/profiles/`, while the wizard reads them from `config/`.
- **Alternatives:** per-profile calibrations in a folder per profile (`config/profiles/<name>/par_setup.yaml`) were
  rejected for now: it changes the documented sharing, and the wizard would have to read calibrations from the
  profile's folder. Keeping the `par_setup_` prefix inside the subfolder was rejected as redundant. Renaming
  `next_to_params_file`, whose `context` argument is now unused, was left out to keep the change small. Existing
  profiles are moved by hand, not migrated by code.

## 2026-10-11: `next_to_params_file` renamed to `config_file`, unused `context` arguments removed

- **What:** `launch_helpers.next_to_params_file(context, file_name)` is now `config_file(file_name)`;
  `webcam_nodes`, `projection_corners_node` and `projection_mapping_node` no longer take `context`, and their callers
  in `par.launch.py`, `calibration.launch.py`, `projection_calibration.launch.py` and
  `camera_pose_calibration_kinect.launch.py` are updated. `par_framework_core/package.xml` declares
  `ament_index_python`, which the launch files and now `launch_helpers` import.
- **Why:** since the calibrations resolve to the shared config folder, the helper no longer reads `params_file`, so
  its name described something it no longer does and its `context` was unused; the three node helpers only had
  `context` to pass it on. The dependency was used without being declared, against the rule that `package.xml`
  declares everything (it only worked because the ROS base ships it).
- **Alternatives:** keeping the old signatures for compatibility was rejected: every caller is in this package, so
  the rename is complete and a leftover `context` would suggest a dependency on the launch arguments that is gone.

## 2026-10-11: calibrations moved to `config/calibration/intrinsics/` and `config/calibration/extrinsics/`

- **What:** the camera intrinsics (`camera_info_<camera>.yaml`) are now in `config/calibration/intrinsics/`; the
  camera poses (`camera_pose_<camera>.yaml`), the table-to-projector mappings (`projection_mapping_<camera>.yaml`)
  and the projection corners (`projection_corners_<camera>.yaml`) in `config/calibration/extrinsics/`. File names are
  unchanged. `launch_helpers` has the constants `INTRINSICS` / `EXTRINSICS`, and `config_file` creates the file's
  folder. The wizard (`par_setup_wizard.py`, `profiles.pose_file`) builds its calibration paths with
  `config_file` and the constants instead of joining them to `config_dir()` itself. `.gitignore` ignores
  `config/calibration/` instead of four file patterns. Docstrings, parameter descriptions, `par_setup.yaml`,
  `CLAUDE.md`, the README and `run_cameracalibrator.sh` name the new paths.
- **Why:** `config/` showed the tracked default profile between machine-local calibration files; now it holds
  `par_setup.yaml`, `profiles/`, `calibration/` and `rviz/`. Projector mapping and corners count as extrinsics: like
  the camera pose they describe where things sit relative to the table. The folder is created in `config_file`
  because none of the writers creates it: `camera_info_manager`'s `saveCalibrationFile` (despite its comment),
  `camera_pose_calibrator.save` and the wizard's `save_manual_pose` all just open the file.
- **Alternatives:** committing the empty folders with a `.gitkeep` was rejected: no code, but it breaks as soon as
  the folder is deleted. Making each writer create its folder was rejected: three places, two of them third-party.
  Shortening the file names to `<camera>.yaml` was rejected: they appear in node parameters and logs, where the folder
  is not visible. Letting the wizard keep its own path joins was rejected: a second copy of the folder names.

## 2026-10-12: `projection_corners` and `projection_mapping` merged into `projection_calibration_server`

- **What:** one package and node, `projection_calibration_server` / `projection_calibration_server_node`, replaces
  `projection_corners_node` and `projection_mapping_node`. It serves both calibrations under the unchanged names
  (`/projection_corners`, `/projection_mapping`, `/set_projection_corners`, `/set_projection_mapping`, parameters
  `projection_corners_file` / `projection_mapping_file`, the same files in `config/calibration/extrinsics/`). A
  `Calibration` namedtuple holds what differs between the two (log name, file, validate, save, message conversion,
  publisher); one `publish_stored` / `store` path handles both. `launch_helpers.projection_calibration_server_node`
  replaces the two start functions, and `par.launch.py`, `calibration.launch.py` and `projection_calibration.launch.py`
  start it. `load` now raises `ValueError` for an empty or non-YAML file, and the node logs and skips a stored file
  that is missing keys or holds wrong types instead of crashing at startup.
- **Why:** the two nodes were copies of one pattern (load a YAML, validate, publish latched, store through a set
  service), and `projection_mapping` read like the projection itself rather than the owner of a stored result. The
  `_server` suffix follows Nav2's `map_server`, which does the same for maps. Because the topic and service names stay,
  `surface_selector`, `projection_calibrator`, `rviz_bridge` and the wizard need no change. The load errors are
  isolated because after the merge one broken file would otherwise also stop the other calibration from being served.
- **Alternatives:** only renaming `projection_mapping_node` was rejected: it fixes the name but keeps the duplicate
  code. Also folding in the camera pose (as a static TF broadcaster) and the intrinsics was rejected: those use the
  standard ROS channels (`/tf_static`, `camera_info_manager`) that third-party tools read. Two separate code paths in
  one class were rejected as the same duplication in one file; a dataclass instead of the namedtuple would need type
  annotations for a record that never changes.

## 2026-10-12: `par_geometry` importable as `from par_geometry import ...`

- **What:** `par_geometry/__init__.py` re-exports the six functions of `par_geometry/par_geometry.py` and lists them
  in `__all__`. `rviz_bridge_node.py` imports `from par_geometry import ...` (now one line); `surface_selector` and
  `gesture_detector` were changed the same way in their repositories. The long form still works.
- **Why:** `par_geometry.par_geometry` read like a package with a node module, while it is a library of shared
  functions. The short path is the usual form for a library (`from image_geometry import PinholeCameraModel`), and
  the package name stays, following ROS's `image_geometry`, which is a library of camera model math too.
- **Alternatives:** renaming the package (e.g. `par_coordinates`) was rejected for now: three `package.xml`, the
  imports, docs and an image rebuild, for a name that already follows a ROS precedent. Silencing flake8's F401 with a
  `# noqa` per name instead of `__all__` was rejected: `__all__` states that the names are the public API.

## 2026-10-12: `gesture_detector` is part of the framework

- **What:** `config/nodes.list` lists `gesture_detector` (`ros2-par-framework-gestures`, branch `main`) under the
  sensor processing nodes.
- **Why:** the node consumes `hand_landmarks` and now also works without intrinsics and camera pose (in camera pixels),
  so it fits the framework's rule that calibration is optional.
- **Alternatives:** listing branch `rework`, where the code currently lives, was rejected: every other entry names
  `main`, and `sync_nodes.sh` never switches an existing checkout's branch. Until `rework` is merged, a fresh clone of
  `main` contains no package.

## 2026-10-12: `CLAUDE.md`: calibration is optional and lives in the calibration repo

- **What:** "What this repository is" sharpens the glue test to "no purpose existing without the framework" and names
  `par_geometry` and the setup wizard next to `rviz_bridge`. A new paragraph states that calibration is optional:
  everything that produces or serves the camera pose, projection corners and projection mapping belongs in
  `ros2-par-framework-calibration`, nodes that can work uncalibrated publish camera pixels and add table coordinates
  only when available, and intrinsics stay with the camera side here. `camera_pose_calibrator` and
  `projection_calibration_server` are named as not yet moved.
- **Why:** your decision. `camera_pose_calibrator` fails the glue test (it uses no framework messages), and no
  application consumes `/projection_mapping` yet, so moving the whole calibration out breaks nothing and makes "add the
  calibration repo" the one step to a calibrated setup.
- **Alternatives:** keeping `projection_calibration_server` in core as the runtime store, with the calibration repo
  only producing files: rejected, it splits one feature across two repos and needs an exception in the rule. Moving
  the intrinsics procedure too: rejected, intrinsics belong to the camera and use ROS's standard `camera_info`
  channel, which third-party tools read.

## 2026-10-12: `camera_pose_calibrator` and `projection_calibration_server` moved to the calibration repo

- **What:** both packages were removed from `packages/` and copied unchanged (from `HEAD`, via `git archive`) into
  `ros2-par-framework-calibration`. `par_framework_core/package.xml` no longer declares them, nor `surface_selector`.
  `par.launch.py` starts `projection_calibration_server` only when `has_resource('packages', ...)` finds it, and logs
  that it runs without a projection calibration otherwise. README tree and package table and `CLAUDE.md` updated.
- **Why:** the rule from the same day, calibration is optional and lives in its own repo. All three exec_depends had
  to go, `surface_selector` included: otherwise core could still not be installed without the calibration repo.
- **Alternatives:** an optional check inside `launch_helpers.projection_calibration_server_node`: rejected, the
  calibration launch files call it too, and there a missing server must fail loudly instead of being skipped. Moving
  the calibration launch files too: left for later, the task was the two packages; they now need the calibration repo
  at runtime, not at build time.

## 2026-10-12: `.gitignore`: ignore `.pytest_cache/`

- **What:** `.pytest_cache/` added next to the existing Python cache rules.
- **Why:** pytest writes this cache into the directory it runs from, and the packages here are meant to be testable
  with plain pytest, so it would otherwise show up as untracked. The node repos got the same rule (plus
  `__pycache__/` where it was missing) in their own `.gitignore` files.
- **Alternatives:** a broad Python template (as in `logitech_brio`): rejected, nearly all of its rules match nothing
  this repo produces and make the file harder to read. Setting `PYTHONDONTWRITEBYTECODE` / `-p no:cacheprovider`:
  rejected, the caches are useful and an environment setting is easy to miss on another machine.
