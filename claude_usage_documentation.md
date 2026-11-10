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

## 2026-10-12: `config/ros_packages.list` for released packages (RealSense, webcam)

- **What changed:** a second list next to `config/nodes.list`: `config/ros_packages.list` holds rosdep keys of
  released packages that are installed instead of cloned, active by default: `v4l2_camera` (generic webcam) and
  `realsense2_camera` (Intel RealSense, until now cloned from `realsenseai/realsense-ros`, which `nodes.list` no
  longer lists). `scripts/common.sh` turns the list into a generated `package.xml` (`par_ros_packages`, one
  `<exec_depend>` per key): `sync_nodes.sh` stages it into `docker/deps/`, so the image's existing rosdep call
  installs it, and `local_build.sh` adds it from a temporary directory to its rosdep call. `par_framework_core`
  no longer declares `v4l2_camera`.
- **Why:** your request. `nodes.list` only lists repositories to clone; released drivers that are used unchanged
  do not need a checkout, a C++ build and its extra build dependencies, nor the risk that an upstream branch does
  not build on the current distro. Declared in `par_framework_core`, they were mandatory for every setup; in the
  list, a setup comments out what it does not use. This reverses the 2026-10-08 decision to keep RealSense as a
  source checkout.
- **Alternatives:** apt package names instead of rosdep keys: rejected, they carry the distro
  (`ros-lyrical-...`), and rosdep keys also cover non-ROS packages and `--skip-keys`. A loop over
  `rosdep resolve` + `apt-get install` in both the Dockerfile and `local_build.sh`: rejected, two copies of new
  install logic instead of one generator feeding the existing rosdep path. Declaring the drivers in
  `par_framework_core/package.xml` (tried first): rejected, it makes every driver mandatory. Each key is checked
  against the form of a rosdep key, because it is written into XML. A package that needs patching goes into
  `nodes.list` again; a checkout in `src/` overrides the installed one.

## 2026-10-12: projection mask, part 1: repo entry and `par_geometry` helpers

- **What changed:** `config/nodes.list` lists the new repo `ros2-par-framework-projection-mask` (checkout
  `src/projection_mask`). `par_geometry` gained four functions: `pixel_rays` (undistorted ray of every stride-th
  camera pixel), `depth_to_table` (depth image to table-frame points), `project_to_table` (central projection
  from the projector's optical centre onto z = 0) and `intersect_rays` (least-squares point closest to a set of
  rays, for finding that centre).
- **Why:** the projection mask keeps projected light off hands and objects. It needs depth points above the
  table mapped to projector pixels. The table-to-projector homography only covers z = 0; a point above the table
  is lit by the pixel whose ray from the projector centre runs through it, so the point is first projected from
  that centre onto the table and then through the homography. The math lives in `par_geometry`, the one place
  for coordinate conversions, so the mask node and the calibrator share it.
- **Alternatives:** the mask in this repo as a core package: rejected, it is an optional capability (it needs a
  depth camera, a calibration and an app that applies it), so it gets its own repo like the calibration. Ignoring
  the projector centre and projecting straight down with a wider margin: rejected as the main path, the offset
  grows with height and projector tilt; it remains the fallback until the centre is calibrated. Splitting the
  helpers into the mask package: rejected, the calibrator needs `intersect_rays` too.

## 2026-10-12: projection mask, part 2: launch, parameters and the package rule

- **What changed:** `par.launch.py` has a `projection_mask` switch (`par_launch` and `projection_mask:=true`); the
  node starts only when `has_resource('packages', 'projection_mask')`, otherwise the launch logs which repo to add.
  `projection_calibration.launch.py` has `projector_center:=true`: it gives `fiducials_detector` `use_depth` and the
  calibrator its board mode, and refuses cameras without depth. `par_setup.yaml` has a `projection_mask_node`
  section, `max_center_ray_distance_m` for the calibrator and `projection_mask: false`; the wizard shows the switch.
  `CLAUDE.md` replaces the "framework glue" definition with three ordered questions (useful outside the framework →
  own repo; shared library or setup/inspection tooling → this repo; otherwise a framework capability → own repo,
  started only when installed), documents the projector centre and the two projector masks (`/projector/mask`,
  and `/projector/content_mask` as a convention for apps).
- **Why:** the old definition put everything framework-specific here, which contradicted the calibration living in
  its own repo, and would have put the mask here too. The ordered questions decide both the same way and keep
  `rviz_bridge` (optional, but tooling) here. The `has_resource` check follows the calibration server's pattern, so a
  setup without the mask repo still starts. The content mask is only a convention: nothing publishes or reads it yet,
  and the app knows exactly where it draws.
- **Alternatives:** adding the mask to `DETECTORS`: rejected, it would get the camera overrides and no install
  check. A table "framework-specific × essential" for the rule: rejected, `rviz_bridge` fits no cell without an
  exception. Reading the projector display to get the content mask: rejected, the desktop runs Wayland, where
  reading the screen needs the screen-cast portal with user consent, does not work from the container, and adds
  delay. Checking the detector switches for installed packages too: left as it is (outside this task).

## 2026-10-13: RViz camera frustum reaches through the table

**What changed:** `Far clip` of the CameraInfo display in `par_framework_brio.rviz`, `par_framework_webcam.rviz`
and `par_framework_kinect.rviz` is now 2 m instead of the placeholder camera height (1 m / 0.97 m).

**Why:** The CameraInfo display draws the frustum up to a plane perpendicular to the optical axis at `Far clip`.
That value only touches the table when the camera looks straight down from exactly the placeholder height. A
calibrated pose (`camera_pose_<camera>.yaml`) is tilted and at a different height, so part of the frustum ended
above the table and you couldn't see where the camera's view meets the table.

**Decisions:**
- *A fixed length longer than any expected camera height* instead of computing it from the pose: the RViz
  display has no option to clip at a plane, and writing the `.rviz` file at launch from the pose would add code
  for a purely visual cue. The frustum now crosses the table, and its intersection with the grid shows the
  camera's footprint.

## 2026-10-13: RViz camera frustum drawn as opaque edges only

**What changed:** The CameraInfo display in the three `.rviz` files sets `Show polygons: false` and `Alpha: 1`; the
edges keep RViz's default grey. The lines still disappear when the frustum is viewed from behind; the cause is
inside RViz's line rendering and not yet found, and no CameraInfo property controls it.

**Why:** By default the display draws grey edges at `Alpha` 0.5 plus a semi-transparent far rectangle that writes
no depth. Ogre sorts transparent objects by distance instead of depth-testing them against each other, so from
some viewing angles the rectangle and the grid were drawn over the lines, which then disappeared. With the
frustum now longer than the camera height, the far rectangle lies below the table and shows nothing useful.

**Decisions:**
- *Only changing the edge colour* was rejected: `Alpha` applies to edges and polygons alike, so the lines would
  stay half-transparent and still be sorted wrongly.

## 2026-10-13: `gesture_detector` started by `par.launch.py`

- **What changed:** `gesture_detector` is a detector switch like the others: in `DETECTORS` of `par.launch.py` (so it
  also gets the launch argument `gesture_detector:=true|false`), in the `par_launch` section of `par_setup.yaml`
  (default `true`, "Needs hand_landmarks") and as a checkbox label in the setup wizard's `NODES`.
- **Why:** your request. Until now it had to be started by hand with `ros2 run`, while every other detector came up
  with the framework.
- **Alternatives:** no camera override, unlike `hand_landmarks`: the node reads only `/hand_landmarks` and
  `/camera/camera_info`, no frames, the same as `page_locator` with `/fiducials`. Starting it automatically
  whenever `hand_landmarks` runs: rejected, a switch of its own keeps the one-switch-per-node rule and lets a setup
  run hand tracking without gestures. Declaring it as `<exec_depend>` of `par_framework_core`: left out, like
  `page_locator`, which is not declared there either.

## 2026-10-13: `projection_mask_node` stride 4 by default

- **What changed:** `stride` under `projection_mask_node` in `par_setup.yaml` is 4 (was 2), with a note why.
- **Why:** part of making the mask fast enough for a 4K projector (the other part is in the mask repo: drawing at a
  quarter of the resolution). The Kinect's registered depth is interpolated up from a coarser sensor, so every
  fourth pixel still samples it finely enough.
- **Alternatives:** keeping 2 and only drawing coarser: measured too slow on its own.

## 2026-10-13: Kinect at 30 fps with `WFOV_2X2BINNED`

- **What changed:** `k4a_ros_device_node` in `par_setup.yaml` runs at `fps: 30` with `depth_mode: WFOV_2X2BINNED`
  (was 15 fps, `WFOV_UNBINNED`); the comment lists the three depth modes with their field of view and frame rate.
- **Why:** a faster camera shortens the delay of the projection mask, the part of it the mask node cannot shorten.
  `WFOV_UNBINNED` only runs up to 15 fps. The narrow `NFOV_UNBINNED` measures finest at 30 fps, but checked
  against this setup's camera pose and projection mapping, the corners of the projection area lie at or beyond the
  edge of its field of view, so hands there would get no depth. The binned wide mode covers the whole area; its
  depth is coarser but less noisy, which suits a mask that is grown by a margin anyway.
- **Alternatives:** `NFOV_UNBINNED`: rejected for the coverage above; it is the better choice where the projection
  area lies well inside its view. Staying at 15 fps: rejected, the mask's delay is dominated by the camera.

## 2026-10-13: `projection_mask_node` stride 6

- **What changed:** `stride` under `projection_mask_node` in `par_setup.yaml` is 6 (was 4), with the reason in the
  comment.
- **Why:** at 30 fps the mask has to be ready in about 33 ms. With `WFOV_2X2BINNED` one depth pixel covers about five
  colour pixels, so every sixth colour pixel still samples about every depth pixel.
- **Alternatives:** 4: measured too slow for 30 masks per second together with the rest of the node.

## 2026-10-13: projection mask debug preview: config and wizard

- **What changed:** `projection_mask_node` in `par_setup.yaml` has `debug: false` and `display_id` (the projector's,
  as for the calibration nodes). The setup wizard lists `projection_mask_node` in `DISPLAY_NODES`, so choosing the
  projector also sets the preview's display.
- **Why:** the mask node can show its mask on the projector for testing (the node itself is in the mask repo). The
  wizard already writes the projector display into every node that opens a window there; one more entry keeps the
  preview on the same display without a second place to set it.
- **Alternatives:** a launch argument for `debug`: rejected for now, the node's parameters come from the params file
  like every other node's, and a switch per node parameter would grow `par.launch.py` for a testing aid.

## 2026-10-13: `rviz_bridge` shows the projector's optical centre and light cone

- **What changed:** `publish_projector_outline` also publishes, on `/projection_mapping/markers`, a sphere at the
  mapping's `projector_center` (namespace `projector_center`) and a `LINE_LIST` from it to the four corners of the
  projector image on the table (`projector_cone`), in the outline's colour. Without a valid centre both are sent as
  `DELETE`, so a centre from an earlier mapping disappears.
- **Why:** the projector-centre calibration had no visual check. Seeing the projector above the table with its light
  cone in RViz makes a wrong calibration obvious and shows where the projection mask expects the light to come from.
  It reuses the outline's corners and topic, so the RViz configs need no change (their marker displays show every
  namespace).
- **Alternatives:** a `projector` TF frame: it would also need the projector's orientation, which the centre alone
  does not give. A separate topic and RViz display: rejected, the centre belongs to the same mapping as the outline
  and goes stale with it. `LINE_STRIP` for the cone: rejected, it would join the corners to each other instead of
  drawing four separate edges from the centre.

## 2026-10-14: `demo_app` as an optional application in `nodes.list` and `par.launch.py`

- **What changed:** `config/nodes.list` lists `demo_app` (`ros2-par-framework-demo-application`) under
  Applications. `par.launch.py` has a `demo_app` switch (launch argument and `par_launch.demo_app`, default `false`
  in `par_setup.yaml`) that starts `demo_app_node` when the package is installed, and otherwise logs which repo to
  add.
- **Why:** the demo application subscribes to `/pages`, `/objects` and `/gestures` as the starting point for an app
  on the framework. Like every node outside this repo, it reaches a setup through its line in `nodes.list`, and the
  launch file must not fail on a setup that leaves it out.
- **Alternatives:** starting it unconditionally whenever it is installed: rejected, a setup that has the repo for
  development would always run it. A separate launch file for apps: rejected, `par.launch.py` is the one entry point
  and already handles optional nodes the same way (`projection_mask`). Adding it to the setup wizard's node list was
  left out for now: the wizard keeps an existing `par_launch.demo_app`, it just cannot change it.

## 2026-10-16: Intel RealSense (D435) as `camera:=realsense`

- **What changed:** `launch_helpers.py` starts `realsense2_camera_node` as `/camera/realsense` (`realsense_driver_node`,
  with `camera_name: realsense` for its TF frames), adds a `realsense` branch to `camera_nodes` with the mount
  transform `world -> realsense_link`, and a `DRIVER_REMAPPINGS['realsense']` entry that maps the colour image, its
  `camera_info` and `aligned_depth_to_color` onto the neutral `/camera/...` topics. `par_setup.yaml` holds the driver
  parameters (colour and depth enabled and both infrared streams disabled explicitly, because the node started
  without `rs_launch.py` streams the infrared images too; colour `1280x720x30` in `BGR8`; `align_depth.enable`) and a
  `/realsense_tf_publisher` placeholder. `par.launch.py` gives it the Kinect's detector overrides (shared as
  `DEPTH_CAMERA_OVERRIDES`) and a new `par_framework_realsense.rviz`; `projection_calibration.launch.py` lists it in
  `DEPTH_CAMERAS`, so the projector-centre run works with it. The `camera:=` descriptions name it.
- **Why:** a second depth camera next to the Kinect, without the Kinect's host-only SDK. The released driver is
  already installed through `config/ros_packages.list`, so the framework only needed the start and the remapping.
  Aligned depth is the driver's depth on the colour pixel grid, which is what `/camera/depth_registered/image_raw`
  means, and its `16UC1` millimetres are what the depth consumers already read (REP 118). `BGR8` keeps
  `/camera/image_raw` the same as the Brio's for consumers that convert with passthrough (`surface_selector`).
  `camera_name` is set in the launch code because the remapping table and the mount transform depend on it.
- **Alternatives:** including the driver's `rs_launch.py`: rejected, it takes its settings as launch arguments
  instead of from `params_file`, and the remappings would have to be passed through it. Leaving the colour format at
  the driver's `RGB8`: rejected, red and blue would swap in consumers that do not convert. Reusing the Kinect's RViz
  config: rejected, its display names and point cloud topic are the Kinect's. Adding the camera to the setup wizard
  was left for a separate step: the wizard handles cameras in several places (settings, pose calibration).

## 2026-10-22: Docker setup moved out of `rework` onto `feature/docker`

**What changed:** `rework` no longer contains the Docker setup:
- Deleted:
  - `docker/` and `docker-compose.yaml`
  - `.env.example`
  - `setup.sh` and `scripts/preflight.sh`
  - `scripts/shell.sh`, `scripts/build_workspace.sh` and `scripts/launch.sh`
- `scripts/common.sh` lost its container helpers (`compose`, `docker_exec`, `in_container`, …). In return it
  sets `ROS_DISTRO` (default `lyrical`, an already set value wins), which `local_build.sh` and `wizard.sh`
  used to read from `.env`.
- `scripts/sync_nodes.sh` only clones now. The staging of the manifests into `docker/deps/` and the
  `--clone-only` flag that skipped it are gone.
- The launch hints, `.gitignore`, README and CLAUDE.md describe the host build (`local_build.sh`, the
  wizard, `ros2 launch`) as the only workflow.

The rule that nothing in `par_framework_core` may declare the Kinect driver moved from "Container
constraints" in CLAUDE.md to its architecture section, because it also holds without Docker.

**Why:** The Docker parts are out of date and not being worked on right now. They will be brought back up to
date once the other features are done. Until then, a second, untested path in the scripts and the docs is
misleading.

**Decisions:**
- *Removal commit on `rework`, then `feature/docker` branched from it, with a revert of that commit.* The
  alternative was to branch `feature/docker` before the removal. Git would then treat the deletion as the only
  change since the common ancestor, and a later merge would not bring the files back. With the revert,
  `feature/docker` is `rework` plus one "add Docker" commit, and it merges back like any feature branch.
- *Delete `setup.sh` and `preflight.sh` instead of keeping a host-only preflight.* `local_build.sh` is
  already the host bootstrap. The git, SSH and DISPLAY checks come back with `feature/docker`.
- *`ROS_DISTRO` as a default in `common.sh` instead of a trimmed `.env.example`.* A single variable did not
  justify a separate file plus the same lookup in two scripts, and it can still be overridden from the shell.
- *Delete `launch.sh` instead of turning it into a host script.* On the host, `ros2 launch
  par_framework_core <name>.launch.py` and the wizard already cover it.

## 2026-10-22: Setup wizard moved out of `rework` onto `feature/setup-wizard`

**What changed:** `rework` no longer contains the setup wizard:
- Deleted: `packages/par_setup_wizard/` and `scripts/wizard.sh`.
- README.md and CLAUDE.md describe the start with `ros2 launch` and the `par_launch` section instead of the
  wizard. The wizard section, its Layout line and its packages table row are gone.
- The comments in `par_setup.yaml`, the launch files, `launch_helpers.py` and `run_cameracalibrator.sh` no
  longer name the wizard. "Profile" became "parameter file", because `params_file:=` takes any file.
- `.gitignore` no longer ignores `config/profiles/`. That folder was the wizard's convention for named
  profiles.
- The Brio and webcam pose comment in `par_setup.yaml` now shows how to write
  `calibration/extrinsics/camera_pose_<camera>.yaml` by hand: the seven flat keys, with the rotation for a
  height and tilt (`rotation.y = sin(a)`, `rotation.w = cos(a)`, `a = (90 - tilt) / 2`).

**Why:** The wizard is out of date and will be brought back up to date later, like the Docker setup. Until
then, the docs should not point to a tool that no longer matches the rest of the framework.

**Decisions:**
- *The same git pattern as for Docker:* a removal commit, then a branch with its revert. This way
  `feature/setup-wizard` merges back like any feature branch.
- *Hand-written pose file instead of a small helper script.* Only the wizard turned height and tilt into a
  quaternion for the Brio and the webcam. A replacement script would be new code for a stopgap. The formula
  in the comment keeps the same result possible, and the placeholder (straight down) stays the fallback. The
  Kinect keeps `camera_pose_calibration_kinect.launch.py`.
- *Keep `params_file:=` and drop `config/profiles/`.* The launch files support any parameter file without the
  wizard; only the folder and its name belonged to the wizard.

## 2026-10-22: Scripts in `scripts/` rewritten for readability

**What changed:** All four scripts behave as before, except for the two cases at the end. The changes:
- One statement per line, `if` instead of `cond && action`, and named variables instead of `$1`.
- Comments at each bash idiom: `set -euo pipefail`, `BASH_SOURCE`, `IFS=$'\t' read`, `< <(...)`, `@{upstream}`, `nullglob`, `trap ... EXIT`.
- `common.sh`:
  - The colours are written straight into the message strings.
  - `have` is now `command_exists`.
  - `NO_BRANCH` names the `-` placeholder.
  - The two list parsers are bash loops instead of awk programs.
  - The `package.xml` is a heredoc instead of ten `echo` lines.
- `sync_nodes.sh`: the loop calls `clone_repo`, `update_repo` and `has_commits` instead of nesting everything.
- `local_build.sh`: the header lists the four steps, and the code is marked with them.
- `run_cameracalibrator.sh`:
  - It uses `common.sh` (`die`, `command_exists`, `ROS_DISTRO` in the hint).
  - Its Python workarounds are a commented block instead of a one-line string.
  - The board path in the header is corrected to `utils/checkerboard.png`.

**Behaviour changes:**
- *A failed `git fetch` (e.g. offline)* used to stop the whole sync through `set -e`. Now that repository is skipped with a warning, like the other cases where a checkout is left untouched. The explicit check was necessary anyway: `set -e` does not apply inside a function that is called as a condition (`update_repo || continue`), so the error would otherwise have gone unnoticed and been reported as a failed fast-forward.
- *An existing but empty checkout* is now reported as "repository is empty" and counted as a failure. Before, `rev-parse --abbrev-ref HEAD` stopped the script with a git error. That is why `has_commits` runs before `update_repo`.

**Decisions:**
- *Bash loops instead of awk,* so the reader needs only one language. The new parsers were checked against the awk versions with the real lists and with test lists: comments, indentation, a missing branch, extra words, a last line without a line break, invalid lines. Output and exit codes matched; only the order of stdout and stderr differs, because awk buffers its output.
- *For the calibrator, the Python code goes into a variable with a heredoc and runs with `python3 -c "$code"`, not `python3 - <<EOF`.* With `-`, the program would be read from stdin and `sys.argv[0]` would change, and the calibrator can only be tested with a camera. `read -d ''` was rejected because it returns 1 at the end of the text and would trigger `set -e`.
- *Kept:* the `-` placeholder for a missing branch, because `read` with a tab as separator merges empty fields, and the output format of the helpers.

## 2026-10-22: `utils/generate_checkerboard.py` made more readable

**What changed:** The readability and unit-in-the-name rules applied to a manual revision that was already in progress (`SQUARE` → `SQUARE_SIZE_PX`, check and output removed):
- `MARGIN` is now `MARGIN_PX`, and `COLS` and `ROWS` are on separate lines.
- The black-and-white pattern is built in named steps (`row_index + col_index` odd → `WHITE`) instead of one chained expression.
- `np.kron` and the border call are commented and use keyword arguments.
- The detection check is back as an explicit `if not found: raise RuntimeError(...)`. It runs before the file is written.

**Why:** After the manual revision, the `findChessboardCorners` result went unused while the docstring still promised the check. A board that OpenCV does not detect is useless to cameracalibrator, so it is better to fail before writing it.

**Decisions:**
- *Check restored instead of removing the dead line,* as decided in the conversation.
- *`np.kron` kept* instead of two nested `np.repeat` calls: it is shorter, and with the comment just as clear.
- *Checked:* a copy of the script, run outside `utils/`, produces a board that is pixel-identical to the tracked `checkerboard.png`.

## 2026-10-22: `custom_interfaces` renamed to `par_framework_interfaces`

**What changed:** The interfaces package (repo `ros2-par-framework-interfaces`) is now called `par_framework_interfaces`, in all repos at once:
- interfaces repo: `<name>` in `package.xml`, `project()` in `CMakeLists.txt`, README.
- every consumer: `<depend>`/`<exec_depend>` in `package.xml` and every `from ... .msg/.srv import` (`rviz_bridge` here; `demo_app`, `fiducials_detector`, `gesture_detector`, `hand_landmarks`, `object_detector`, `page_locator`, `projection_mask`, `surface_selector`, `projection_calibration_server`).
- here: the checkout directory in `config/nodes.list` (and `src/` renamed to match), README, CLAUDE.md.
- Where the new name sorts differently (`c` → `p`), the import moved to its alphabetical place, so flake8's import-order check stays as it was.

**Why:** The old name described where the package came from, not what it holds, and the cost of renaming grows with every node that imports it. The VIGITIA compatibility that justified it only saved editing imports when porting a node; the READMEs now say to change `custom_interfaces` to the new name when porting.

**Decisions:**
- *One rename across all repos* instead of a compatibility package under the old name: nothing outside these repos depends on it, and a second package would have to be kept in sync.
- *Repo name unchanged:* `ros2-par-framework-interfaces` already matches the new package name.
- *Older log entries keep the old name,* because they describe what was true at the time.
- *Checked:* full build, every changed node module imports with the old build output deleted, and the lint suites of the changed packages show no new errors.

## 2026-10-22: `num_hands` for `hand_landmarks_node` in `par_setup.yaml`

**What changed:** `par_setup.yaml` has a `hand_landmarks_node` block with `num_hands: 2`, the maximum number of hands the node detects per frame (a new parameter of the node, see its repo's log).

**Why:** how many hands are expected depends on the setup (one user, or several people at one table), and `par_setup.yaml` is where a setup's values are visible and edited. `par.launch.py` already passes the file to every framework node, so no launch file changes.

**Decisions:**
- *Listed with its default value,* like the `page_locator_node` values, instead of left to the node's code default: a setup can see that the knob exists without reading the node.
- *Bare key `hand_landmarks_node`:* the node runs without a namespace (`framework_node` in `par.launch.py`).

## 2026-10-22: camera frame topic chosen by remapping, compressed frames by `use_compressed`

**What changed:** `par.launch.py` no longer sets `topic_name_frame`: the frame consumers (`hand_landmarks`, `fiducials_detector`, `object_detector`) subscribe to the constant `/camera/image_raw` and lost the parameter. `object_detector` has a new bool parameter `use_compressed` (default false) that subscribes to `/camera/image_raw/compressed` as `CompressedImage`; `CAMERA_OVERRIDES` sets it for the Brio, whose driver passes the camera's JPEGs through. The depth cameras' and the webcam's overrides that switched `object_detector` back to raw are gone, and with them the `DEFAULT_TOPIC_NAME_CAMERA_IMAGE` import.

**Why:** remapping is ROS 2's own way to point a node at another topic and works for every topic; the frame topic was the only input chosen by parameter, set by nothing but the switch between raw and compressed. Raw is the one colour topic every camera provides, so it is the default in every node; the compressed variant only exists where a driver publishes it, which the launch file knows per camera.

**Alternatives:**
- *Compressed as the default for all nodes:* rejected, only the Brio publishes JPEGs; every other camera would need an override per node.
- *Dropping compressed support in `object_detector`:* rejected, with the Brio the driver then decodes every frame for it.
- *Keeping `topic_name_frame` and inferring the type from a `/compressed` suffix:* rejected, a topic-name parameter duplicates remapping, and a name pointing at the wrong type subscribes silently and receives nothing.
- *image_transport's transport selection:* not used, it needs Python bindings that would be a new dependency.

**Open:** `surface_selector` (calibration repo) still has `topic_name_frame`, and `par_setup.yaml` still sets it.

## 2026-10-22: `surface_selector` without `topic_name_frame`; CLAUDE.md on topic names

**What changed:** `par_setup.yaml` no longer sets `topic_name_frame` for `surface_selector_node`, whose parameter is gone (calibration repo), and the comment in `calibration.launch.py` says which topic the node subscribes to. CLAUDE.md's section on the neutral camera interface names `object_detector`'s `use_compressed` as the one consumer of the compressed frames, and states the convention: nodes take the `/camera/...` names as constants, another topic is chosen by remapping.

**Why:** completes the previous entry for the last node with the parameter, and records the convention where the next change to a node will look for it.

**Alternatives:** leaving the convention to the code alone: rejected, a new node would likely copy the old parameter from an older node.

## 2026-10-23: reorder `launch_helpers.py`

**What changed:** `packages/par-framework-core/par_framework_core/launch_helpers.py` is reordered, no line of code changed: imports, then all constants (`CAMERA_*`, `DRIVER_REMAPPINGS` with its helper `_namespaced`, `INTRINSICS`/`EXTRINSICS`), then the generic helpers (`config_file`, `read_launch_section`, `chosen_camera`), then the camera start functions with the dispatcher `camera_nodes` above the drivers it calls, then `mount_tf_publisher` and `projection_calibration_server_node`.

**Why:** the constants were spread through the bottom half of the file, after the functions that use them, so a reader met `DRIVER_REMAPPINGS` and `EXTRINSICS` before learning what they hold. Top-down order (definitions, then general helpers, then the specific start functions) lets the file be read once from the top.

**Alternatives:**
- *Splitting the file (constants module, camera module):* rejected, one file of this size is easier to find things in than three, and nothing outside imports the parts separately.
- *Also unifying return types (`kinect_driver_node` returns a `Node`, the other drivers a list):* left out, it changes the interface for `camera_pose_calibration_kinect.launch.py` and is not part of a reorder.

## 2026-10-23: `launch_helpers.py` checks camera poses; camera list in errors from `DRIVER_REMAPPINGS`

**What changed:** `mount_tf_publisher` checks the loaded camera pose with the new `invalid_pose_keys`: all of `CAMERA_POSE_KEYS` (`translation.xyz`, `rotation.xyzw`) must be finite numbers. Otherwise it raises an error that names the file, the bad keys and the fix (re-run the pose calibration or delete the measured file; for the placeholder, the section to set in the params file). A params file without the `/<name>_tf_publisher` section gets the same error. The error texts of `chosen_camera` and `camera_nodes` take their camera list from `CAMERA_NAMES`, built from `DRIVER_REMAPPINGS`; the final `raise` of `camera_nodes` now says what it actually catches, a camera in `DRIVER_REMAPPINGS` without a start function, since `chosen_camera` already rejects unknown cameras. The file header now says co-authored, as the file has hand edits.

**Why:** the pose files are read in every launch with that camera and may be hand-edited or cut short. Before, an empty file or a missing key ended as a `TypeError`/`KeyError` traceback that named neither the file nor the fix. Finite numbers rather than a key check, because YAML `.nan` would pass a key check and reach `static_transform_publisher`; `bool` is excluded because Python counts it as `int`. The camera list was spelled out in each error text and went stale when a camera was added.

**Alternatives:**
- *Checking only that the keys exist:* rejected, `nan` or a string would still reach the transform.
- *Replacing the `if` chain in `camera_nodes` by a lookup table:* rejected, with four cameras the chain is easier to read.
- *Building the `camera` argument descriptions of the launch files from `DRIVER_REMAPPINGS` too:* left out, their docstrings list the cameras in prose anyway, so a new camera touches them regardless.

## 2026-10-23: `DRIVER_REMAPPINGS` written out, without `_namespaced`

**What changed:** the Brio and webcam entries of `DRIVER_REMAPPINGS` in `launch_helpers.py` list their `(driver topic, framework topic)` pairs explicitly instead of generating them with `_namespaced`, which is removed. All four entries use one pair per line; the framework names use the existing constants where there is one (`DEFAULT_TOPIC_NAME_CAMERA_IMAGE`, `…_INFO`, `…_DEPTH`, `CAMERA_SET_INFO`). The resulting table is unchanged.

**Why:** the generated pairs hid what is remapped onto what; written out, each line shows both names, can be found by grepping for either topic, and an entry whose driver name differs from the pattern needs no special case.

**Alternatives:** keeping the helper for the two namespaced drivers: rejected on request, and the table is short enough that writing it out costs only a few lines.

## 2026-10-23: `DRIVER_REMAPPINGS` renamed to `CAMERA_DRIVER_REMAPPINGS`

**What changed:** the remapping table in `launch_helpers.py` and every current reference to it (`par.launch.py`, `scripts/run_cameracalibrator.sh`, `CLAUDE.md`) use the name `CAMERA_DRIVER_REMAPPINGS`. Earlier entries in this file keep the old name, as they describe the code at their time.

**Why:** "driver" alone is ambiguous (any device driver, or a person); the table maps camera drivers' names onto the framework's camera interface, and its keys are camera names. The qualified name stays clear where the name appears without its file around it: in a grep, a traceback, CLAUDE.md.

**Alternatives:** `TOPIC_REMAPPINGS`: rejected, the table also remaps a service (`set_camera_info`), and it does not say whose names are remapped.

## 2026-10-23: `INTRINSICS`/`EXTRINSICS` renamed to `FOLDER_PATH_CAMERA_INTRINSICS`/`FOLDER_PATH_EXTRINSICS`

**What changed:** the two folder constants in `launch_helpers.py` and their uses there and in `camera_pose_calibration_kinect.launch.py`. Lines that grew past the length limit are split into named steps (`camera_info_path`, then `camera_info_url`; `camera` from the publisher name; `camera_pose_file` in the launch file) instead of being broken mid-expression.

**Why:** bare `INTRINSICS` reads as the intrinsics themselves (camera matrix, distortion), not as a folder path. The `FOLDER_PATH_` prefix follows the codebase's kind-first naming (`TOPIC_NAME_…`, `SERVICE_NAME_…`). `CAMERA_` qualifies the intrinsics because a projector-camera setup has projector intrinsics too, and the folder holds only camera calibrations; the extrinsics folder holds camera poses as well as projection corners and mapping, so it stays unqualified. That the paths are relative to `config/` is stated once, in `config_file`, the only place that resolves them.

**Alternatives:**
- *Suffix style (`INTRINSICS_DIR`):* equally clear, rejected only for consistency with the kind-first names next to it.
- *`RELATIVE_FOLDER_PATH_…`:* rejected, longer without adding clarity where the constants are used.

## 2026-10-23: `config_file(file_name)` renamed to `get_path_in_config_folder(relative_path)`

**What changed:** the function in `launch_helpers.py` and its calls there and in `camera_pose_calibration_kinect.launch.py`. Each call first puts the relative path in a named variable, then passes it.

**Why:** `config_file()` did not say whether it returns a file's contents, its path or an open file, and every caller passes a path relative to `config/`, not a file name. `get_` states that the function returns a value, matching `get_package_share_directory`, which it wraps; "in" says the path points into the folder.

**Alternatives:**
- *`get_config_folder_path()`:* rejected, it reads as the path of the config folder itself.
- *`calibration_file_path()`:* rejected, true of every call today but narrower than what the function does (any path below `config/`).

## 2026-10-23: naming and readability rules applied to all Python files in `packages/`

**What changed:** names and expressions in `launch_helpers.py`, the four launch files, `par_geometry.py` and `rviz_bridge_node.py`; behaviour is unchanged.
- Functions start with a verb that says what they do: the launch helpers that build launch actions are `create_*` (`create_camera_nodes`, `create_logitech_brio_node`, `create_kinect_driver_node`, `create_realsense_driver_node`, `create_webcam_nodes`, `create_mount_tf_publisher`, `create_projection_calibration_server_node`, `create_camera_and_surface_selector`, `create_framework_node`), those returning a value `get_*` (`get_chosen_camera`, `get_invalid_pose_keys`, `rviz_bridge`'s `__get_camera_parameters`), a boolean `is_enabled`. `read_launch_section` and the `X_to_Y` conversions keep their names, as their verb is already more specific.
- Constants and variables say what they hold and, where they have one, their unit: `rviz_bridge`'s sizes and heights end in `_M` (`PROJECTOR_HEIGHT` became `PROJECTOR_OUTLINE_HEIGHT_M`, as it is the outline's height, not the projector's), `par_geometry` takes `camera_matrix`, `distortion_coefficients`, `homography`, `translation_m`, `width_px` instead of `k`, `d`, `h`, `translation`, `width`; single letters and generic names (`obj`, `lm`, `q`, `t`, `e`, `s`, `a`, `source`, `fix`, `section`, `value`, `what`) are replaced. `CAMERA_SET_INFO` is `DEFAULT_SERVICE_NAME_CAMERA_SET_INFO`, matching `DEFAULT_TOPIC_NAME_*`.
- Hard-to-read expressions are split into named steps: nested comprehensions (hand bones, light cone) and `a or b` fallbacks became loops and explicit `if`s, multi-step formulas got intermediate variables.

**Why:** the naming and readability rules for this repository: names must be unambiguous on their own (they are read in greps, tracebacks and docs), functions say what they do or return, and units belong in the name.

**How it was checked:** the previous versions were kept aside and compared with the new ones by result, not by reading: every `par_geometry` function returns bit-identical arrays for the same random inputs (including empty input, parallel rays, missing depth); every launch file generates identical actions with identical fields for all cameras, switches and calibration modes, and raises identical errors; `rviz_bridge` publishes identical markers for messages covering every branch. flake8 is clean apart from one existing long comment, and the `par_geometry` and `rviz_bridge` test suites pass.

**Alternatives:**
- *Renaming `par_geometry`'s public functions too (`rotation_matrix`, `pixel_rays`, ...):* left out, three other repositories import them; their parameters could be renamed safely because every caller passes them positionally.
- *`get_` for the launch start functions:* rejected, they build new launch actions rather than return existing ones, so `create_` is the more specific verb.
- *Keeping `launch_setup` as is:* yes, it is the conventional name of the function an `OpaqueFunction` runs in ROS 2 launch files.

## 2026-10-23: `par_geometry`: `rotation_matrix` → `quaternion_to_rotation_matrix`, `pixel_rays` → `compute_pixel_rays`

**What changed:** the two functions in `par_geometry` and every caller: `rviz_bridge` here, and `gesture_detector`, `projection_mask` and `surface_selector` (calibration repo) in their own repositories. `__init__.py` lists the names in alphabetical order again.

**Why:** the naming rule that a function name says what it does or returns. `rotation_matrix()` read like a value, not a conversion; `quaternion_to_rotation_matrix` follows the `X_to_Y` pattern of the other conversions in the module. `pixel_rays` computes the rays (slowly, once per camera_info), so `compute_` is the specific verb.

**Alternatives:**
- *`get_rotation_matrix`:* rejected, the function converts its input rather than returning stored state, and the module's other conversions are named `X_to_Y`.
- *Keeping the old names as aliases for a transition:* rejected, all callers are in repositories of this framework and are changed in the same step; an alias would keep the unclear name alive.

## 2026-10-23: private methods with one underscore instead of two

**What changed:** `rviz_bridge`'s `__get_camera_parameters` is `_get_camera_parameters`; the same rename was made for every `__method` in the framework's node repositories (`fiducials_detector`, `framework-calibration`, `gesture_detector`, `hand_landmarks`, `object_detector`), each logged there. `logitech_brio` still has its `__methods`: its checkout is on `main`, where changes wait for a branch.

**Why:** one leading underscore is Python's convention for "private"; two trigger name mangling (`_ClassName__method`), which only helps when a subclass could clash with the name. None of these classes is subclassed, and nothing accessed the mangled names. Before renaming, each new name was checked against the names already in its file and against the members of `rclpy.node.Node`, because with one underscore a name collision with a base class would silently override it; there was none.

**Alternatives:** keeping two underscores: rejected, the mangling protected nothing here and made the private methods harder to reach in a debugger or a test.

## 2026-10-23: README section "Camera interface"

**What changed:** the README ends with the conventions of the neutral camera interface: the `/camera/...` names with type, content and which cameras provide them; names as constants with remapping to choose; QoS; optional streams switched per camera in `par.launch.py`; detections in raw image pixels; where intrinsics and the camera pose come from; and the steps to add a camera.

**Why:** these conventions were spread over the project's CLAUDE.md, code comments and `launch_helpers.py`; someone adding a camera or a node needs them in one place, in the document they read first.

**Alternatives:** a separate document under `docs/`: rejected, the README already holds the other design conventions, and one more file is one more place to keep in sync.

## 2026-10-23: README section "Coordinate systems"

**What changed:** after "Camera interface", the README describes the four coordinate systems (camera pixels, camera optical frame, table frame `world`, projector pixels) with unit, origin, axes and what uses each; the rule that `world` is the table (z = 0 the tabletop, z up, origin below the camera); that messages stay in the frame they were measured in, with table coordinates only added next to pixels with a validity flag; that conversions happen locally with `par_geometry`; and why the shared table plane makes projection accuracy independent of an exact camera pose, with the parallax limit above the table.

**Why:** the frame conventions were only in the project's CLAUDE.md, message comments and node constants; a node author needs to know which frame a value is in and where to convert it.

**Alternatives:** listing the frames per message in the package table: rejected, the conventions are shared, so one section states them once.

## 2026-10-27: fiducials_detector takes the Brio's JPEGs

**What changed:** `par.launch.py` sets `use_compressed` for `fiducials_detector` with the Brio, as it already did for
`object_detector`; README and CLAUDE.md name both nodes.

**Why:** the Brio node decodes and publishes raw frames only while something subscribes to them. With the detector on
the compressed topic, a page-tracking setup without other raw subscribers saves the full-colour decode in the camera
node and the transfer of a full raw frame per image, and the detector decodes only the brightness it needs.

**Alternatives:** decoding at reduced size (`IMREAD_REDUCED_GRAYSCALE_2`) would be faster still, but halves the
pixels per marker, which at table distance are already few; detecting on regions around the last known markers is a
larger change, left for the page-detection work.

## 2026-10-27: README explains why frames are keep-last-1

**What changed:** the design decision "Frames are best-effort, keep-last-1" in the README now explains that the
queue depth decides which frame a slow node loses rather than whether it loses one, what a deeper queue changes
(spikes absorbed at the cost of latency; no help when processing is slower than the frame interval on average), and
why the framework prefers the newest frame: projected content must not trail what it belongs to.

**Why:** the README only stated that a late frame is worthless, which left open whether a deeper queue would reduce
dropped frames for a node that almost keeps up with the camera.

**Alternatives:** a per-node queue depth parameter (rejected for now: without measured processing times there is
nothing to tune it against).

## 2026-10-27: fiducials_detector settings in `par_setup.yaml`

**What changed:** a `fiducials_detector_node` section with `marker_type`, `dictionary`, `corner_refinement` and
`adaptive_thresh_constant`, set to the values the node used as code defaults.

**Why:** these are the settings to tune per setup (lighting, projector, required corner precision), and
`par_setup.yaml` is the one place for per-setup values. `dictionary` is written out because the printed pages and the
projected calibration markers depend on it.

**Alternatives:** also listing `use_compressed` and `use_depth` (rejected: they follow from the camera, and
`par.launch.py` sets them as overrides that would win over the file anyway).

## 2026-10-27: `debug` for fiducials_detector in `par_setup.yaml`

**What changed:** `fiducials_detector_node` lists the new `debug` parameter (off), which shows a preview window with
the detected markers.

**Why:** like `projection_mask`'s `debug`, it is switched in the one parameter file for a test run.

## 2026-10-27: Brio exposure 4 ms with gain 64 in `par_setup.yaml`

**What changed:** the Brio section sets the new `exposure_time_ms: 4.0` and `gain: 64`.

**Why:** with the driver's default 10 ms, a page moved quickly by hand blurs until its markers are no longer
detected; at 4 ms with gain 64 detection held up in a live test with this setup's light. The comment says to check for
flicker after changing it, because exposures below 10 ms can pulse under mains-powered light.

## 2026-10-27: page_locator's smoothing parameters for the 1€ filter

**What changed:** `page_locator_node` in `par_setup.yaml` sets `smoothing_min_cutoff_hz` and `smoothing_beta_per_px`
instead of `smoothing`.

**Why:** page_locator replaced its fixed exponential smoothing with the 1€ filter, which smooths a still page
strongly and a moving page hardly at all (details in the page_locator repository's documentation). A parameter
the node no longer declares would be ignored without a warning.

**Alternatives:** keeping `smoothing` as an alias (rejected: two ways to configure the same thing).

## 2026-10-27: page_locator's debug preview in the launch and the setup file

**What changed:** `par.launch.py` sets `use_compressed` for page_locator with the Brio, as for object_detector and
fiducials_detector, and its comment no longer claims that page_locator reads no camera topic. `par_setup.yaml` has
page_locator's `debug: false` with a description.

**Why:** page_locator got a debug preview that shows the camera frames; with the Brio, whose driver publishes JPEGs,
it must read the compressed topic like the detector, or the driver would decode every frame for it.

**Alternatives:** leaving `use_compressed` to the user (rejected: the launch file is the one place that knows what
each camera publishes).

## 2026-10-28: quick-launch.md with a ros2 run command per node

**What changed:** new `quick-launch.md` in the repository root: one `ros2 run` command per node (camera drivers,
mount transforms, detectors, calibration server, projection mask, apps, calibration tools), each with every parameter
the node declares and the remappings the launch files apply.

**Why:** starting a single node for a test, or trying one parameter value, should not need a launch or parameter
file. The values are those of `par_setup.yaml` where it sets them, so a command behaves like the node under
`par.launch.py`; where the node's own default differs, the file says so. The RealSense and webcam drivers declare far
more parameters than fit, so only the ones the framework sets are listed, with the command to see the rest.

**Alternatives:** node defaults only (rejected: the commands would behave differently from the launched setup, e.g.
the Brio's exposure); a script that generates the commands from the code (rejected: more code to maintain than the
list itself; the file names `ros2 param list` for checking the current parameters instead).

## 2026-10-28: calibration marker ids 0-8 in CLAUDE.md, webcam start resolves params_file

**What changed:** `CLAUDE.md` names the projected calibration markers as ids 0-8, which is what
`projection_calibrator_node` and `par_setup.yaml` use. `launch_helpers.create_webcam_nodes` takes the launch context
and passes the resolved `params_file` path to `v4l2_camera`, like the other camera starts.

**Why:** the ids are fixed at 0-8; the earlier move to 50-58 (entry above) no longer holds, and the guidance file must
not describe another setup than the code. The ids 0-8 are page ids 0-2 in page_locator's numbering, so they still stay
clear of the document pages (96-99). The webcam start was the only camera start that handed the unresolved
`LaunchConfiguration` to `Node`. That works, but it differed from the others for no reason, and every other start
resolves the path through the context.

**Alternatives:** leaving `create_webcam_nodes` as it was, since `Node` resolves substitutions itself (rejected: two
ways to do the same thing in one module); changing the other starts to pass the substitution instead (rejected: they
need the resolved path anyway inside the OpaqueFunction, so resolving it is the common case).

## 2026-10-28: quick-launch.md shows the Brio's values

**What changed:** the detector commands in `quick-launch.md` use the Brio's `use_compressed: true` /
`use_depth: false`, and the calibration server paths and the RViz configuration name the Brio. The text warns that a
raw-frame subscriber on the Brio slows down every node.

**Why:** the Brio driver decodes its JPEGs only while someone subscribes to raw frames, and does so in the path that
publishes the compressed frames. A command copied with the depth camera's `use_compressed: false` while the Brio runs
therefore lagged the whole pipeline. With a depth camera, a wrong `use_depth: false` only drops the 3D values, which
is the milder mistake.

**Alternatives:** both variants under each command (rejected for now: doubles the file; the table lists the
differences); keeping the Kinect's values because `par_launch.camera` names it (rejected: the camera is often chosen
per run with `camera:=`).

## 2026-10-28: `demo_app_node` gets its projector display

**What changed:** `par_setup.yaml` has a `demo_app_node` section with `display_id`.

**Why:** the demo app now lights the pages in a fullscreen window on the projector and needs to know which display
that is. Per-setup values belong in `par_setup.yaml`, not in node defaults.

**Alternatives:** a launch argument (rejected: the display does not change per run; `projection_mask` and
`projection_calibrator` keep theirs in the same file).

## 2026-10-28: `page_locator` expects upright markers

**What changed:** `par_setup.yaml` sets `marker_quarter_turns: 0` for `page_locator_node`; the comment names 3 for the
printed VIGITIA document pages.

**Why:** follows `page_locator`'s new default (reasoning in its log): pages are published clockwise from the top
left and sheets from `make_page_template` carry upright markers. Leaving 3 here would have overridden the new default.

## 2026-10-28: rendering manager in `config/nodes.list`

**What changed:** `config/nodes.list` lists `ros2-par-framework-rendering-manager` (branch `develop`) under a new
"Rendering" section.

**Why:** the repository now holds `rendering_manager_bridge`, an `ament_python` package one level down that colcon
builds like any node; the Rust compositor at its root has no `package.xml` and is left to `cargo build`. Pinned to
`develop` because the bridge exists only there so far; switch to `main` once it is merged.

**Alternatives:** the bridge as a package in this repository's `packages/` (rejected in the rendering manager's
`MASTER_PLAN.md`: it belongs with the control protocol it speaks).

## 2026-10-28: setup profiles (`profile:=<name>`)

**What changed:** every launch file of a setup (`par.launch.py`, `calibration.launch.py`,
`projection_calibration.launch.py`, `camera_pose_calibration_kinect.launch.py`) takes `profile:=<name>`. The profile
is `config/profiles/<name>.yaml` (gitignored) and holds only what differs from `params_file`. In `launch_helpers`:
`get_params_file_paths` returns `[params_file, profile]`, which every node gets (ROS applies the later file per key);
`read_merged_parameters` merges both the same way for what the launch files read themselves (`par_launch`, the
placeholder camera poses); `get_extrinsics_folder_path` puts a profile's camera pose, projection corners and mapping in
`calibration/extrinsics/<name>/`; `get_brio_camera_info_file_name` gives a Brio with `serial` set its own intrinsics
file, `camera_info_brio_<serial>.yaml`. `create_projection_calibration_server_node` takes the launch context now.
Without `profile:=`, all files and paths are the same as before.

**Why:** several physical setups (different tables, projectors, mounting heights, and several units of the same
camera type) share one checkout. Extrinsics describe a setup, so each profile needs its own; intrinsics describe a
lens, so they belong to the camera unit, not to the camera type and not to the profile.

**Alternatives:**
- *Full copies of `par_setup.yaml` as profiles* (as on the setup-wizard branch): no merge code, but copies drift, and
  a parameter added later is silently missing from old profiles. Rejected in favour of override files.
- *Intrinsics per profile:* a camera used in two setups would need its lens calibrated twice. Rejected.
- *A wildcard node key (`/**`) in profiles:* hides which node a value is for. Not used.
- *Replacing `params_file:=` with `profile:=`:* would drop arbitrary paths; both stay, the profile adds on top.
- *Webcam intrinsics per unit:* `v4l2_camera` exposes no serial, so they stay per type (marked `Simplification:`).
- The merge matches keys as written; ROS also accepts a node without leading slash or nested instead of dotted
  parameters. Marked `Simplification:` rather than normalising both spellings now.

## 2026-10-28: `page_locator` default layout clockwise from the top left

**What changed:** `par_setup.yaml` and `quick-launch.md` set `marker_corners: [top_left, top_right, bottom_right,
bottom_left]` for `page_locator_node`, next to `marker_quarter_turns: 0`; the comment lists the parameter sets of
both old VIGITIA sheet types.

**Why:** follows `page_locator`'s new default (reasoning in its log), so sheets printed with `make_page_template`
match the setup without overrides.

## 2026-10-28: `run_cameracalibrator.sh` takes the board size from `BOARD_SIZE`

**What changed:** the board's inner corners come from `BOARD_SIZE` (default `8x6`, the board in `utils/`).

**Why:** setups use other printed boards. cameracalibrator collects `--size` and `--square` as lists, so passing a
size through the script's extra options adds a second board instead of replacing the first.

**Alternatives:** a second positional argument (rejected: the remaining arguments already go to cameracalibrator,
and `CAMERA_NAMESPACE` sets the other optional value the same way).

## 2026-10-28: threshold window sizes of `fiducials_detector` in `par_setup.yaml`

**What changed:** `fiducials_detector_node` in `par_setup.yaml` and its command in `quick-launch.md` list the new
parameters `adaptive_thresh_win_size_min_px` / `adaptive_thresh_win_size_max_px` with OpenCV's defaults (3, 23).

**Why:** a single threshold window that suits the markers' size in the image makes detection faster without losing
markers (details in the `fiducials_detector` repo). The defaults keep every existing setup as it was; a profile sets
the faster value where it has been checked.

**Alternatives:** changing the default to one window for every setup (rejected: the right window depends on the
camera, its distance and the marker size, so it must be checked per setup).

## 2026-10-29: FLIR Blackfly S as camera `blackfly`

**What changed:** `camera:=blackfly` starts a FLIR Blackfly S through the released `spinnaker_camera_driver`
(`config/ros_packages.list`), as `/camera/blackfly`. `launch_helpers` got `create_blackfly_nodes` and its entry in
`CAMERA_DRIVER_REMAPPINGS`; `par_setup.yaml` its settings (fixed short exposure, fixed gain, high frame rate, a
driver queue of one frame) and a placeholder pose under `/blackfly_tf_publisher`; `par.launch.py` an RViz config.
Intrinsics are per unit (`camera_info_blackfly_<serial_number>.yaml`): `get_brio_camera_info_file_name` became
`get_camera_info_file_name`, shared by the Brio and the Blackfly. The webcam's body-to-optical transform became
`create_optical_frame_tf_publisher`, used by both cameras that need it. README, quick-launch and CLAUDE.md list the
camera.

**Why:** a fast global-shutter camera for the detectors. The driver is released for the distro and ships the Spinnaker
SDK, so a rosdep key is all a fresh computer needs. Details found on the real driver: its calibration parameter is
spelt `camerainfo_url`, and its `set_camera_info` service ignores the node's namespace and appears at the root, so the
remapping takes `/set_camera_info`. `frame_id` is set in the launch code, next to the transform it must match. The
exposure bounds the frame rate (a frame cannot be shorter than its exposure), so auto exposure is off; string values
such as `Off` are quoted, because YAML reads a bare `Off` as a boolean, which the driver silently ignores.

**Alternatives:**
- *Camera name `flir`:* ambiguous next to the FLIR Lepton thermal camera node. Rejected for `blackfly`.
- *Including the driver's `driver_node.launch.py`:* would bring its own node name, example parameters and a remapping
  to an exposure controller the framework doesn't run. Rejected; the node is started like the other drivers.
- *Best-effort images through `qos_overrides`:* matches the Brio's default, but couldn't be verified without the
  camera connected, and the driver's reliable default already reaches best-effort subscribers and `cameracalibrator`.
  Left at the driver's default.
- *Colour conversion in the driver:* the monochrome model only offers mono formats; nodes that need colour convert
  with cv_bridge.

## 2026-10-29: clearer names in `par.launch.py` and `create_mount_tf_publisher`

**What changed:** `CAMERA_OVERRIDES` is now `CAMERA_DETECTOR_PARAMETER_OVERRIDES` (also in the README), and the local
`pose` in `launch_helpers.create_mount_tf_publisher` is `camera_pose`.

**Why:** the old names didn't say what is overridden or whose pose it is.

**Alternatives:** renaming `DEPTH_CAMERA_OVERRIDES` and `get_invalid_pose_keys`'s parameter in the same pass (not
done: not part of the request).

## 2026-10-29: Blackfly binning and image size set explicitly

**What changed:** the `/camera/blackfly` section in `par_setup.yaml` sets `binning_x`/`binning_y` (1), `offset_x`/
`offset_y` (0) and `image_width`/`image_height` (full sensor size).

**Why:** the camera keeps these values until it loses power, and the driver only writes the parameters it is given.
After one run with 2x2 binning, every later start delivered binned images, and switching binning back to 1 alone
left the image at the reduced size. Listing all of them makes every start independent of what ran before. Binning
and size are only writable while the camera is not streaming, so they take effect at driver start only.

**Alternatives:** leaving them out and power-cycling the camera after a binning test (rejected: a silent wrong image
size changes every pixel coordinate, e.g. stored corners and intrinsics, without an error).

## 2026-10-30: event camera as an extra sensor (`event_camera`)

**What changed:** `par_launch.event_camera` (launch argument `event_camera:=true`) starts an event camera next to the
chosen camera: the released `metavision_driver` as `/event_camera`, and `event_camera_renderer` as
`/event_camera/renderer`, which turns the events into images on `/event_camera/renderer/image_raw`. Both are in
`config/ros_packages.list`; `launch_helpers` got `create_event_camera_nodes`, `par_setup.yaml` an `/event_camera`
section and the switch. `par.launch.py` starts it only when both packages are installed, otherwise it logs which list
to edit. It also starts with `camera_only`. README ("Event camera"), quick-launch and CLAUDE.md describe it, including
how to install a camera maker's OpenEB plugin by hand.

**Why:** an event camera publishes events, not frames, so the detectors and calibrations, which read
`/camera/image_raw`, can't use it; as a `camera:=` choice it would have replaced the image camera that they need.
Found on the real driver and camera: the driver needs a vendor plugin for cameras outside Prophesee's own, found only
through `MV_HAL_PLUGIN_PATH`. A missing variable ends in a bare "cannot open default camera", so the launch logs a
hint when the variable is unset. The driver catches no exceptions while writing a bias; on a USB 2 link a live bias
change aborted it and left the camera unopenable until replugged, while on USB 3 repeated changes at a high event rate
worked. The README therefore requires USB 3. The renderer subscribes to events only while its image has a subscriber,
so starting it with every event camera launch costs nothing when nobody watches.

**Alternatives:**
- *Event camera as `camera:=event`, with the rendered images remapped onto `/camera/image_raw`:* the detectors and the
  intrinsics calibration are built for normal images and mostly fail on accumulated events, and there would be no
  image camera in the same run. Rejected; chosen together with Vitus.
- *Including the driver's own `driver_node.launch.py`:* it hard-codes its parameters (e.g. `trigger_in_mode:
  external`), so `par_setup.yaml` couldn't set them. Rejected; started like the other drivers, with the parameter
  files.
- *Setting `MV_HAL_PLUGIN_PATH` in the launch file:* the folder depends on the camera maker's installer, not on the
  framework. Rejected for a hint naming the command.
- *A pose transform and intrinsics for the event camera:* nothing consumes them yet. Left out; the events carry
  `event_camera_optical_frame`, named like the other optical frames, so a transform can be added later.

## 2026-10-30: one RViz configuration for every camera

**What changed:** `config/rviz/par_framework.rviz` replaces `par_framework_<camera>.rviz` for brio, kinect,
realsense, webcam and blackfly. It is the former Kinect file (with its dock layout and the disabled point cloud) with
neutral display names ("Camera image", "Camera frustum") and an added, disabled "Event camera image". `par.launch.py`
uses `RVIZ_CONFIG_FILE_NAME` instead of the per-camera `RVIZ_CONFIG_FILE_NAMES`; README ("Adding a camera") and
quick-launch name the one file.

**Why:** every driver is remapped onto the same `/camera/...` topics, so the five files had become copies: without
comments, the webcam and Blackfly files were identical to the Brio's, and the others differed only in display names,
a saved window layout and the Kinect's disabled point cloud. Each new camera added another copy to keep in sync. A
disabled display subscribes to nothing, so topics only some setups publish can sit in the shared file switched off.

**Details:** Qt's saved dock layout (`QMainWindow State`) refers to the image panel by its display name, encoded as
UTF-16 inside the hex string; the name was changed there too ("Camera image" has the same length as "Kinect image",
so the length field stays valid). With `--symlink-install`, the build folder kept links to the removed files, which
made the next build fail ("doesn't exist or not a regular file"); removing the dangling links fixed it.

**Alternatives:** keeping separate files only for cameras that really differ, e.g. a depth camera with its point
cloud on (rejected: switching on one display in RViz is one click, while every extra file has to be kept in sync and
the existing copies had already drifted apart).

## 2026-10-30: event camera as camera `event`

**What changed:** the event camera is a `camera:=` choice like the others, replacing the extra-sensor switch
`par_launch.event_camera`. `camera:=event` starts `metavision_driver` as `/camera/event` and `event_camera_renderer`
as `/camera/event_renderer`; `CAMERA_DRIVER_REMAPPINGS['event']` maps the renderer's images onto `/camera/image_raw`
and the raw events onto the new neutral `/camera/events` (`DEFAULT_TOPIC_NAME_CAMERA_EVENTS`), which the renderer also
reads. The camera got a mount transform (`/event_tf_publisher`, placeholder pose in `par_setup.yaml`) and an optical
frame (`event_optical_frame`, set as the driver's `frame_id`). `par_setup.yaml` has the renderer's `fps` and
`display_type` under `/camera/event_renderer`. The disabled event display left the RViz config, since the image now
arrives on `/camera/image_raw`. README, quick-launch, CLAUDE.md and the camera lists of the launch files follow.

**Why:** Vitus' decision: a user mostly wants the image, and only sometimes the events. As an extra sensor, the
event camera's image never reached the detectors or the RViz camera display.

**Details:** the driver publishes no `camera_info`, so the event camera has no intrinsics, and what needs them
(`pixels_to_table`, the RViz frustum) does not work with it. Tested without the camera (it was unplugged) in its own DDS
domain, apart from another session's test: parameters reach the renderer, a subscriber on `/camera/image_raw` makes
the renderer subscribe to `/camera/events`, and `world` → `event_optical_frame` resolves. The driver's own topic
remapping was checked against its source (`~/events`, i.e. `/camera/event/events`), not with a running camera.

**Alternatives:**
- *Keeping the extra-sensor switch next to `camera:=event`:* two ways to start the same driver with different topic
  names. Rejected.
- *Keeping the events on the driver's own name (`/event_camera/events`):* every other camera topic is remapped onto a
  neutral name that nodes hard-code; the events follow that rule.
- *Camera name `silkyevcam`:* the driver runs every OpenEB camera, so a model name would need a second name for the
  same driver. `event` is generic like `webcam`.

## 2026-10-30: e-con See3CAM_CU40 as camera `cu40`

**What changed:** `config/nodes.list` adds `see3cam_cu40` (repo `ros2-see3cam-cu40`, branch `develop`).
`launch_helpers` has a `cu40` entry in `CAMERA_DRIVER_REMAPPINGS` (`image_raw`, `camera_info`, `set_camera_info`
onto the neutral names) and `create_see3cam_cu40_node`, which sets the intrinsics file per unit through `serial`
like the Brio. `par_setup.yaml` has the node's section (`/camera/cu40/see3cam_cu40_node`: serial, sensor mode,
`full_resolution`) and the placeholder pose `/cu40_tf_publisher`. The launch files list `cu40` among the cameras.

**Why:** The CU40 is an RGB-IR camera: a quarter of its pixels see infrared. It only offers V4L2 `Y16`, the raw
10-bit mosaic in 16-bit pixels, which no released ROS 2 driver turns into images (`v4l2_camera` aborts on `Y16`,
`usb_cam` has no package for this distro). So it gets its own node, which splits the mosaic into a colour and an
infrared image.

**Decisions:**
- *Own repo, not under `packages/`*: a camera driver is useful outside the framework.
- *`develop` in `nodes.list`*: the repo's `main` holds only its initial commit so far.
- *The infrared image keeps the driver's name* (`/camera/cu40/ir/image_raw`): the framework has no neutral
  name for infrared yet, and inventing one for a single camera would be a convention nothing consumes.
- *No `use_compressed` or depth override in `par.launch.py`*: the node publishes neither.

## 2026-10-30: See3CAM_CU40 infrared correction in `par_setup.yaml`

**What changed:** `/camera/cu40/see3cam_cu40_node` sets `visible_to_ir_leakage_bgr`, the share of the blue, green
and red signal that reaches the camera's infrared pixels; the node subtracts it from the infrared image.

**Why:** Projected content showed up in the infrared image. The shares depend on the spectrum of the light to be
removed, here the projector's, so they are per setup and live in the parameter file. The comment there says how
they are measured, so another setup can measure its own.

**Decisions:** The node's own default stays `[0, 0, 0]` (uncorrected), so a setup without a measurement gets the
unchanged infrared image instead of a correction made for another projector.

## 2026-10-30: See3CAM_CU40 infrared gain in `par_setup.yaml`

**What changed:** `/camera/cu40/see3cam_cu40_node` sets `ir_gain`.

**Why:** After the leakage correction the indoor infrared image was very dark. The gain is chosen so the brightest
parts of this setup's scene come close to full brightness; it depends on the scene's infrared light, so it is per
setup. A longer exposure was rejected: it costs frame rate and saturates the colour pixels, which breaks the
leakage correction.

## 2026-10-30: neutral name `/camera/ir/image_raw` for infrared

**What changed:** `launch_helpers` has `DEFAULT_TOPIC_NAME_CAMERA_IR = '/camera/ir/image_raw'`, and the `cu40` entry
remaps the driver's `/camera/cu40/ir/image_raw` onto it. `CLAUDE.md`, the README's topic table and the CU40
comment in `par_setup.yaml` name it; the README also lists the CU40 under `/camera/set_camera_info`.

**Why:** The CU40's infrared image was the only image stream left under its driver's name, against the convention
that framework nodes see only neutral `/camera/...` names, chosen by remapping.

**Decisions:**
- *The name promises the colour image's pixel grid*, like `depth_registered` does for depth, so a consumer can
  combine infrared and colour pixel by pixel. The CU40 meets it, because its infrared pixels are part of the colour
  sensor. The Kinect's infrared is on its depth camera's grid, so it is not mapped onto this name.
- *`/camera/ir/image_raw` instead of `/camera/ir_registered/image_raw`*: shorter, and as long as only cameras with
  infrared on the colour grid are mapped onto it, the rule is documented where the name is defined.

## 2026-10-30: See3CAM_CU40 infrared leakage correction switched off in `par_setup.yaml`

**What changed:** `visible_to_ir_leakage_bgr` is `[0.0, 0.0, 0.0]` again; the measured average shares stay in the
comment next to it.

**Why:** With `ir_gain` the infrared image showed bright and dark patches where the projector shone. Projecting
single colours and mapping what was left of them in the corrected infrared image showed that the leaked share
varies across the image, so one set of shares for the whole image under-corrects some regions and over-corrects
others, and the gain makes both visible. Under blue, horizontal stripes appeared as well, most likely because the
DLP projector's short light pulses meet the camera's row-by-row exposure, and the blue pixel lies in a different
row than the infrared pixel it corrects.

**Decisions:** Switched off rather than kept: a uniform projector image in the infrared image disturbs less than
patches that look like objects. The node's correction stays; a position-dependent version is to be decided after
measuring whether the share follows image position or the projection surface.

## 2026-10-30: `object_teaching` added to `config/nodes.list`

**What changed:** New line for `ros2-par-framework-object-teaching` (packages `training_images_collector` and
`transfer_learning_service`), pinned to `feature/object-teaching`.

**Why:** The old VIGITIA object teaching pipeline is ported step by step in that repo. Its `main` stays at the initial
commit until the first working version, so the remote's default branch would clone an empty repo.

**Decisions:** The pin moves to `main` once the port is merged there. The line goes on `develop` directly rather than a
core feature branch, because nothing else in core changes for the first port steps.

## 2026-10-30: `/datasets/` gitignored

**What changed:** `.gitignore` ignores `/datasets/` at the framework root.

**Why:** object teaching stores captured frames, its dataset and training runs in `<workspace root>/datasets/`
by default (`data_dir` parameter of its nodes); these are local recordings, not source.

**Decisions:** a root folder next to `/models/`, rather than inside `install/` (deleted by clean builds) or the
user's home (harder to find next to the framework).

## 2026-10-30: `par_geometry.table_to_pixels`

**What changed:** New function `table_to_pixels(points_m, camera_matrix, distortion_coefficients, rotation,
translation_m)`: table points (z = 0) to raw camera pixels, with the camera's distortion applied, via
`cv2.projectPoints` and the inverted camera pose. Exported from the package.

**Why:** object teaching stores its region as a table polygon in metres, but its trainer crops and masks the captured
camera frames in camera pixels. Until now the library only had the opposite direction (`pixels_to_table`).

**Decisions:** the same pose arguments as `pixels_to_table` (the optical frame's pose in the table frame), so callers
pass one TF lookup to both. Points behind the camera are not filtered, because a table region seen by the camera never
has any; the docstring says so. Checked with a round trip pixels -> table -> pixels on a tilted, distorted camera.

## 2026-11-04: `temporal_mean_frame_count` in `par_setup.yaml`

**What changed:** the `fiducials_detector_node` section lists the detector's new parameter `temporal_mean_frame_count`
(0 = off) with a comment on when to use it.

**Why:** per-setup values belong in `par_setup.yaml`; a setup with a noisy camera (short exposure at high gain) sets it
there or in its profile, without changing the node.

**Decisions:** off by default, because it roughly doubles the detection work per frame; the reasoning behind the
feature is in the fiducials repo's documentation.

## 2026-11-04: `/projector/content_mask` comes from the rendering manager

**What changed:** CLAUDE.md, "Projector masks": the content mask is no longer a convention for apps but an optional
topic of `rendering_manager_bridge` (`content_mask_enabled`), downscaled by `content_mask_downscale_factor` and stamped
with the drawing time.

**Why:** only the compositor knows the final projected image, including black areas inside apps; apps don't know the
warp or what lies over them. The reasoning and the alternatives are in the rendering manager repo's documentation.

**Decisions:** the mask is smaller than the projector's resolution, so consumers scale by its size; a full-resolution
mask would cost a large read-back and DDS bandwidth on every frame.

## 2026-11-04: tracking parameters in `par_setup.yaml`

**What changed:** the `fiducials_detector_node` section lists the detector's new parameters
`tracking_window_size_px` (0 = off) and `full_scan_rate_hz`, with a comment on what they do.

**Why:** per-setup values belong in `par_setup.yaml`; a setup with a large camera image and small markers turns
tracking on there or in its profile. Off by default, so other setups keep their current behaviour.

## 2026-11-04: `camera_info` dropped once calibrated

**What changed:** `rviz_bridge_node` destroys its `/camera/camera_info` subscription as soon as a message with a calibrated
camera matrix (`k[0] != 0`) has arrived, and logs that. Uncalibrated messages keep the subscription.

**Why:** `camera_info` comes with every camera frame, so at a high frame rate it costs one Python callback per frame,
yet the intrinsics do not change while the camera runs. Measured first in `demo_app`, where it lowered the node's
CPU load; applied to every node that only stores the message.

**Alternatives:**
- *Keep the subscription with a smaller queue*: rejected, rclpy still takes and deserialises every message.
- *Read the intrinsics from the calibration file*: rejected, some cameras publish factory intrinsics that exist only
  on the topic.
- *A shared helper for the pattern*: rejected for now, it would need a ROS-side shared package; the pattern is a few
  lines per node.
- Accepted limit (marked `Simplification:`): intrinsics stored with `set_camera_info` while the node runs take effect
  only after a restart.

## 2026-11-04: `fiducials_detector` bit-reading parameters in `par_setup.yaml`

**What changed:** `par_setup.yaml` lists `bit_sample_px_per_cell` and `bit_ignored_margin_per_cell` for
`fiducials_detector_node` at OpenCV's defaults, with a note on when to raise them.

**Why:** Small markers with few camera pixels per cell are read more reliably from more samples per cell and a wider
margin. A profile for such a setup can then use a single threshold window, which costs much less CPU. Defaults stay
at OpenCV's values, so other setups behave as before.

**Alternatives:** *Changing the defaults*: rejected until checked on a colour camera with larger markers.

## 2026-11-04: `demo_app` `page_content` in `par_setup.yaml`

**What changed:** `par_setup.yaml` lists the demo app's new `page_content` parameter at its default `white`.

**Why:** It lists every per-setup value; a profile switches to `checkerboard` for a showcase under projected content.

**Alternatives:** *A launch argument*: rejected, the launch files pass the demo app's settings only through
parameter files, and a profile already covers a per-setup choice.

## 2026-11-04: template for a sensor processing node

**What changed:** `templates/sensor_processing_node.py` is a blueprint for `<pkg>/<pkg>_node.py` of a node that
processes camera frames. It collects what the existing processing nodes share: neutral camera topics, the
best-effort depth-1 frame QoS, read-only parameters with descriptions, the optional `use_compressed` and
`use_depth` inputs (pairing, missing-depth warning, 16UC1 to metres, pixel-grid check), dropping `camera_info`
once calibrated, one result message per frame with the frame's header, throttled warnings, and the shutdown
pattern in `main()`.

**Why:** Each node had grown the same pieces separately, with small differences in names and behaviour (e.g. the
`main()` without the shutdown-race handling in some nodes). A new node starts from the agreed version instead.

**Decisions:**
- *One commented Python file instead of a generator (cookiecutter, `ros2 pkg create` template).* Copying and
  renaming one file is enough today, and it needs no new dependency.
- *Optional blocks included and marked, rather than left out.* `use_compressed` and `use_depth` are the parts
  most often copied between nodes and the easiest to get subtly wrong.
- *Missing-depth check inline in the node, not as a helper class.* `fiducials_detector` has one in its logic
  module, but a template can't import it; the few lines of timing are ROS glue anyway.
- *No TF or table coordinates.* Detectors publish camera pixels; consumers convert with `par_geometry`.

## 2026-11-05: rendering manager in `par.launch.py`

**What changed:** New switch `rendering_manager` (`par_launch` and launch argument). It starts the rendering
manager (Rust program) fullscreen on the projector with `--socket-name par-tabletop` and `--display-id` from the
new `rendering_manager` section of `par_setup.yaml`, plus `rendering_manager_bridge` with the parameter files and
the control socket path. A log line says what is missing when the bridge package or the built program is absent,
and a warning when `demo_app` is on as well. `local_build.sh` builds every `src/*/Cargo.toml` with
`cargo build --release` in full builds. `par_setup.yaml` lists the bridge's page app defaults and explains in a comment how a page gets its own app
(`page_ids_with_own_app`, `page_apps.page<id>.*`).

**Why:** One command starts camera, detectors, compositor and bridge. colcon builds only the ROS packages, so the
Rust program needs its own build step; release mode because the launch file starts that build.

**Alternatives:** *colcon-cargo*: a new build dependency for one program, rejected. *Installing the program into
the bridge's install space*: `cargo install` rebuilds from scratch each time; instead the launch file follows the
bridge's `--symlink-install` link to its repo (marked `Simplification:`). *Searching for the control socket in the
bridge*: ambiguous with several compositors, so the launch file fixes the socket name. It is
`wayland-99-par-tabletop`: snap apps such as Chromium may only open sockets matching `wayland-[0-9]*` (their AppArmor
profile), so a plain name like `par-tabletop` makes them fail with "Permission denied".

## 2026-11-06: `debug` launch argument in `par.launch.py`

**What changed:** New launch argument `debug` (`true`, `false`, or empty). When set, `par.launch.py` adds
`{'debug': <value>}` to the parameters of every framework node it starts (detectors, `projection_mask`,
`demo_app`, `rviz_bridge`); empty keeps each node's value from the parameter files. The true/false check of the
node switches moved into a shared `read_true_false_argument()`, which both use.

**Why:** Testing a feature (e.g. gestures: `hand_landmarks` and `gesture_detector`) needs the debug windows of the
nodes involved. Before, `debug` could only be set in `par_setup.yaml` or a profile, or by starting the node by hand,
because most nodes read it once at startup. One argument makes "start everything for this test, with previews" a
single command. Nodes that declare no `debug` parameter ignore the override (rclpy drops overrides for undeclared
parameters), so no list of which nodes have one is needed.

**Alternatives:** *One argument per node (`hand_landmarks_debug:=true`, ...)*: five more arguments, and only the
started nodes would get it anyway, so a single switch already reaches just the nodes of the test; per-node control
stays possible in `par_setup.yaml` or a profile. *A list of node names (`debug:=hand_landmarks,gesture_detector`)*:
more flexible but a second syntax to learn for little gain. *Keeping a list of nodes that have `debug`*: has to be
updated with every node that adds one; rejected since undeclared overrides are harmless.

## 2026-11-06: Kinect infrared on the colour grid, `use_ir` for hand landmarks

**What changed:**
- Kinect driver (`src/azure_kinect_ros_driver`): new topic `ir_to_rgb/image_raw`, the IR image transformed into the colour camera's geometry with the Azure Kinect SDK's `depth_image_to_color_camera_custom` (IR viewed as `CUSTOM16`, linear interpolation, 0 where there is no depth), stamped like `depth_to_rgb`, in the colour camera's frame. It is only computed while someone subscribes.
- `launch_helpers.CAMERA_DRIVER_REMAPPINGS['kinect']` remaps it onto the neutral `/camera/ir/image_raw`; CLAUDE.md says so instead of "stays unmapped".
- `par_setup.yaml`: `hand_landmarks_node.use_ir: false` with an explanation (the node is in the `hand_landmarks` repo).

**Why:** Hands under a projected checkerboard were lost completely in the colour image; in the Kinect's IR image, with contrast enhancement, they were found (offline test, kanban card "Detect hand gestures"). The framework's convention is that `/camera/ir/image_raw` lies on the colour image's grid, so landmarks found in IR are colour pixels and line up with the registered depth and `camera_info` like before. Transforming in the driver keeps every node camera-neutral and serves any later IR consumer too.

**Alternatives:** *Running MediaPipe on the IR image's own grid and moving the landmarks to colour pixels in `hand_landmarks`* (via depth, both intrinsics and TF): Kinect-specific code and extra subscriptions in a camera-neutral node, and a landmark without depth could not be moved; rejected by Vitus in favour of the driver. *Remapping the raw `ir/image_raw`*: wrong pixel grid for every consumer.

## 2026-11-06 — Capture camera: a second Blackfly S in software trigger mode

**What:** New `par_launch` switch `capture_camera` (also a launch argument of `par.launch.py`). It starts a second
`spinnaker_camera_driver` as `/capture_camera/blackfly` (`launch_helpers.create_capture_camera_node`), with the new
mapping file `config/blackfly_s_software_trigger.yaml` (the driver's `blackfly_s.yaml` with `trigger_mode` after
`trigger_source` and a `trigger_software` command parameter). `par_setup.yaml` gets the section
`/capture_camera/blackfly` with the trigger parameters and a long `acquisition_timeout`; serial and image format go
into the setup's profile.

**Why:** Apps such as the tabletop worksheets need single high-resolution colour frames of a sheet, while another
camera keeps tracking at a high frame rate. A software trigger avoids streaming full-resolution frames over USB all
the time.

**Decisions and rejected alternatives:**
- Not remapped onto `/camera/...`: the main camera keeps that interface, and the capture camera's frames are only
  for the app that triggers them. Rejected: a general multi-camera scheme for all cameras, larger than one use needs.
- The launch fails without a `serial_number` for the capture camera: otherwise the driver opens the first Blackfly
  it finds, which can be the main camera. Rejected: falling back to the first camera found.
- The mapping file is a copy of the driver's file, kept in the framework. Rejected: changing the installed driver
  file (lost on every update, and it would change the main Blackfly too).
- `acquisition_timeout` of one day: the driver restarts streaming when its last frame is older than this, and in
  trigger mode a restart between two captures can lose the next trigger.
- Not started with `camera_only:=true`, which keeps meaning the main camera alone. No transforms and no
  calibration use yet: nothing maps the capture camera's pixels onto the table so far.
- Not done yet: a first trigger right after start, and a restart after a USB reconnect.

## 2026-11-06 — Focus preview for any camera (`scripts/focus_preview.py`)

**What:** A small rclpy script that shows the newest frame from `/camera/image_raw` scaled to fit, next to its centre
crop enlarged without smoothing, with a sharpness score (variance of the Laplacian of the crop, averaged over a few
frames) and the peak score so far. Keys: `q` quits, `r` resets the peak.

**Why:** After a camera is remounted it has to be refocused by hand. The enlarged crop shows single pixels, and
the score with its peak shows when the focus ring has passed the best setting, which is hard to see by eye on a
noisy, high-gain infrared image.

**Decisions and rejected alternatives:**
- Subscribes to the neutral camera topic, so it works with every camera the launch files start. Rejected: talking to
  one camera's SDK directly (works for one camera only, and not while the driver runs).
- A script in `scripts/` instead of a node package: it is a setup tool, not part of a running setup. Rejected: a
  package with an entry point (build step for a tool that has no dependents).
- The crop's brightness is stretched for display only; the score uses the raw pixels, so the stretch does not
  change it. A dim frame behind an infrared filter would otherwise show its edges poorly.
- The score has no absolute threshold: it depends on the scene and the light, so only the peak in the same scene is
  a fair reference.
- Converts `sensor_msgs/Image` with NumPy instead of `cv_bridge`, for the four 8-bit encodings the drivers publish.

## 2026-11-06 — Launch file for the checkerboard camera pose (`camera_pose_calibration_sheet.launch.py`)

**What:** Starts the chosen camera (`camera:=` or `par_launch.camera`) and `sheet_pose_calibrator` from
`ros2-par-framework-calibration`, with the board size (`board_columns`, `board_rows`, inner corners) and
`square_size_mm`, and writes `camera_pose_<camera>.yaml` into the profile's extrinsics folder. The launch ends when
the calibrator is done.

**Why:** Cameras without depth need a measured pose too, especially when mounted at an angle.

**Decisions and rejected alternatives:**
- Its own launch file instead of a mode in `camera_pose_calibration_kinect.launch.py`: that one is about the Kinect's
  depth; this one works for every camera with intrinsics, including the Kinect's colour camera.
- Starts the camera itself like the Kinect launch, so one command does the measurement. Rejected: attaching to an
  already running camera, which would depend on what else was started.
- The body frame per camera (`<camera>_link`, the Kinect's `camera_base`) is derived in the launch file, matching
  `create_camera_nodes`.

## 2026-11-06 — Setup wizard skeleton: Flutter app and FastAPI backend (`setup_wizard/`)

**What:** New top-level folder `setup_wizard/` with a Flutter desktop project (`app/`, package `par_setup_wizard`,
Linux only for now, generated with `flutter create --empty`) and a Python backend (`backend/setup_wizard_backend.py`,
FastAPI served by uvicorn on `127.0.0.1:8800`, one endpoint `GET /api/status`). `backend/requirements.txt` adds
`fastapi` and `uvicorn`; `scripts/local_build.sh` includes it in its single `pip` call.

**Why:** The setup wizard is rebuilt in Flutter so the same UI can later run on a phone or in a browser. Everything
that touches the PAR machine (profiles, cameras, displays, launches) goes through a backend on that machine, so the
desktop app already talks to it the way a phone or browser will.

**Decisions and rejected alternatives:**
- Outside `packages/`, because colcon scans that folder; the backend is not a ROS package, it will start launches as
  subprocesses. Rejected: an `ament_python` package under `packages/` (a build step for something no node depends on).
- FastAPI + uvicorn: WebSockets built in (needed for live sharpness, preview, logs, install progress), typed request
  validation at the network boundary, generated API docs at `/docs`, and the same stack as the worksheets app's
  backend. Rejected: Flask (WebSockets only through add-ons, one thread per open connection or a Socket.IO protocol
  the Dart side would need a special client for; no built-in validation), aiohttp (nothing else in the project uses
  it), rosbridge (cannot start processes or read files), gRPC (browsers need a proxy), the Flutter app starting
  Python directly (rules out phone and browser).
- Installed into the shared `.venv` instead of a separate environment like the worksheets backend, because the
  backend will import `launch_helpers` from the sourced workspace; lower bounds match worksheets so the one `pip`
  call stays conflict-free.
- Bound to `127.0.0.1` only: nothing authenticates requests yet. Port 8800 because the worksheets backend uses 8000.
- Linux desktop only for now; web and Android are added later with `flutter create --platforms=... .`.
- The app reaches the backend through the `http` package (Dart team), wrapped in `SetupWizardBackendClient`
  (`lib/setup_wizard_backend_client.dart`) so screens never build URLs themselves. Rejected: `dart:io`'s
  `HttpClient`, which does not exist in a browser build. The start screen shows the connection and the machine name
  at the bottom, with the command to start the backend when it is unreachable.

## 2026-11-06 — Setup wizard: profile list and start screen dropdown

**What:** The backend lists the profiles (`GET /api/profiles`: the names of `config/profiles/*.yaml` and the one
selected last time) and stores the selection (`PUT /api/profiles/last-selected`) in the hidden file
`config/profiles/.setup_wizard_last_selected_profile`. The app's start screen (`lib/start_screen.dart`) shows a
dropdown of the profiles with the last one preselected and "+ New profile" at the end; Continue saves the selection
and opens a placeholder for the overview or the new-profile screen, which come next.

**Why:** First step of the wizard's flow: a returning user picks their hardware setup, a new user creates one.

**Decisions and rejected alternatives:**
- The backend reuses `FOLDER_PATH_PROFILES`, `FILE_NAME_PART_PATTERN` and `get_path_in_config_folder` from
  `launch_helpers`, so it finds exactly the profiles `profile:=` accepts. This needs a sourced workspace to start
  it. Rejected: deriving `packages/par-framework-core/config/` from the backend's own path (works unsourced, but
  copies the lookup and misses its `--symlink-install` handling).
- The last selection lives in the profiles folder, which is gitignored as a whole, because it belongs to the
  machine, not the repository. A leading dot and no `.yaml` keep it out of the profile list. Rejected: a file in
  `config/` (would need its own `.gitignore` entry) or remembering it in the app (a phone would not know what the
  desktop chose).
- `PUT` accepts only names of existing profiles, since the name ends up in a file path and in `profile:=`;
  unknown names get 404, malformed requests FastAPI's 422.
- Without a stored selection the first profile is preselected, without any profile "+ New profile".
- Running without a profile (`par_setup.yaml` alone) is not offered: a hardware setup is a profile.

## 2026-11-06 — Setup wizard: profile cards, title and dark theme

**What:** The start screen shows every profile as a card with its cameras, sensor nodes and apps instead of a
dropdown; a click selects a card (highlighted border), the last card starts a new profile. `GET /api/profiles`
returns one summary per profile for this. The app is titled "ROS 2 PAR Framework" (app bar, `MaterialApp.title`
and the native window title in `linux/runner/my_application.cc`) and always uses a dark Material 3 theme.

**Why:** Choosing a hardware setup by name alone needs knowing what each name means; the card shows it.

**Decisions and rejected alternatives:**
- The backend reads a profile's `par_launch` section through `launch_helpers.read_launch_section` with a
  `LaunchContext` whose `params_file` and `profile` are set as `par.launch.py profile:=<name>` would set them, so
  the cards show exactly what a launch would run. Rejected: merging the YAML files itself (a second copy of the
  merge rules) or importing the private `_merge_parameters`.
- Sorting the switches: `demo_app` and `rendering_manager` are apps; `projection_mask`, `rviz` and `capture_camera`
  are not shown as nodes; every other switch that is on counts as a sensor node, so a new detector appears without
  a backend change. The capture camera is listed under cameras. Rejected: an explicit sensor node list copied from
  `DETECTORS` in `par.launch.py` (two lists to keep in sync). The rendering manager's per-page apps are not shown.
- A profile whose files cannot be read gets a card with the error instead of failing the whole list.
- Dark theme always (`themeMode: ThemeMode.dark`), not following the desktop setting, since projection setups
  usually run in dimmed rooms.

## 2026-11-06 — Setup wizard: projector background on the start screen

**What:** `lib/projector_background.dart` draws a simplified grey projector in top view (body with a few vent lines,
lens barrel pointing down with light yellow glass), fixed at the top centre with its upper quarter above the
window's edge, and a faint yellow light cone from the lens that reaches the window's edges. Only the cone follows
the mouse cursor, by a quarter of the angle and at most 12°. The start screen wraps its content in it and extends
its body behind the connection bar (`extendBody`), so the light reaches the window's bottom edge.

**Why:** Makes the start screen recognisable as the projection framework's, without an image asset.

**Decisions and rejected alternatives:**
- Drawn with a `CustomPainter` from a few shapes, so it scales with the window and needs no file. Rejected: an SVG or
  PNG asset (needs a package such as `flutter_svg` for SVG, or a fixed-resolution image).
- The projector stays still and only the light moves, and only slightly, so the background does not distract.
- The cone is drawn longer than the window and clipped to it, so it always ends at the window's edges.
- The widget wraps the content and tracks the cursor with a translucent `MouseRegion`, because a background behind
  the content would not receive hover events over the cards. The cursor position goes through a `ValueNotifier`
  passed as the painter's `repaint`, so a mouse move repaints only the background, not the cards.
- The cone fades with the distance from the lens, so text over it stays readable; the cards are opaque anyway.

## 2026-11-06 — Setup wizard: camera calibration state on the profile cards

**What:** `GET /api/profiles` reports per camera of a profile the state of its intrinsics (`calibrated`, `factory`,
`missing`, `unsupported`) and of its pose (`measured`, `placeholder`, `invalid`, `unsupported`). The app combines
both into three levels and shows them as an icon on the camera chip: green check (everything the camera supports is
calibrated), amber warning (one of the two), red cross (neither); a tooltip names each state.

**Why:** Shows at a glance which hardware setup is ready and which still needs a calibration step.

**Decisions and rejected alternatives:**
- Intrinsics and pose together in three levels, chosen over intrinsics only (would hide a missing pose, which every
  table coordinate depends on) and one icon per calibration including the projection mapping (too busy for a card;
  belongs on the overview).
- The intrinsics file name comes from `launch_helpers.get_camera_info_file_name`, with the node section and serial
  parameter per camera copied from the `create_*_node` functions (marked as a simplification in the backend; a
  shared function returning a camera's intrinsics path would remove the copy). Kinect and RealSense count as
  calibrated (factory intrinsics); the event camera's intrinsics and the capture camera's pose are `unsupported`
  and do not count against the level.
- The pose is the file `create_mount_tf_publisher` reads (`camera_pose_<camera>.yaml` in the profile's extrinsics
  folder), checked with `get_invalid_pose_keys`, so a broken file shows as `invalid` instead of as measured.
- Intrinsics files are only checked for existence, not content (marked as a simplification).
- Icons differ in shape as well as colour, so the state does not depend on telling green, amber and red apart.

## 2026-11-06 — Setup wizard: profile names and installed cameras in the new-profile wizard

**What:** The wizard's first step (`new_profile_hardware_step.dart`) asks for a friendly profile name (e.g. "Labor
Neu") and an internal name (e.g. `labor_neu`), derived while typing and editable, and lists the installed cameras as
checkboxes (none, one or several). New backend module `cameras_api.py` (`GET /api/cameras`: every camera of
`CAMERA_DRIVER_REMAPPINGS`, its driver packages and whether they are installed) and the app-side
`lib/cameras_api.dart`. `NewProfileDraft` holds `profileDisplayName`, `profileName` and a list `cameraNames`.

**Why:** The internal name is a file name and the value of `profile:=`, so it must be plain; people should still be
able to call their setup what they like. A profile can now have several cameras.

**Decisions and rejected alternatives:**
- The internal name is derived (lowercase, ä/ö/ü → ae/oe/ue, ß → ss, other characters → `_`) until the user edits it
  by hand; emptying it hands it back to the derivation. Checked against `FILE_NAME_PART_PATTERN` and the existing
  profiles. Rejected: only one name field (either unreadable names on the cards or unsafe file names).
- "Installed" means every driver package of the camera is found by `ament_index_python` (`has_resource`), the check
  `par.launch.py` uses for optional nodes. The camera → package map copies the `create_*_node` functions (marked as
  a simplification). Not-installed cameras are named in one line instead of being hidden, so it is clear they exist.
- Rejected: listing only connected cameras; detecting connected units is a separate step (see the card's
  multi-camera section), and the list now selects camera types, not units.
- The friendly name is not stored yet: finishing the wizard still saves nothing.

## 2026-11-06 — Setup wizard: profiles open on click, internal profile name hidden

**What:** The start screen has no Continue button any more: clicking a profile card stores it as the last used one
and opens its hub; clicking "New profile" opens the wizard. The last used profile stays framed. In the wizard's
first step the internal name field is gone: `createInternalProfileName` generates it from the friendly name
(umlauts transliterated, other characters → `_`, `profile` when nothing usable is left). A name whose profile
exists already is refused with a warning under the field; Next stays disabled. Ticking a camera in that step shows
the live preview of the camera ticked last next to the list (`CameraPreviewView`, below the list in narrow
windows).

**Why:** One click less per start, and the internal name is a technical detail users should not have to handle.

**Decisions and rejected alternatives:**
- A taken name is refused instead of made unique with a suffix: two profiles that differ only by `_2` would be
  hard to tell apart. Names are compared by their internal form, so "Labor Neu" and "labor-neu" collide. Rejected:
  showing the internal name read-only (still a detail users need not see).
- The preview shows one camera at a time (the neutral camera topics exist once), the one ticked last, so the user
  sees which camera is which while choosing.
- Next waits for the existing profiles to load, so a taken name is always detected.
- The frame on the last used profile is kept as orientation, although selecting no longer needs it.

## 2026-11-06 — Setup wizard: camera preview stops when nobody watches

**What:** A watchdog thread in `camera_preview_api.py` stops the preview's camera once no frame was requested for
`PREVIEW_UNWATCHED_TIMEOUT_S` (5 s); the app requests one about every 0.1 s while a preview is shown.

**Why:** The camera kept running after the preview was left. The app's stop request on leaving the screen does not
cover every case, e.g. a closed window or a crashed app.

**Decisions and rejected alternatives:**
- In the backend, because only the backend sees every way a preview can end. Rejected: relying on the app's stop
  alone (never sent when the app quits or crashes), a stop request on window close (desktop only, not for a phone
  or browser that loses its connection).
- Five seconds, so a short hiccup in polling does not restart the camera, but an abandoned camera does not keep the
  device busy for long.

## 2026-11-06 — Setup wizard: settings of the previewed camera

**What:** `GET /api/camera-preview/settings` (in `camera_preview_api.py`) reads the previewed camera's settings
live from its driver node through the ROS 2 parameter services (`AsyncParameterClient`: `list_parameters`,
`describe_parameters`, `get_parameters`) and returns name, value, type, description, range and read-only flag.
`lib/camera_settings_view.dart` lists them read-only under the preview in the wizard's first step and retries
while the camera is still starting.

**Why:** The user should see which settings a camera offers and their allowed ranges, from one source that always
matches the installed driver.

**Decisions and rejected alternatives:**
- Ranges and descriptions come from the drivers' `ParameterDescriptor`s, ROS 2's own mechanism, which our nodes
  already use. Rejected: the comments in `par_setup.yaml` (written for people, no fixed format, ranges only as
  prose) and a separate table of ranges (would drift from the drivers).
- Shown are the parameters with a range plus a few per camera without one (resolution, frame rate); both the
  driver node names and that list are copied knowledge, marked as simplifications until the camera catalog names
  the node and the settings to show.
- One parameter client per driver node, kept for the backend's lifetime, because rclpy offers no way to destroy
  one on its own. Waiting for the driver happens outside the session lock, so frames keep flowing.
- Read-only for now; changing values (live through `set_parameters` or by restarting the driver) and storing them
  in the profile come later.

## 2026-11-06 — Setup wizard: cameras as a cart, preview and settings in the next step

**What:** The wizard's first step lists the installed camera types with − count + instead of checkboxes; every
added camera becomes an instance named `<type>_<n>` (`NewProfileDraft.cameraInstances`, `CameraInstanceDraft`).
Preview and settings left that page: the camera image step now goes through the instances one by one with the
live preview and the settings next to it, the intrinsics step with the preview only, both through the shared
`lib/camera_instance_preview_panel.dart`.

**Why:** A setup can contain several units of one type (e.g. two Brios), and the first page should stay a quick
choice of name and hardware.

**Decisions and rejected alternatives:**
- Instances named `<type>_<n>` with the lowest free number, as decided for the multi-camera model; removing takes
  the instance added last, like lowering a count in a cart. Editing instance names comes with choosing units.
- One shared panel for both steps instead of a copy in each; the settings list is switched on per step.
- Until each instance gets its unit (serial or USB port), the preview starts a camera by type, so every instance
  of one type shows the same physical camera; the panel says so (marked as a simplification).

## 2026-11-07 — Setup wizard: start screen shows one profile, switching through a menu

**What:** The start screen shows only the profile opened last time, as one card centered on the page (the first
profile when the last one no longer exists, the "New profile" card when there is none). A menu button in the
bottom left corner, next to the backend connection, lists all profiles (the shown one checked) and "New profile".
Picking a profile in the menu only switches the shown card; clicking the card opens the profile, which also
remembers it as the last opened one.

**Why:** A machine rarely changes its hardware setup, so a grid of all profiles made the common case (open the
same profile again) compete with a rare one.

**Decisions and rejected alternatives:**
- Picking a profile in the menu shows its card instead of opening it right away: the card shows the calibration
  state before the user commits, and opening stays one click on the card. Rejected: opening directly from the
  menu, which would make the centered card pointless for every profile but the last one.
- `MenuAnchor` with one `MenuItemButton` per entry instead of a `DropdownButton`: each entry has its own action,
  so "New profile" needs no sentinel value mixed in with the profile names.

## 2026-11-07 — Setup wizard: camera settings shown generically

**What:** The camera image step shows every parameter of the camera's driver node, except those ROS 2 itself
adds to nodes and image publishers (`use_sim_time`, `start_type_description_service`, `qos_overrides.*`,
image_transport's `*.enable_pub_plugins` and plugin parameters such as `image_raw.compressed.jpeg_quality`).
`EXTRA_SHOWN_SETTING_NAMES_BY_CAMERA` and the rule "only settings with a range" are gone.

**Why:** The wizard is meant to work with any ROS 2 camera driver that follows ROS conventions, without code per
driver. Showing only ranged parameters hid settings the camera image step needs, e.g. a webcam's
`auto_exposure` (a menu control without range) and `white_balance_automatic` (a bool): the automatic modes must be
switched off before manual exposure or white balance take effect.

**Decisions and rejected alternatives:**
- Filter out what ROS adds rather than pick what a driver adds: the ROS side is the same for every driver, a pick
  list would have to be written per driver. Rejected: adding the missing names to the per-camera list (one more
  special case per driver).
- image_transport plugin parameters are recognised by the plugin names shipped with ROS 2 (marked as a
  simplification); asking pluginlib for the installed plugins would cover third-party plugins too.
- Wiring parameters of the driver (device path, frame id, `camera_info_url`, serial) are shown as well: ROS has
  no convention that separates them from image settings. How to group or hide them is open.

## 2026-11-07 — Setup wizard: table on the start screen

**What:** The start screen's profile card stands on a dark table drawn at the bottom of the window
(`lib/tabletop_shape.dart`): a tabletop seen slightly from the front, narrower at the back, above a darker front
face that the connection bar and the profile menu sit on. `ProjectorBackground` takes an optional
`surfaceUnderLight`, drawn behind the light cone, so the projector's light falls onto the tabletop.

**Why:** The framework projects onto a table; the start screen now shows that scene: projector, light, table,
and the profile on it.

**Decisions and rejected alternatives:**
- The table lies under the light cone instead of in front of it: in front, it cut the light off at its back edge
  like a wall.
- The front edge spans the whole window, as if the user stood at the table, so the menu in the bottom left corner
  sits on the table. Rejected: a table narrower than the window, which left the menu next to it on the floor.
- Drawn from shapes in the theme's colours, like the projector, so it scales with the window and needs no image.
- Known limit: the light also falls onto the vertical front face, which a real projector from above would not
  light.

## 2026-11-07 — Setup wizard: camera preview survives resizing and step changes

**What:** Starting a preview returns a `preview_id`; stopping names that id instead of the camera, and the backend
ignores a stop for any other preview. `CameraPreviewView` remembers its id and also stops a preview whose start
was answered only after the view had closed. The new-profile wizard builds only the current step's content, and
`CameraInstancePreviewPanel` keeps preview and settings under `GlobalKey`s. Below a width that grows with the
number of steps, the wizard's stepper is vertical. A long setting value wraps instead of overflowing.

**Why:** Resizing the window across the panel's side-by-side width disposed the preview and created a new one;
the new view started the camera, the old one's stop named the same camera, and the backend ended the new preview.
Flutter's `Stepper` keeps every step's content alive (horizontal: `Visibility(maintainState: true)`, vertical:
`AnimatedCrossFade`), so the hidden Intrinsics step ran a second preview of the same camera, each start replacing
the other's camera process. The horizontal stepper header overflowed in narrow windows, and since every driver
parameter is shown, a file URL overflowed the settings list.

**Decisions and rejected alternatives:**
- The id protocol fixes the race at its root: any two views previewing one camera (resize, Next, Back) can no
  longer stop each other. Rejected: only the `GlobalKey`s, which fix the resize but not moving between steps.
- The `GlobalKey`s are kept on top, so a resize moves the running preview instead of restarting the camera.
  Switching between vertical and horizontal stepper still rebuilds the step and restarts the preview; that is rare
  and now safe.
- Steps restore themselves from `NewProfileDraft` when they come back, so not keeping hidden steps alive loses no
  input.

## 2026-11-07 — Setup wizard: light ends at the table, brighter rays through the cursor

**What:** The light cone no longer has a fixed opening angle and no longer turns towards the mouse. Its edges run
from the lens to the tabletop's back corners and cover the whole tabletop to its front edge. While the cursor is
inside the light, a narrow, blurred wedge of brighter rays runs from the lens through the cursor. The table moved
into the projector background's painter (`tabletop_shape.dart` now holds its geometry and painting), replacing
the `surfaceUnderLight` slot.

**Why:** The light should match the table at every window size, as a projector set up for its table does, and the
cursor reads as something held into the light.

**Decisions and rejected alternatives:**
- The cone follows from the table's corners instead of an angle: an angle that fits one window size misses the
  table in another. The vertical front face stays dark, as under a projector shining from above.
- Table and light in one painter, because the light's shape depends on the table's corners. Rejected: passing the
  table geometry between two widgets, which keeps two places that must agree.
- The wedge is clipped to the light and drawn only while the cursor is inside it: rays cannot pass through a
  cursor that is outside the light.

## 2026-11-07 — Setup wizard: preview restarts reliably, camera feeds and editable settings

**What:**
- Backend (`camera_preview_api.py`): a start no longer refuses because of the camera it has just stopped. The
  publishers of `/camera/image_raw` that a stopped preview had (by DDS endpoint GID) are remembered and count
  neither as another program's camera nor as the next preview's driver.
- The driver node is found as the node publishing `/camera/image_raw`; `DRIVER_NODE_NAME_BY_CAMERA` is gone.
  `GET /api/camera-preview/feeds` lists every `sensor_msgs/Image` topic that node publishes, and
  `GET /api/camera-preview/frame?topic_name=` serves each feed; depth and 16-bit images (`16UC1`, `mono16`,
  `32FC1`) are stretched to 8-bit gray between their 1st and 99th percentile, 0 and NaN staying black.
- `PUT /api/camera-preview/settings` sets one setting on the running driver through `set_parameters`; the value is
  converted to the parameter's current type (whole numbers only for integers), and a refusal returns the
  driver's reason. Settings carry the descriptor's `additional_constraints`.
- The start takes an optional `profile_name` (`profile:=`), checked against the saved profiles
  (`profiles_api.check_profile_exists`, also used by the last-selected endpoint). Profile summaries name the
  camera type to preview (`preview_camera_name`), None for the capture camera.
- App: `CameraPreviewView` shows every feed (one large, several in two columns), each polling its own frames.
  `CameraSettingsView` offers a switch for bools, a slider for numbers with a range (sent on release), a text
  field otherwise (sent with Enter, lists comma-separated), and shows the driver's refusal under the setting.
  `CameraPreviewWithSettingsView` (feeds plus settings, side by side or stacked, with the `GlobalKey`s) is shared
  by the wizard panel and the hub's overview, which now lists the profile's cameras: clicking one starts it with
  the profile's settings.

**Why:** Moving from the Camera image to the Intrinsics step stopped one preview and started the next; the old
driver, ended by a signal, stays in the ROS graph until its DDS lease runs out, so the start took it for another
program's camera and refused. A depth camera has several images worth checking (colour, depth, infrared), and
settings must be adjustable both while creating a profile and later.

**Decisions and rejected alternatives:**
- Generic throughout: driver node, feeds and settings come from the ROS graph and the parameter services, so any
  convention-following driver works. Rejected: per-driver lists of node names and topics.
- Remembering stopped publishers by GID instead of waiting until they leave the graph: the lease can take
  seconds; a camera started elsewhere is still refused.
- Special cases, marked in the code: the event camera's images come from `event_camera_renderer`, so its
  settings are the renderer's; the capture camera starts only together with the main camera and has no preview
  of its own; a menu's options are only shown as text, because ROS gives `additional_constraints` no format.
- Changes apply to the running driver only and are not saved in the profile yet.

## 2026-11-07 — Setup wizard: projector step with the connected displays

**What:** A new-profile step "Projector" between Camera image and Intrinsics lists the connected displays as
cards (display id, resolution, refresh rate, position on the desktop, connector, make, model and serial from the
EDID); clicking one stores its id in `NewProfileDraft.projectorDisplayIds` (renamed from the unused
`projectorDisplayNames`). Next stays disabled until a display is chosen. Backend: `displays_api.py`,
`GET /api/displays`.

**Why:** The calibrations that follow project onto the projector, so it has to be known before them.

**Decisions and rejected alternatives:**
- Displays are listed through SDL, because the framework's `display_id` is SDL's display index
  (`surface_selector` lists displays with pygame, the rendering manager counts the same way); another source
  could number the displays differently. SDL is loaded with `ctypes` from the system library pygame also uses,
  so the backend needs no new Python package. Rejected: importing pygame (comes only with the optional
  calibration repo), xrandr or Mutter's D-Bus interface (other numbering, desktop-specific).
- Make, model and serial come from the EDID under `/sys/class/drm`, since SDL names only the connector; this part
  is Linux-specific.
- One projector for now, the draft holds a list for setups with several.

## 2026-11-07 — Setup wizard: wider cursor rays that light up the tabletop

**What:** The brighter rays through the cursor are drawn as a sweep gradient around the lens (6° to each side,
fading to both edges), clipped to the light, and once more on the tabletop, where they hit it brighter.

**Why:** The rays were too narrow, and they did not visibly reach the table.

**Decisions and rejected alternatives:** A sweep gradient is bright by angle, so the rays reach exactly as far as
the light, whatever the window size. Rejected: the blurred wedge, whose length and blur depended on the window
and the renderer.

## 2026-11-07 — Setup wizard: lens (intrinsic) calibration in the app

**What:** Backend `intrinsics_api.py`: `GET /api/intrinsics/camera-state` tells for the previewed camera where its
intrinsics come from (no `camera_info` published, all-zero camera matrix = uncalibrated, the file in the driver's
`camera_info_url` exists, otherwise the camera itself) and whether the driver offers `/camera/set_camera_info`.
`/api/intrinsics/calibration/{start,progress,frame,calibrate,save,stop}` run ROS's `camera_calibration` library
(`MonoCalibrator`) on the preview's frames in a worker thread: coverage of left-right, top-bottom, near-far and
tilt, the number of views, "good enough", the frame with the detected board (rectified once calibrated, with the
remaining line error), calibration in the background, saving through `set_camera_info`. App:
`intrinsics_calibration_view.dart` (state, board form with the measured square size, coverage bars, result with
Save / Discard) in the Intrinsics step; `CameraInstancePreviewPanel` takes a builder for the selected camera's
content instead of a settings switch. Helpers of `camera_preview_api.py` used by both modules are public now.

**Why:** Calibrating a camera needed a terminal (`run_cameracalibrator.sh`) and the user had to know which cameras
need it.

**Decisions and rejected alternatives:**
- Generic need check from `camera_info` and the `camera_info_url` parameter, the conventions every ROS camera
  driver follows, instead of per-driver lists (`FACTORY_INTRINSICS_CAMERA_NAMES`); it needs the camera running,
  so the profile cards keep their file-based check for now.
- The library inside the backend instead of starting `cameracalibrator`: its window would open on the PAR
  machine's screen, outside the app and out of reach from a phone later. The library is the same code, so the
  coverage rules and the result are the same.
- The driver stores the result itself (`set_camera_info`), so the file lands where the driver reads it. A driver
  without that service (e.g. the Azure Kinect's) cannot be calibrated from the app; the app says so.
- The calibration runs in the background, because it can take long with many views of large images; progress
  requests never wait for it.
- The square size has no default: it sets the calibration's scale and must be measured on the print.
- Special cases: only `file://` calibration URLs are resolved; `camera_calibration` is not declared as a
  dependency of anything yet (it was only used by the script), the backend names the install command when it
  is missing.

## 2026-11-07 — Setup wizard: preview start without 500, protected factory calibrations, settings layout

**What:**
- `camera_preview_api.py`: a publisher of `/camera/image_raw` whose node ROS does not know yet (it reports
  `_NODE_NAMESPACE_UNKNOWN_` right after a camera starts) counts as "camera still starting" (503) instead of being
  passed on as a node name; listing a node's topics that fails because the node left meanwhile is a 503 too.
- `launch_helpers.CAMERA_DRIVER_REMAPPINGS['webcam']`: `v4l2_camera` creates `set_camera_info` at the root, like
  the Blackfly driver, so the remap now starts from `/set_camera_info`.
- `par_framework_core/package.xml`: `camera_calibration` declared as an exec dependency.
- `intrinsics_api.py`: starting and saving a calibration are refused (409) for a camera that brings its own
  calibration, one without `camera_info` and one without `set_camera_info`; the app offers no calibration for
  them either.
- App: changeable settings first, read-only ones below "Fixed by the driver"; integer settings with at most 12
  values and `v4l2_camera`'s menus get a dropdown; the settings scroll in an area of their own (as high as a
  feed next to it, a fixed height below it), so the feeds stay in place.

**Why:** The app asked for the feeds right after the start and got a 500 from the half-known node. The webcam's
calibration could not be stored (neither from the app nor with `run_cameracalibrator.sh`, whose
`--no-service-check` hid it). A calibration stored through `set_camera_info` would make a driver use the file
instead of the camera's own calibration from then on, which must never happen by accident.

**Decisions and rejected alternatives:**
- The protection is checked in the backend at start and again right before saving, not only in the app: a phone
  or browser client later must not be able to bypass it.
- Dropdowns for small integer ranges are generic; reading menu labels from `additional_constraints` follows
  `v4l2_camera`'s format and is marked as a special case, other text stays a hint next to a number field.
- Fixed heights for the settings area instead of filling the window: the wizard's steps sit in the stepper's
  scroll view, which gives its content no height to fill.

## 2026-11-07 — Setup wizard: delete profiles

**What:** `DELETE /api/profiles/{name}` (`profiles_api.py`) moves the profile file and its extrinsics folder
(`calibration/extrinsics/<name>/`) into `config/profiles/.deleted/<name>_<date>_<time>/`. The start screen's profile
menu has "Delete <profile> …" for the shown profile, with a confirmation dialog that says where the files go.

**Why:** Profiles could only be removed by hand in the config folder.

**Decisions and rejected alternatives:**
- Moved, not deleted for good: both folders are gitignored, so nothing could be recovered, and measured camera
  poses and projector calibrations take real work to redo. Rejected: deleting the files, deleting only the
  profile file (would leave orphaned extrinsics that a new profile of the same name would silently pick up).
- Lens calibrations stay: they belong to the camera unit, not to the profile.
- Only names of listed profiles are accepted, so a request cannot move other files (e.g. `../x`).

## 2026-11-07 — PAR apps in the ament index; one app on the projector

**What:**
- Apps register in the ament index under the resource type `par_framework_apps`: the marker file's content is the
  app's entry (display name, description, `executable` or `launch_file`, `required_launch_switches`,
  `used_calibrations`). Blueprint and format: `templates/par_app/` (README, entry, `setup.py`, `package.xml`, a
  launch file that also starts a web frontend with `ExecuteProcess`).
- `launch_helpers.get_par_app_package_names()` / `read_par_app_entry()` list and check the entries, used by
  `par.launch.py` and the setup wizard backend alike.
- `par_launch.projector_app` (`none`, `rendering_manager` or a PAR app's package; launch argument
  `projector_app:=`) replaces the booleans `demo_app` and `rendering_manager`; `par_launch.projector_display_id`
  (argument `projector_display_id:=`) replaces the `display_id` of `demo_app_node` and the `rendering_manager`
  section. `par.launch.py` starts the chosen PAR app generically (its executable as a node with `display_id`, or
  its launch file with `params_file`, `profile`, `display_id`) and switches on the nodes it requires. The old
  switches stop the launch with the replacement in the message; the two local profiles using them were changed.
- Backend: `GET /api/apps` (`apps_api.py`) lists the apps that can own the projector; the profile cards take the
  app from `projector_app` and list the nodes the app requires.
- `demo_app` is the first registered app (in its own repo); the rendering manager's README uses the new argument.

**Why:** The wizard is to choose the app of a profile, generically: a new app must show up without a change to the
wizard or core. Two booleans also allowed two apps on one projector, which only logged a warning.

**Decisions and rejected alternatives:**
- The ament index is ROS 2's mechanism for packages announcing resources to tools (used by `rclcpp_components`,
  pluginlib, `rosidl_interfaces`), searchable from Python and C++ without crawling. Rejected: an `<export>` tag in
  `package.xml` (every manifest must be found and parsed), setuptools entry points (Python packages only), a list in
  the wizard or core (a change per app).
- Installed vs. running dependencies: `package.xml` keeps what must be installed; the entry names the shared
  framework nodes that must run, which `par.launch.py` starts once. An app's own launch file starts only what the
  app owns (its nodes, a frontend or backend server), so shared nodes never run twice.
- Unknown keys in an entry are an error, not ignored: a misspelt `required_launch_switches` would otherwise start
  the app without its nodes.
- A required switch wins over `switch:=false` (marked as a simplification).
- One string instead of booleans makes two projector owners impossible to choose. The old keys fail loudly instead
  of being ignored, so a profile does not silently start without its app.
- The rendering manager stays a special case in `par.launch.py` and the backend until it has its own launch file.

## 2026-11-07 — Setup wizard: preview no longer stopped while the camera starts; start screen design

**What:**
- Backend: asking for the feeds (`GET /api/camera-preview/feeds`) now counts as watching the preview, like a frame
  request, so the watchdog keeps a starting camera running.
- App: a feed keeps asking for frames after a failed request (retry every second, error shown until frames come
  back) instead of giving up for good.
- Start screen: no title bar (the window title names the app); the projector light is a pale white instead of
  yellow (`projectorLightColor`); the table has an apron and two front legs down to the window's bottom edge, with
  the connection bar between the legs (`computeTableHeightBelowTabletopLogicalPx` replaces
  `computeTableFrontFaceHeightLogicalPx`).

**Why:** The preview failed often, especially on the calibration step. After a camera restart ROS reports the new
driver node several seconds after the driver runs, during which the app only asks for the feeds. The watchdog,
which stopped a camera after a few seconds without a frame request, could stop it before the app asked for a single
frame. One failed frame request (e.g. a timeout while the machine is busy calibrating) also ended that feed's polling,
after which the watchdog stopped the camera too.

**Decisions and rejected alternatives:**
- Feeding the watchdog from the feeds request, instead of a longer watchdog timeout: the timeout would also keep a
  forgotten camera running longer, and a slower camera would still hit it.
- Only the front legs are drawn: in this view from slightly above the front, the back legs would stand behind the
  tabletop. Apron and legs use a colour between the background and the tabletop, so they stand out against the dark
  background.

## 2026-11-07 — Setup wizard: save camera settings into the profile

**What:**
- Backend: the preview session remembers the profile the camera was started with and which settings were changed
  on its driver. `POST /api/camera-preview/settings/save-to-profile` reads their current values from the driver (in
  the parameter's own type) and writes them with `profiles_api.write_node_settings_into_profile` into
  `config/profiles/<name>.yaml`. `GET /api/camera-preview/settings` also returns `profile_name` and
  `unsaved_setting_names`.
- The writer rewrites the profile with ruamel.yaml's round trip (new dependency in the backend's
  `requirements.txt`): only values that differ from `par_setup.yaml` are kept (a value equal to it removes its key,
  an emptied section is removed), into the section that already names the node (with or without leading `/`), else
  a new section under the node's full name with a "Saved by the setup wizard" comment. Written to a hidden file
  next to it and moved into place in one step.
- App: the settings panel shows how many changes are not saved and a "Save to profile" button; without a saved
  profile (new profile in the wizard) it says the changes apply to the running camera only.

**Why:** Settings changed in the wizard were lost when the camera stopped.

**Decisions and rejected alternatives (decided by Vitus):**
- Rewrite the profile itself. Rejected: a separate wizard file loaded on top of it, which would silently override
  hand edits of the same setting.
- ruamel.yaml instead of PyYAML: PyYAML drops every comment of a rewritten file, and the profiles carry the reasons
  for their values as comments. All existing profiles and `par_setup.yaml` load and dump byte-identical.
- The backend tracks the changed settings and reads their values from the driver, instead of the app sending
  values: the driver's types are exact (`5.0` for a double, which ROS needs in the file), and a value the driver
  refused is never saved.
- Saving is an explicit button, not every change, so trying values does not rewrite the profile each time.

## 2026-11-07 — Setup wizard: Finish creates the profile

**What:**
- Backend: `POST /api/profiles` creates `config/profiles/<name>.yaml` with `par_launch.camera`,
  `par_launch.projector_display_id` and the display name as a comment, with exclusive create (`open(..., 'x')`), so
  an existing profile is never overwritten. It refuses names `profile:=` would reject and a profile without a
  camera. Setting changes made in the wizard are then written into it (`write_node_settings_into_profile`).
- Backend: changes made while a camera runs without a profile are kept per camera and driver node when that camera
  stops (the wizard stops it between steps), and taken by the profile creation for its camera.
  `DELETE /api/camera-preview/new-profile-settings` forgets them; the wizard calls it when it opens. The save
  endpoint uses the values the driver accepted, recorded at the change, instead of reading them again.
- App: Finish creates the profile (button shows "Saving …", errors stay in the wizard), returns its name to the
  start screen, which selects and shows it.

**Why:** Finish closed the wizard without saving anything, so a new profile was lost.

**Decisions and rejected alternatives:**
- Create the file only at Finish, not after the first step: an abandoned wizard would otherwise leave half a
  profile behind.
- Keep the wizard's setting changes in the backend instead of the app: the backend already knows which changes the
  driver accepted, with their exact types, also after the camera stopped. Changes kept for another camera are
  dropped at creation, since the profile does not run that camera.
- Simplification: the profile gets the first camera of the Hardware step, since the framework launches one camera
  at a time.

## 2026-11-08 — Projection calibration on the profile's projector display

**What:**
- `projection_calibration.launch.py` passes `par_launch.projector_display_id` (or `projector_display_id:=<n>` for
  one run) to `projection_calibrator_node` as `display_id`. Without either, the calibrator's own default applies.
- `get_projector_display_id` moved from `par.launch.py` into `launch_helpers`, together with a new
  `create_projector_display_id_launch_argument`, so both launch files read and validate the display the same way.
- `par_setup.yaml`: `projection_calibrator_node.display_id` removed; a comment says where it comes from.

**Why:** the setup wizard stores the projector as `par_launch.projector_display_id`, which the projector app gets,
but the calibrator read its own `display_id`. A profile made in the wizard could show the calibration markers on
another display than the one its app draws on. This is the first step of running the extrinsic calibration from the
wizard.

**Decisions and rejected alternatives:**
- One setting for the projector display instead of one per node: the calibration and the app must use the same
  projector, so two settings can only disagree. Rejected: having the wizard also write
  `projection_calibrator_node.display_id` into the profile (two places to keep in sync, and hand-written profiles
  would still drift).
- No profile set `projection_calibrator_node.display_id`, so removing it overrides nothing silently.
- `surface_selector_node` and `projection_mask`'s debug window still have their own `display_id`; left as they are
  (outside this change).

## 2026-11-08 — Setup wizard: run camera pose and projector calibration from the backend

**What:**
- New `setup_wizard/backend/extrinsics_api.py`:
  - `GET /api/extrinsics/state?profile_name=&camera_name=`: the profile's camera pose (measured or placeholder,
    height, tilt from straight down, the method's quality figures from the file) and projection mapping
    (reprojection error, projector size, projector centre, whether it is older than the pose), the calibration
    kinds the camera offers now, and which packages are missing for them.
  - `POST /api/extrinsics/run/start`: runs `camera_pose_calibration_sheet`, `camera_pose_calibration_kinect` or
    `projection_calibration` (with or without `projector_center:=true`) unchanged, with the profile.
  - `GET /api/extrinsics/run/progress`: running, stored, failed or stopped; for failed and stopped the error lines
    of the launch's output.
- `camera_preview_api.start_camera_preview` split into `start_camera_launch(camera, profile, launch file,
  arguments)`, which the calibration uses too; `read_camera_process_log_lines` made public.
- `profiles_api.create_profile_launch_context` made public (was `_create_profile_launch_context`).

**Why:** first backend part of the extrinsic calibration in the wizard (quick path: the existing per-camera
launches, unchanged in what they measure).

**Decisions and rejected alternatives:**
- A calibration launch runs as the preview's camera process. Each calibration launch starts the camera itself, so
  the app gets its live image, the stop and the watchdog of the preview without new code. Rejected: a second
  process slot next to the preview (two launches would fight over the camera device and the neutral topics).
- Success is a result file newer than the run's start, never the exit code: `ros2 launch` exits with 0 also when
  the node it shuts down for exited with 1. A projector-centre run also needs the centre in that file.
- The result is read from the files the calibrators write; failures show the launch's error lines as they are
  (colour codes removed). Rejected: a status topic from the calibrator nodes (changes both nodes and needs a
  message type), parsing log text (breaks silently when a message is reworded).
- The final result of a run is kept once the launch has ended, because the preview's watchdog later stops the
  ended launch too, which would otherwise make a failed run look stopped.
- The board method is offered to every camera; the depth method only when the previewed camera publishes
  `/camera/depth_registered/image_raw` and a depth pose launch exists for it. That launch starts the Kinect driver
  itself, so it is chosen by camera name in `POSE_DEPTH_LAUNCH_FILE_NAME_BY_CAMERA`, marked as a special case.
- Camera names are checked against `CAMERA_DRIVER_REMAPPINGS` before they become part of a file path.
- Tilt is the angle between the body frame's x axis (its viewing direction, REP 103) and straight down, computed
  from the stored quaternion, so it works for every pose file whichever method wrote it.

## 2026-11-08 — Setup wizard: camera pose and projector calibration screens

**What:**
- `extrinsics_api.dart`: the app's calls to the backend's extrinsics endpoints.
- `extrinsics_calibration_view.dart`: one camera's camera pose or projector calibration in a saved profile. It
  shows what is stored (height, tilt, the method's quality figures; mapping error, projector size, centre, a warning
  when the mapping is older than the pose), the live image, the start controls (board pose with the board's size,
  "Use depth instead" where offered; projector mapping, projector centre where offered), Stop while it runs, and the
  result or the launch's error lines.
- `screens/extrinsics_calibration_step.dart`: the wizard steps "Camera pose" and "Projector calibration", one camera
  after the other (`CameraInstancePreviewPanel`).
- `new_profile_wizard_screen.dart`: six steps. Leaving Intrinsics ("Save profile and continue") creates the
  profile; Finish only closes the wizard. Back into the steps before is closed once the profile exists, and leaving
  the wizard in any way hands the saved profile to the start screen.
- `profile_overview_screen.dart`: for the selected camera, a choice between "Image & settings", "Camera pose" and
  "Projector".

**Why:** the extrinsic calibration (quick path) from the app, in the wizard and as Redo from the Overview.

**Decisions and rejected alternatives:**
- The profile is created before the calibration steps (decided with Vitus), because camera pose and projector
  calibration are stored per profile. Rejected: calibrating only from the Overview, a draft extrinsics folder moved
  at Finish.
- One view for both calibrations and both places (wizard, Overview), so a Redo behaves exactly like the wizard step.
- During a run, the preview widget stays: the run's launch replaces the preview's camera in the backend, so the
  same frame requests show the run's live image. After the run the preview is started again under a new key.
- The state is fetched again every 2 s while no run goes, because the depth method is offered only once the
  previewed camera publishes depth.
- Simplification: Back into the steps before the saved profile is closed, since `POST /api/profiles` only creates.
  Upgrade: update the saved profile from those steps.

## 2026-11-08 — Setup wizard: projector shows black during calibrations that do not need it

**What:**
- Backend `projector_blackout_api.py` (`POST /api/projector-blackout/keep`, `POST /api/projector-blackout/stop`)
  and `projector_blackout_window.py`: a black fullscreen pygame window on the projector's display, in its own
  process. A display that is not connected is reported, not an error. A projector calibration run ends the window
  first (`stop_projector_blackout_for_projection`), since it draws its markers on that display.
- `profiles_api`: the profile summary carries `projector_display_id` (read with `launch_helpers.get_projector_display_id`,
  so it is validated as a launch does).
- App `projector_blackout_api.dart`, `projector_blackout_holder.dart`: holds the blackout while shown and says in one
  line whether the projector is black. Shown in the wizard steps Intrinsics and Camera pose (the draft's projector),
  and in the Overview's Camera pose section (the profile's projector).

**Why:** projector light on the table disturbs calibrations that only use the camera, e.g. glare on the checkerboard
or a bright area that makes the board harder to detect. Asked for by Vitus: every calibration step after the
projector has been chosen that does not need the projector.

**Decisions and rejected alternatives:**
- Not in the Camera image step, which comes before the projector is chosen and may need the projector light to tune
  exposure; not in the projector calibration, which needs the display itself.
- The app asks again every 2 s and a watchdog ends the window 6 s after the last request, like the camera preview,
  so a black projector cannot stay on after the app quits or crashes. Rejected: start on enter and stop on leave
  only (a crashed app would leave the projector black).
- Every request names its holder (one per screen): moving from one step to the next sends the old screen's stop and
  the new screen's keep at about the same time, and a stop arriving late must not end the next screen's blackout.
  A new holder on the same display takes the window over without reopening it.
- A separate process with pygame, as the calibrator's own fullscreen windows: it can be ended at any time without
  touching the backend's SDL state (`displays_api` uses SDL in the backend process). `SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS=0`
  keeps the window up when the user clicks back into the wizard.
- A window that ends by itself is reported with its output and not reopened on every request.

## 2026-11-08 — Sensor processing nodes from the ament index; selection and settings in the setup wizard

**What:**
- `launch_helpers`: resource type `par_framework_sensor_nodes` with `get_sensor_node_package_names`,
  `read_sensor_node_entry` (checks every key, like the PAR app entry) and `add_required_sensor_nodes`; the YAML
  loading of both entry kinds is shared (`_read_ament_index_entry`). `templates/sensor_processing_node_entry.yaml`
  is the blueprint, and `templates/sensor_processing_node.py` points to it.
- `par.launch.py`: the node switches come from the index (`DETECTORS` and the projection mask's own block are gone);
  a selected node's `required_sensor_nodes` start along with it; a `par_launch` switch that is true for a node no
  installed package registers is reported with the fix. The six framework nodes register themselves in their repos.
- Backend `sensor_nodes_api.py`: the installed nodes and the profile's selection (`GET /api/sensor-nodes`,
  `PUT /api/sensor-nodes/selection`, written as `par_launch` switches with the existing profile writer), a run of
  the profile's camera with the selected nodes (`POST /api/sensor-nodes/run/start`, `GET .../run/state`), a node's
  settings (`GET /api/sensor-nodes/settings`), applying them (`POST .../settings/apply`: into the profile, then
  the run starts again), and a node's latest output message as text (`GET .../output-message`).
  `camera_preview_api`: `get_node_parameter_client`, `read_node_settings`, `convert_setting_value` and
  `join_node_name` are public, so both modules use them.
- App: hub area "Sensor nodes" (`screens/sensor_nodes_screen.dart`, `sensor_nodes_api.dart`). The per-setting
  controls moved from `camera_settings_view.dart` into `setting_row_view.dart` (`SettingRowView`), which hands a
  change to its owner: the camera settings send it to the driver at once, the node settings collect it until Apply.
  `CameraFeedImage` (live frames of one topic) is public for the camera image and the nodes' image outputs.

**Why:** Vitus wants to choose a profile's sensor processing nodes after opening it, and adjust their settings.

**Decisions and rejected alternatives** (decided with Vitus, details on the card "Setup Wizard"):
- Nodes register in the ament index, like PAR apps; rejected: a shared list in `launch_helpers`.
- The selection is the profile's `par_launch` switches, which `par.launch.py` already reads; rejected for now: a new
  per-camera mapping format, "available only" without starting.
- None of the nodes applies a parameter change while it runs, so Apply saves into the profile and starts the run
  again. `read_only` parameters are editable there for that reason. Rejected: making every node apply changes live
  first, a settings form without running the nodes.
- Outputs are shown generically from the ROS graph: `sensor_msgs/Image` topics as frames, every other topic as its
  latest message in YAML (`rosidl_runtime_py.message_to_yaml`, long arrays cut), so a third-party node needs no
  code in the wizard. Rejected: drawing each node's results onto the camera image (per-node code).
- A run is `par.launch.py` with the profile and `projector_app:=none rviz:=false capture_camera:=false`, as the
  preview's camera process, so the watchdog and stop work as for a preview.
- Unknown setting names are checked against the node's parameter list first, because ROS fails a whole
  describe request when one name is unknown.
- Simplification: a parameter `par.launch.py` sets itself (e.g. `use_depth` for a depth camera, `debug`) keeps the
  launch's value whatever the profile says.

## 2026-11-08 — Intrinsics per profile, the camera's serial pinned in the profile

**What:**
- `launch_helpers`: `get_intrinsics_folder_path` (the profile's `calibration/intrinsics/<profile>/`, without a
  profile the shared `calibration/intrinsics/`, like the extrinsics) and `get_camera_info_url`, which every camera
  start (Brio, CU40, webcam, Blackfly, capture camera) now uses instead of building the path itself.
  `CAMERA_SERIAL_SOURCE_BY_CAMERA` (node section and serial parameter per driver) and
  `WEBCAM_CAMERA_INFO_FILE_NAME` moved there from the backend, which had a copy marked as a simplification.
- Backend `profiles_api`: a profile's intrinsics state is read from its own folder; deleting a profile moves its
  intrinsics folder into `.deleted/` with the extrinsics. Creating a profile writes the camera's serial into it
  whenever the merged parameters have one, even when it equals `par_setup.yaml`'s
  (`write_node_settings_into_profile(..., always_written_setting_names=...)`).
- Wizard: the new profile is created when leaving the Projector step instead of Intrinsics, and the Intrinsics step
  starts the camera with the profile (`IntrinsicsCalibrationView.profileName`), so the driver stores the
  calibration in the profile's folder.
- Docs and comments naming the intrinsics path (`par.launch.py`, the calibration launch files, `par_setup.yaml`,
  `run_cameracalibrator.sh`, `README.md`, `CLAUDE.md`).

**Why:** Vitus wants every saved intrinsic calibration tied to a profile. Refocusing a camera for one setup changes
its intrinsics; with one file per camera unit, recalibrating for one setup silently replaced the calibration of
every other setup using that unit. The serial is pinned because the profile's intrinsics file is named after it: if
`par_setup.yaml`'s serial changed later, the profile would start another unit with this unit's calibration.

**Decisions and rejected alternatives** (with Vitus):
- `calibration/intrinsics/<profile>/` next to `calibration/extrinsics/<profile>/`, shared folder for launches
  without a profile. Rejected: no fallback (a launch without a profile would always run uncalibrated), one
  `calibration/<profile>/` folder for both (moves every existing extrinsics folder).
- The existing shared files stay where they are and are not copied into the profiles, so existing profiles show
  their intrinsics as missing until recalibrated. Copying a calibration from one profile to another, when the user
  wants it, is a later feature.
- Special case: ROS has no convention for a camera's serial parameter, so the per-driver table
  `CAMERA_SERIAL_SOURCE_BY_CAMERA` stays; a driver without an entry gets no serial written.
- Simplification: the serial comes from the parameter files; a driver started without one opens the first unit it
  finds, whose serial the wizard does not learn yet (choosing the unit in the Hardware step is still open).

## 2026-11-08 — Setup wizard: focus help with sharpness and the enlarged image centre

**What:** backend `focus_api.py` (`GET /api/focus/state`, `POST /api/focus/reset-peak`, `GET /api/focus/center-crop`)
measures the previewed camera's `/camera/image_raw`: variance of the Laplacian in a 240 px square at the image
centre, averaged over the last five frames, with the best value since the preview started or the last reset. Each
frame enters the average once however often the app asks; a new preview starts a new measurement.
`camera_preview_api.convert_image_message_to_frame` (full-size conversion, shared with the preview) is public for
it. App: `focus_api.dart`, `focus_assist_view.dart` (bar with a mark at the best value, "Reset best", the centre
crop enlarged without smoothing), shown below the feeds in `CameraPreviewWithSettingsView`, so in the wizard's
Camera image step and the Overview's "Image & settings"; `CameraPreviewView` frames the measured square on the
camera image.

**Why:** Vitus wants the focus helper (`scripts/focus_preview.py`) in the wizard. Focus comes before the intrinsics,
since refocusing invalidates them.

**Decisions and rejected alternatives:**
- The same measure as `scripts/focus_preview.py`, computed in the backend on the full-resolution frame: the preview
  JPEGs are scaled down and compressed, which removes exactly the fine edges the score measures. Rejected: computing
  it in the app from the preview frames.
- The crop is sent as PNG, not JPEG, so its single-pixel edges are not blurred by compression.
- Score, best mark and enlarged crop (chosen by Vitus); rejected: score and best mark only.
- Simplification: `compute_sharpness` is duplicated (two lines) because the script is a standalone file outside any
  importable package; moving both into a shared module is the upgrade once a third user needs them.

## 2026-11-08 — Setup wizard: choose the app on the projector in a profile's Overview

**What:** `PUT /api/profiles/{name}/projector-app` writes `par_launch.projector_app` into the profile (only `none`
or an installed app from `GET /api/apps` without a broken entry; `none` removes the key, since it is
`par_setup.yaml`'s value). App: `apps_api.dart`, `projector_app_choice_view.dart` at the top of the Overview, one
chip per app plus "None"; an app named in the profile but not installed is shown with a warning.

The profile writer now keeps what follows a section's last key (empty lines, the comment before the next section)
in place when a key is appended to or deleted from the end of a section
(`_add_key_keeping_comment_after_section`, `_delete_key_keeping_comment_after_section`). Before, an appended
`projector_app` landed below the next section's "Saved by the setup wizard" comment, and deleting the last key took
that comment and the empty line with it. A comment on a key's own line still belongs to that key.

**Why:** Vitus wants the app selection stored in the profile; chosen in the Overview only, so new profiles start
with none.

**Decisions and rejected alternatives:** Overview only (Vitus); rejected: an extra wizard step, editing the rendering
manager's page apps as well (both later). The choice is stored at once and the Overview is not reloaded, so a
running camera preview there keeps running.

## 2026-11-08: `run_cameracalibrator.sh` no longer predefines the checkerboard size

**What changed:** the board's inner corners are now the first, required argument
(`run_cameracalibrator.sh 8x6 0.031`), the square size the second. The `BOARD_SIZE` variable and its `8x6` default
are gone. A value that is not `<columns>x<rows>` stops the script with a message showing the right form.

**Why:** the default silently applied to whatever board was printed; a different board then calibrated with the wrong
pattern. The user chooses the board, so the script should not assume one.

**Alternatives considered:** keeping `BOARD_SIZE` but without a default (rejected: an environment variable is easy to
forget and fails later and less clearly than a missing argument); a `--size` option (rejected: cameracalibrator
already has `--size`, and a second one would be added, not replace it).

## 2026-11-08: `projection_calibration.launch.py` detects with fiducials_detector's general settings

**What changed:** the launch file passes a fixed set of detection parameters to `fiducials_detector_node` after the
parameter files (`FIDUCIALS_DETECTOR_GENERAL_DETECTION_PARAMETERS`: no tracking window, threshold windows 3 to 23 px,
4 px per cell, 0.13 margin), so they win over whatever a profile sets for that node.

**Why:** a profile may tune the detector for small, moving printed markers (a tracking window around known markers,
one small threshold window). The calibration looks for large projected markers that lie still and are not known yet,
so with that tuning it found none and ended with "No mapping after 20 s". The values are those of `par_setup.yaml`.

**Alternatives considered:** `ros2 param set` on the running detector (rejected: these parameters are read-only after
start); editing the profile for the calibration run (rejected: easy to forget to restore, and every profile with a
tuned detector would hit the same problem); a launch argument to choose (rejected: nothing needs the tuned values
during calibration).

## 2026-11-09: Setup wizard: lens calibration in an existing profile's Overview

**What changed:** the Overview's section choice for a camera has a fourth segment, "Intrinsics", between
"Image & settings" and "Camera pose". It shows the same `IntrinsicsCalibrationView` as the new-profile wizard, on the
saved profile, so the driver stores the calibration in that profile's intrinsics folder. The projector shows black
during it, as in the wizard.

**Why:** until now the lens of an existing profile could only be calibrated in a terminal
(`camera_only:=true` + `run_cameracalibrator.sh`); a refocused or remounted lens needs this without recreating the
profile.

**Alternatives considered:** a separate screen (rejected: the view already takes a profile name, and the segments
already hold the other per-camera procedures); leaving the projector on (rejected: projected light disturbs board
detection, as in the wizard step).

## 2026-11-09: Setup wizard: start screen mentions the backend connection only when it fails

**What changed:** the bottom bar of the start screen no longer shows "Connected to … (address)" or "Connecting …"; it
holds only the profile menu. When the backend cannot be reached, the middle of the screen shows a plain message
("Cannot reach the PAR machine …") with a "Try again" button instead of the card. The technical reason (address,
exception) goes to the console log only.

**Why:** a working connection is not news for the user, and exception text and start commands mean nothing to someone
at a fresh setup.

**Alternatives considered:** keeping the status in a small icon (rejected: still noise while everything works);
showing the exception behind a "Details" expander (rejected: nobody asked for it, the console log has it).

## 2026-11-09: Setup wizard: Cameras area, app dropdown, adding a camera to a profile

**What changed:**
- The Overview now holds only the app on the projector, as a dropdown (a profile starts one app, so chips that look
  like a multi-choice were misleading). An app with a broken entry is listed but disabled.
- The profile's cameras moved into their own hub area "Cameras", above "Sensor nodes", with the same sections as
  before (Image & settings, Intrinsics, Camera pose, Projector).
- "Add camera" in that area lists the installed camera types the profile does not have yet and adds the chosen one
  (`POST /api/profiles/{name}/cameras`). It is stored as `par_launch.additional_cameras` (a list) in the profile and
  appears next to the first camera, ready to be previewed, set up and calibrated.

**Why:** calibration data is already named per camera (intrinsics by camera and serial, pose and projection mapping by
camera), so a profile can hold the calibration of several cameras before the framework can run them together. The
wizard can therefore prepare a second camera now.

**Decisions and rejected alternatives:** `par.launch.py` ignores `additional_cameras` and starts only
`par_launch.camera` (marked `Simplification:` in the code), so nothing about launching changed. Rejected: waiting for
the multi-camera framework (nothing usable meanwhile), making the added camera the launched one (changes what a
profile starts without being asked). One unit per camera type for now, because files are named by type (and serial);
two units of one type come with camera instances. Removing a camera from a profile is not built yet.

## 2026-11-09: Several units of one camera type per profile, selected camera, removal, Run

**What changed:**
- A profile's cameras are now units: a camera type plus, for types that have serial numbers, the unit's serial. The
  one in `par_launch.camera` (with its serial in the driver's section) is the *selected* camera, the one a run
  starts; the others are `par_launch.additional_cameras`, entries `<camera>` or `<camera>:<serial>`.
- Pose, projection-mapping and projection-corners files get the serial in their name
  (`camera_pose_<camera>_<serial>.yaml`), like the intrinsics already had. `launch_helpers.get_extrinsics_relative_path`
  is the one place that builds them; the calibration launch, the mount transform, the projection server and the
  backend all use it. Files without the serial are still used while the profile has one unit of that type, and when a
  second unit of a type is added, the first unit's old files are renamed to its serial, so nothing is taken over.
- Backend: add a unit (`POST .../cameras`), select (`PUT .../selected-camera`), remove (`DELETE .../cameras`, its
  calibrations moved to `config/profiles/.deleted/`), list connected units (`GET /api/cameras/{camera}/units`, from
  `/dev/v4l/by-id` for the Brio and CU40; other types type the serial), and `run_api.py` (start, state, stop of
  `par.launch.py profile:=<name>` as a subprocess group).
- App: the Cameras area shows chips (click = select, delete icon with a confirmation = remove, "Add camera" with the
  unit choice); sections open on request for the selected camera only. The Overview has Run / Stop.
- Every error text the app shows is a plain sentence now (`describeBackendErrorForUser`); the technical text goes to
  the console. Backend sentences are shown only where they are written for users (add, select, remove camera).

**Why:** the serial alone names the intrinsics file, but the pose, the projection mapping and the driver's serial
setting were per type, so two units of one type would have overwritten each other. Only the selected camera is ever
started, so the driver always opens the unit the profile names and calibrations land in that unit's files.

**Alternatives considered:** instance names (`brio_1`, `brio_2`) everywhere (rejected for now: it is the full
multi-camera framework); previewing any unit by passing its serial per run (rejected: another override path next to
the profile); erasing a removed camera's files (rejected: measured poses take work, the profile deletion already moves
files); types without a serial parameter (webcam, event) stay one per profile. Known limits: the first
unit of a type must have its serial set before a second can be added; the capture camera is unchanged; the Blackfly's
units cannot be listed (typed); settings saved into the profile are per camera type, so two units of one type share
them; the Brio's `/dev/v4l/by-id` name pattern is taken from the driver's matching and was not seen with a real
Brio.

## 2026-11-09: One camera ID names every file of a camera unit; no legacy file names

**What changed:** `launch_helpers.get_camera_id(camera, serial)` is the one definition of a unit's identifier:
`<camera>_<serial>`, or `<camera>` for a camera without serial. The intrinsics file and the camera pose, projection
mapping and projection corners files all end in it. The fallback that let a unit with a serial still read a file
without the serial in its name is gone, and so is the rename on adding a second unit of a type. Files from before are
not read any more: they are renamed by hand (`camera_pose_brio.yaml` of a Brio with serial 123 becomes
`camera_pose_brio_123.yaml`, likewise `projection_mapping_*` and `projection_corners_*`).

**Why:** with the fallback, two names could mean one camera, and which unit owned an old file depended on how many units
of the type the profile had at that moment. One name per unit is unambiguous, also on other machines.

**Alternatives considered:** keeping the fallback (rejected: the ambiguity stays); user-chosen camera names
independent of type and serial (rejected for now: names would run through launch files, transform frames and parameter
sections, which is the full camera-instance model); a migration script or an automatic rename (rejected: the
framework is in alpha, so old names get no code at all; a one-time rename by hand is cheaper than carrying a
compatibility path).

## 2026-11-09: Kinect and RealSense units have serials too

**What changed:** `CAMERA_SERIAL_SOURCE_BY_CAMERA` now lists the Azure Kinect (`sensor_sn` under
`k4a_ros_device_node`) and the RealSense (`serial_no` under `/camera/realsense`), so several units of these types can
be in one profile, with their pose and projection files named by the unit's ID. The Kinect's depth pose launch
(`camera_pose_calibration_kinect.launch.py`) took its file name `camera_pose_kinect.yaml` literally; it now uses the
same ID-based name as every other camera. The serial of these two is typed in the wizard (no listing yet).

**Why:** the first version of the unit support listed only the cameras that already had a serial in the framework,
and called the others serial-less, although both drivers take one. The device was only missing from the list.

**Alternatives considered:** listing connected units through the Kinect SDK / RealSense library (rejected for now:
needs the vendor libraries in the backend, typing the serial is enough). Not checked: whether the event camera's driver
takes a serial; the webcam's driver (`v4l2_camera`) has none, so it stays one per profile.

## 2026-11-09: Alpha rule: no code for old names; webcam intrinsics name from the camera ID

**What changed:** the constant `WEBCAM_CAMERA_INFO_FILE_NAME` is gone: the webcam's intrinsics file is
`camera_info_<camera id>.yaml` like every other camera's (`get_camera_info_file_name_of_unit('webcam', '')`, which is
`camera_info_webcam.yaml`, so no file changes).

**Why:** the framework is in alpha: no extra cases or fallbacks for old implementations, a generic rule first even if it
breaks old code (ROS 2 conventions always apply). A second name for something the ID rule already produces is such a
case.

## 2026-11-09: Alpha rule: no check for the old app switches; profile cards list sensor nodes from the index

**What changed:** `par.launch.py` no longer refuses the former `demo_app` / `rendering_manager` switches
(`REPLACED_APP_SWITCH_NAMES` and its check in `get_projector_app_name` are gone); a leftover switch is now ignored
like any other key that is not a launch switch. The setup wizard's profile cards (`profiles_api._read_profile_summary`)
list as sensor nodes the switched-on names that the ament index registers as sensor processing nodes
(`get_sensor_node_package_names`), instead of every switched-on name minus the hand-kept `HIDDEN_LAUNCH_SWITCH_NAMES`.

**Why:** alpha rule: no code that exists only for old names, and one generic mechanism instead of hand-kept lists. The
check only served migration; no parameter file still uses the old switches. The card now uses the same source as the
Sensor nodes area and `par.launch.py`, so a new switch (`rviz`-like) never shows up as a sensor node by mistake, and
`projection_mask`, which registers as a sensor node, is listed like the others.

**Alternatives considered:** keeping the check as a helpful error (rejected: the rule forbids code for old names; a
profile still carrying the old key loses nothing but the hint); keeping the hidden list and adding the index (rejected:
two sources of truth). Known effect: a switched-on node that is not installed no longer appears on the card;
`par.launch.py` still logs which repo to add when it starts.

Renamed in the same pass, no behaviour change: `OTHER_LAUNCH_SWITCHES` → `NON_SENSOR_NODE_LAUNCH_SWITCH_NAMES`
(`par.launch.py`), `DEPTH_CAMERAS` → `DEPTH_CAMERA_NAMES` (`projection_calibration.launch.py`, README),
`switched_on_names` → `switched_on_launch_switch_names` (`profiles_api.py`), so each name says what it holds.

## 2026-11-09: Setup wizard: one page per topic and camera; projector found by its identity

**What changed (new-profile wizard):** every step that works per camera has one page per camera, and the camera
image has two pages per camera, Focus (preview, focus help, only the focus settings) and Image settings (preview, the
other settings). The camera selector inside the steps (`CameraInstancePreviewPanel`) is no longer used. Each page shows
its topic and camera ("Focus: brio_1", "Camera 1 of 2"), and Next names the page that follows ("Next: Image settings:
brio_1", "Save profile, next: Intrinsics: brio_1"). The shell (`new_profile_wizard_screen.dart`) builds the list of
pages from the draft (`WizardPage`, `WizardPageTopic`); the stepper still shows the six steps. `CameraSettingsView` and
`CameraPreviewWithSettingsView` take a title, a filter of shown settings and whether the focus help is shown.

**Why:** with several cameras, one screen showed a camera selector, the feeds, every setting and the focus help at
once, so it was unclear what to do and when a camera was done. One topic per page gives a clear order (focus before
the other settings, because focus changes invalidate intrinsics). The pages of one step share their layout, so the
camera preview keeps running from Focus to Image settings instead of restarting.

**Special case:** ROS has no convention that marks a parameter as the lens focus, so the Focus page recognises focus
settings by name (`isFocusSettingName`: the name contains "focus", as in `v4l2_camera`'s `focus_absolute`). A driver
naming it otherwise shows its focus on the Image settings page.

**What changed (projector):** a profile now stores the projector's identity next to `par_launch.projector_display_id`:
`projector_manufacturer_id`, `projector_model_name`, `projector_serial_text` (from the EDID) and
`projector_connector_name`. The display detection moved from the wizard backend into
`par_framework_core/connected_displays.py` (no ROS imports), shared by the backend and the launch files.
`launch_helpers.get_projector_display_id` finds the display with the stored identity (EDID values first, the
connector only to tell identical projectors apart, or alone when the display reports no EDID) and uses its current
index; `projector_display_id:=` still wins for one run; without a stored identity the stored index is used as before.
Not connected or ambiguous raises an error naming the fix. `par.launch.py` looks the projector up only when an app
draws on it, so camera-only runs work with the projector off. The wizard backend stores the identity when a profile is
created and through `PUT /api/profiles/{name}/projector-display`; the profile summary reports the state
(`connected`, `moved`, `not_connected`, `ambiguous`, `unidentified`, `displays_unreadable`, `not_set`). The Overview
has a Projector section with a warning when the saved number no longer points to the projector, "Save display N"
when it moved, and the display cards to choose it again (`projector_display_status_view.dart`,
`projector_display_choice_view.dart`, shared with the wizard's Projector step).

**Why:** SDL numbers displays in their current order, so plugging a monitor in or out changes the projector's number
and an app would open fullscreen on the wrong display. The identity does not change with the order, so resolving it
at every launch fixes the cause instead of only warning about it; the warning and re-selection cover what launching
cannot fix (projector off, two identical projectors, profiles without an identity).

**Alternatives considered:** only warning and re-selecting in the wizard (rejected by Vitus: launches started from the
terminal would still use the wrong display); matching by connector first (rejected: the connector changes when the
cable moves to another port, the EDID does not); the identity as a nested `projector_identity:` mapping (rejected: the
wizard's profile writer writes flat keys); camera by camera through all steps (rejected by Vitus: the projector would
be chosen after the intrinsics, so it could not show black during them).

## 2026-11-09: Setup wizard: Run as a floating action button in every area of a profile

**What changed:** Run / Stop (`ProfileRunView`) is an extended floating action button in the bottom right corner of
the profile hub's `Scaffold`, so every area (Overview, Cameras, Sensor nodes, Store, Running) shows it; the Run
section of the Overview is gone. The button reads "Run", "Stop", or "Stop <profile>" while another profile runs, and
shows a progress circle while a start or stop is on its way. What was text below the old button (a run that stopped by
itself, a failed start or stop, an unreachable backend) is a snack bar, shown once when it happens. The scrolling areas
leave `runButtonClearanceLogicalPx` free below their content, so the button never covers their end.

**Why:** Vitus wants Run where a primary action is expected in Material design and reachable from every area, e.g.
right after a calibration in the Cameras area, without going back to the Overview.

**Alternatives considered:** the button in the Overview only (rejected by Vitus); a Run button in the app bar
(rejected: less visible, and the app bar already holds the profile name).

## 2026-11-09: Setup wizard: Running area removed from the hub for now

**What changed:** the profile hub's navigation rail no longer has the "Running" area, and its placeholder
(`screens/running_apps_screen.dart`) is deleted.

**Why:** Vitus' choice: the area was an empty placeholder, and Run / Stop now sits in every area as a floating button.
The placeholder file was deleted as well (Vitus): an unused file only suggests a feature that does not exist; the
sketch on the card "Setup Wizard" keeps what the area should show when it comes back.

**Alternatives considered:** keeping the placeholder file unused (rejected by Vitus).

## 2026-11-09: Setup wizard: the setup seen from the front in the Overview

**What changed:** the Overview starts with a drawing of the profile's setup seen from the front
(`setup_side_view.dart`): the table, the projector with the light it throws onto the table, and every camera unit
with its viewing direction and, where its intrinsics are known, its field of view; heights are labelled. Up is the
height above the table; left to right follows the projected image's rows, since people read the projected image
upright from its bottom edge (`front_view_right_direction` in the answer). Without a projection mapping the selected
camera's image rows stand in, else world x. Both directions use the same scale. Measured poses are solid, placeholder poses
dashed in the error colour; notes below say what is left out (no intrinsics file, projector centre not measured, no
projector calibration). The data comes from a new backend endpoint, `GET /api/profiles/{name}/setup-geometry`
(`setup_geometry_api.py`): per camera unit its position, where its optical axis meets the table and its field of view
on the table (the image border's rays through `par_geometry.pixels_to_table`), and from the selected camera's
projection mapping the projection area (`projector_to_table` of the projector image corners) and the projector
centre, all in metres in world. `profiles_api._read_camera_units` became `read_camera_units`, since the new module
uses it.

**Why:** Vitus wants the Overview to show the setup as it is, like the RViz view but simplified and flat; the front
view is the first part (mockup on the card "Setup Wizard"). The backend returns the outlines on the table rather than
side-view lines, so the top view can be drawn from the same answer later.

**Simplification:** the camera's optical frame is taken as the REP 103 rotation of its body frame
(`BODY_TO_OPTICAL_ROTATION`, what `create_optical_frame_tf_publisher` publishes). Drivers that publish their own
frames with a small mount tilt are drawn without it. Upgrade: read the transform from TF while the camera runs.

**Alternatives considered:** computing the geometry in the app (rejected: the files live on the PAR machine, and
`par_geometry` is the one place for this math); reading TF from a running framework (rejected for now: the Overview
must also work while nothing runs); drawing a nominal field of view for cameras without intrinsics (rejected: it
would look measured although it is a guess).

**Front direction (same day):** the first version drew world x as left to right, which in the measured profiles is the
projected image's short side, so the drawing showed the setup from the side. World's axes come from the pose
calibration and carry no meaning for where people stand; the projected image does. Rejected: a fixed world axis per
profile set by the user (one more setting to get wrong), world y (only right by chance for these setups).

## 2026-11-09: Setup wizard: cameras and projector look different in the front view and can be clicked

**What changed:** in the Overview's drawing a camera is a body with a lens barrel pointing along its view, the
projector a wide housing with vents and its lens at the optical centre, where its light starts. Hovering a device
rings it and shows the hand cursor; clicking a camera opens the Cameras area with that unit selected and its images
and settings open (`CamerasScreen.requestedCameraUnit`, set by the hub); clicking the projector scrolls to the
Overview's Projector section and opens its display cards (`ProjectorDisplayStatusView.displayChoiceOpenRequestCount`).
The drawing's layout (scale, device positions, label positions) moved into `_SideViewLayout`, which the painter and
the hover and click handling share, so they always agree on what is where. Camera labels move down until they cover
neither another label nor an icon. The backend's camera geometry also carries `camera_type` and `serial`, to select
the unit.

**Why:** Vitus wants cameras and projector told apart at a glance, and the drawing as the way into each device's
settings.

**Alternatives considered:** Material icons drawn into the canvas (rejected: there is no projector icon, and a camera
icon cannot turn along its view); a dialog with the device's settings over the Overview (rejected: the camera's
settings need its running preview, which the Cameras area already manages, one camera at a time); opening a camera
without selecting it (not possible: only the selected camera is ever started, so the driver opens the unit the profile
names).

**Projector drawn like the start screen's (same day):** the front view's projector is the start screen's projector
(grey body with vents, lens barrel pointing down, pale lens glass), at 0.4 of its size, with its light starting from
both edges of the lens glass in the start screen's lamp colour (`projectorLightColor`). Its drawing moved out of
`_ProjectorBackgroundPainter` into the top-level `paintDownwardProjector(canvas, lensExitPoint, scale)` in
`projector_background.dart`, which both call, so the two cannot drift apart. Rejected: a second copy of the shape in
`setup_side_view.dart` (two places to change for one look).

## 2026-11-10: Setup wizard: missing calibration steps in the Overview, a Projectors area

**What changed:** the Overview lists what the profile still misses under "Calibration": per camera the lens
calibration (intrinsics `missing`) and the camera pose (`placeholder` or `invalid`), then for the selected camera the
projector calibration (no projection mapping) and, optional, the projector's position (mapping without projector
centre). A step that can run has a Calibrate button that opens the Cameras area with that unit selected and the
matching section open (`CamerasScreen.requestedCameraSection`, a `CameraSectionRequest` of camera type, serial and
`CameraSection`, passed through the hub; a click on a camera in the drawing uses the same path with the images and
settings section). A step that cannot run says what it needs: the projector position needs a depth camera, the
capture camera cannot be opened on its own. The drawing lost its title, legend and explanation notes; the files it
had to leave out are still shown, in the error colour, below the steps. The Overview now loads the setup geometry
once and hands it to `SetupSideView`, which no longer fetches it, so drawing and steps read the same state. The
projector's display choice moved from the Overview into a new hub area, Projectors (`projectors_screen.dart`), above
Cameras; clicking the projector in the drawing opens it with the display cards open.

**Why:** Vitus wants every missing calibration reachable from the profile's first page, and the drawing without the
text around it. The projector gets its own area like the cameras.

**Alternatives considered:** running the calibration views inline on the Overview (rejected by Vitus: the Cameras area
already manages the one running camera, its blackout and section switching); hiding steps that cannot run (rejected
by Vitus: the user would not learn what is missing, e.g. the projector position in a profile without a depth
camera); deciding that projector-position step from the camera type (rejected: whether a camera delivers depth is
known only while it runs, and a list of depth camera names is a special case; marked as `Simplification:`); keeping
the projector section on the Overview as well (rejected by Vitus).

## 2026-11-10: Setup wizard: one shared loader for a profile's summary

**What changed:** `SetupWizardBackendClient.fetchProfileSummary(profileName)` returns one profile's summary and
throws `ProfileUnavailableException` (with a sentence for the user) when the profile no longer exists or its files
cannot be read; `describeBackendErrorForUser` returns that sentence. The Overview, Projectors and Cameras areas call
it instead of each fetching the list, searching it and building the same two error texts.

**Why:** three copies of the same lookup and error texts would drift apart; one change now covers all hub areas.

**Alternatives considered:** a backend endpoint for one profile (rejected for now: one more route to keep in step with
the list, and the list request is cheap); a shared widget that also owns the loading state and the error view
(proposed separately, a larger change).

## 2026-11-10: Setup wizard cleanup: state enums, one camera-section widget, shared loading and process stop

**What changed:**
- `CameraCalibrationSummary.intrinsicsState` and `poseState` are enums (`IntrinsicsCalibrationState`,
  `CameraPoseState`, each with `fromBackendName`, like `ProjectorDisplayState`) instead of strings. The start
  screen's tooltip switches over them exhaustively.
- `camera_section_view.dart` holds `CameraSection`, `CameraSectionRequest` and `CameraSectionView`: one camera
  section (images and settings, lens calibration, camera pose, projector calibration) with the rule which of them run
  under a black projector. The Cameras area and the new-profile pages Intrinsics, Camera pose and Projector
  calibration use it instead of each wiring `ProjectorBlackoutHolder` and the calibration view themselves. The section
  content is keyed by section inside the widget, so the blackout stays on when switching between the lens calibration
  and the camera pose. The new-profile Intrinsics page now also says so when the profile has no name yet, like the
  Camera pose page.
- `profile_summary_loading.dart`: the mixin `ProfileSummaryLoading` holds the loading flag, error text and summary
  of a hub area, `loadProfileSummary`, `getShownProfileSummary` and the spinner or error-with-retry view. Overview,
  Projectors and Cameras use it.
- Backend: `process_groups.stop_process_group(process, stop_signals, timeout_per_signal_s)` replaces the three copies
  of "signal the process group, wait, try the next signal" in `run_api`, `camera_preview_api` and
  `projector_blackout_api`; `LAUNCH_STOP_SIGNALS` is the Ctrl+C-first order for launches.

**Why:** each rule lived in two or three places that had to be changed together; a typo in a state string failed a
comparison silently.

**Alternatives considered:** a builder widget for the profile loading (rejected: the Cameras area acts after the first
load, selecting the requested camera, which a builder makes awkward; a `State` mixin keeps each area's flow, as
Flutter's own `TickerProviderStateMixin` does); merging the two new-profile calibration pages into one file
(not done: each keeps its own introduction, and the shared part is now one widget call); a shared module for the two
three-line `_read_yaml_file` helpers in `extrinsics_api` and `setup_geometry_api` (rejected: a module for three lines
costs more than the copy, and importing one API module from the other would pull in ROS for the geometry).
Unknown state names from the backend now raise a `FormatException` instead of showing the raw name; backend and app
ship together, as for `ProjectorDisplayState`.

## 2026-11-10: Setup wizard: no start screen; the hub opens the last used profile

**What changed:** the start screen (`screens/start_screen.dart`, a profile card on a decorative table) is gone. The
app starts in the hub (`ProfileHubScreen`, now `home` in `main.dart`), which loads the profile list itself and shows
the last used profile, else the first. The profile menu (switch, New profile, Delete) became `ProfileSelectorView` at
the top of the Overview; the hub owns the shown profile, remembers a switch through `setLastSelectedProfile`, runs the
new-profile wizard and asks before deleting. Switching profiles builds the areas and the Run button afresh (keyed by
profile name). Without any profile the Overview shows only the selector with a hint, the other rail entries are
disabled and there is no Run button. When the profile list cannot be loaded (e.g. the backend does not answer), the
hub shows the reason with Try again instead of the areas. A profile that cannot be read still shows the selector, so
the user can switch away from it.

**Why:** Vitus no longer wants the first page; the profile is switched rarely, so the work starts on its Overview.

**Alternatives considered:** the selector in the app bar of every area (rejected: Vitus asked for it on the Overview;
the app bar keeps the profile name); a separate empty screen for "no profile" (rejected: the hub with disabled areas
keeps one layout for every state).

**Unused code removed (same day):** with the start screen gone, its decorative background went too: the
`ProjectorBackground` widget with its light-cone painters and `tabletop_shape.dart`. The projector's shape
(`paintDownwardProjector`) and `projectorLightColor`, which the setup drawing uses, moved to `projector_drawing.dart`.
Also removed from the backend client: `CameraCalibrationLevel` / `getCalibrationLevel` (the start card's camera
icons) and `fetchBackendStatus` / `SetupWizardBackendStatus` (the hub detects an unreachable backend from the profile
list request). The backend's `GET /api/status` stays. Rejected: keeping the background for later (git history has it).

## 2026-11-10: Setup wizard: profile menu in the app bar, Apps area

**What changed:** the profile selector (`ProfileSelectorView`) is a menu button with a hamburger icon in the top right
corner of the hub's app bar instead of a button at the top of the Overview; its menu is unchanged (switch, New
profile, Delete). The app bar reads "Profile: <name>" ("Profile: none yet" without profiles). The projector app choice
(`ProjectorAppChoiceView`) moved from the Overview into a new rail area "Apps" (`screens/apps_screen.dart`), between
Sensor nodes and Store; the Overview now holds only the setup drawing and the missing calibration steps. Without a
profile, Apps is disabled like the other areas and the Overview's hint points to the menu at the top right.

**Why:** Vitus wants the profile choice reachable from every area, and the Overview about the setup only.

**Alternatives considered:** a navigation drawer opened by the hamburger icon (rejected: three entries plus the
profile list fit a dropdown menu, and a drawer would cover the rail); placing Apps after Store (rejected: the
installed app choice belongs before the store of apps not yet installed).

## 2026-11-10: Setup wizard: Run menu, app settings in the Apps area, no debug banner

**What changed:**
- **Run is a menu:** pressing Run (`ProfileRunView`) reads the installed apps and the profile's app and opens a menu
  above the button: "No app" and every installed app, the profile's app checked, a broken entry disabled. A pick is
  stored as `par_launch.projector_app` (when it changed) and the profile starts; while it runs, the button stops it.
  The hub then rebuilds the shown area, so the Apps area shows the new choice.
- **App settings:** the app's ament index entry may list `settings_node_names` (full node names, checked by
  `launch_helpers.read_par_app_entry`; documented in `templates/par_app/`, set for `demo_app`). The Apps area keeps
  the app choice and lists every installed app below it; "Edit settings" starts the profile with that app on the
  projector (`apps_api.py`: `POST /api/apps/settings-run/start`, `GET .../settings-run/state`,
  `GET /api/apps/settings`, `POST /api/apps/settings/apply`), shows each settings node's parameters, and Apply writes
  the changes into the profile under the node's full name and starts the app again. Node names from the network
  must be listed in the app's entry.
- **Shared with the sensor nodes:** the settings form (`node_settings_editor_view.dart`, used by both areas),
  checking and converting values for a running node (`camera_preview_api.convert_settings_of_running_node`) and
  reading a profile's `par_launch` section (`profiles_api.read_profile_launch_section`).
- **Store** placeholder now describes the plan: a portal for new camera nodes, sensor nodes and apps.
- `debugShowCheckedModeBanner: false` in `main.dart`.

**Why:** Vitus wants the app chosen where it is started, every installed app's settings in one place, and the Store
for installing.

**Alternatives considered:**
- *Run menu:* run the picked app for this run only (`projector_app:=` override) instead of storing it (rejected by
  Vitus: a terminal launch of the profile should run the same app).
- *App settings, finding the app's nodes:* detecting them at runtime by comparing the ROS graph with and without the
  app (rejected by Vitus: two starts per look, and late or shared nodes would be misattributed).
- *App settings, scope:* only listing apps for now and building the settings later (rejected by Vitus).
- *Settings form:* a copy of the sensor node card's form (rejected: two copies of the same load, retry and apply
  logic would drift apart).

## 2026-11-10: Setup wizard: tabs for sensor nodes and apps, settings read once

**What changed:**
- **Settings read once** (`setup_wizard/backend/node_settings_api.py`): a sensor node's or app's settings are read
  by starting its nodes alone with `par_setup.yaml` (sensor node: `ros2 run <pkg> <pkg>` named `<pkg>_node`, as
  `par.launch.py` names it; app: its entry's executable or launch file), reading their parameters through the
  parameter services, stopping them and caching the result in `~/.cache/par_setup_wizard/node_settings/` until the
  package's `package.xml` is installed again (or "Read again"). Shown values are the profile's where it sets them,
  else the cached ones; Save converts to the cached types and writes into the profile without any run
  (`GET /api/node-settings`, `POST /api/node-settings/save`, `POST /api/node-settings/refresh`). A read is refused
  while this backend runs a profile, preview or calibration, or while a node of the same name is in the ROS graph.
  The live settings endpoints of sensor nodes and the app settings run are gone.
- **Profile's app list:** `par_launch.apps` (default `[]` in `par_setup.yaml`), set with
  `PUT /api/profiles/{name}/apps`; the projector app must be one of them (`projector-app` refuses others, removing an
  app resets `projector_app` to none). `ProfileSummary.enabled_app_names`. The Run menu offers only these.
- **Tabs** (`addable_tabs_view.dart`): Sensor nodes and Apps show one tab per enabled node or app with "Add …" and
  Disable. A tab's content is built when first shown and kept, so unsaved changes survive switching tabs.
  Sensor node tabs keep "Try it" (camera with the enabled nodes, this node's outputs; saving restarts it); the Apps
  area has no projector app choice any more.
- `NodeSettingsEditorView` saves without a restart and offers "Read again".

**Why:** Vitus asked whether starting an app is needed to edit its settings. Reading is (ROS 2 nodes declare
parameters only at runtime, no file lists them), but only once; storing never was.

**Alternatives considered:**
- *Settings source:* keep the live run for editing (rejected by Vitus); read `par_setup.yaml` only (rejected: no
  types, ranges or descriptions, and parameters missing there would not be editable).
- *Detecting a running node before a read:* only through the ROS graph (rejected after a test: a backend started a
  moment ago has not discovered the graph yet and started a second node of the same name next to a running one).
- *Apps tabs:* one per installed app without enabling (rejected by Vitus in favour of the profile's app list).
- *Tab content:* Flutter's `TabBarView` (rejected: it disposes hidden tabs, losing unsaved changes).

**Removed (same day, Vitus' OK):** `projector_app_choice_view.dart`, unused once the Run menu chooses the projector
app.

## 2026-11-10: Setup wizard: projector list and mode warning, Run only on the Overview, Debug node, slow nodes

**What changed:**
- **Settings read of a slow node:** a node is in the ROS graph as soon as it exists but answers parameter requests
  only once it spins; `demo_app` first opens its fullscreen window (at least 3 s) and failed the 2 s request with
  the preview's text "The camera driver did not answer in time", which read like a missing camera. The read now asks
  again until its overall deadline (`_read_settings_once_answering` in `node_settings_api.py`) and names the node
  when it really does not answer.
- **Projector display mode stored:** choosing the projector also stores `projector_width_px`,
  `projector_height_px` and `projector_refresh_rate_hz` (`connected_displays.get_projector_display_mode`, written next
  to the identity). The profile summary compares them with the display the projector is found on
  (`stored_display_mode_text`, `current_display_mode_text`, `is_display_mode_changed`).
- **Projectors page:** always lists the connected displays with the projector's display selected; warnings for
  not connected, display id changed, several matching displays, no stored identity, and changed display mode, with
  "Save display N as it is now" for a changed id or mode. The same warnings (`getProjectorWarningTexts`) head the
  Overview, with "Open Projectors".
- **Run** floats only over the Overview. **Sensor nodes** get their own floating "Debug node" button instead of
  "Try it": it starts the camera with the enabled nodes; the tab in front shows the camera image and its node's
  outputs.

**Why:** Vitus saw adding an app fail and suspected the missing camera; the log showed the app's own start time.
He wants the projector page as a plain list with the choice remembered and checked, and Run only where the profile
is overviewed.

**Alternatives considered:** starting the camera and the framework to read an app's settings (rejected: the app
would still open its window before answering, and the read would need a camera); a longer single request timeout
(rejected: no fixed time fits every node, the overall deadline already exists); comparing only the resolution
(rejected: a changed refresh rate also changes what the projector shows); a warning banner in every area (rejected
for now: the Overview and the Projectors area are where the projector is looked at).

## 2026-11-10: Setup wizard: one scroll bar per screen

**What changed:** the camera settings next to or below the feeds (`CameraPreviewWithSettingsView`, Cameras area and
the new-profile camera pages) no longer sit in a fixed-height scroll area with their own scroll bar
(`_ScrollingSettingsArea` removed); they take the height they need and scroll with the page. A sensor node's latest
output message (Debug node) likewise shows at its full height instead of in a 200 px scroll box.

**Why:** Vitus wants never more than one scroll bar on one screen.

**Alternatives considered:** keeping the inner area so the feeds stay in view while going through a long settings
list (rejected: a second scroll bar, and scrolling depends on where the mouse is); a sticky camera image beside the
settings (not done: more layout code for a case Vitus did not ask for; possible later).

## 2026-11-10: Setup wizard: quieter Projectors page, compact settings rows

**What changed:**
- **Projectors page:** no heading and no "… is display 2" line; the selected card says it. Text appears only for a
  problem (no projector chosen, the warnings). Every display card shows the same rows, an unreported detail as "–",
  each one line high with the name cut to one line (full name as tooltip), so all cards have the same size. The
  hint "Which display is the projector? Click its card." moved into the new-profile wizard's Projector page.
- **Settings rows** (`setting_row_view.dart`, used by camera, sensor node and app settings): no type names; a text
  field accepts only what the setting's type allows while typing (`typedTextPatternByTypeName`), and a wrong entry
  says what is expected in words ("a whole number"); the value is written out only where no control shows it
  (read-only settings, next to a slider); name and control share one line from 560 px row width, below that the
  control goes under the name.

**Why:** Vitus wants the selection itself to carry the information, text only for problems, and settings without
technical noise in as few lines as the window allows.

**Alternatives considered:** equal card heights through a fixed card height (rejected: a fixed height clips with a
larger font); rejecting a wrong text only on Enter (rejected: Vitus wants the input to allow only the allowed
type); keeping the value text next to text fields and dropdowns (rejected: it repeats what the control shows).

## 2026-11-10: Setup wizard: Blackfly intrinsics, settings without Enter, Reset to default

**What changed:**
- **Blackfly intrinsics:** the Intrinsics tab said the Blackfly uses the calibration from the camera and refused a
  calibration. The backend looked for the calibration file only under the driver parameter `camera_info_url`, but
  `spinnaker_camera_driver` calls it `camerainfo_url`; finding no file behind a calibrated camera matrix, it took
  the calibration for the camera's own. It now asks the framework which file it gives the camera at launch
  (`profiles_api.get_camera_intrinsics_file_path`, the same rules the profile summary uses, now shared through
  `_get_camera_intrinsics_file_name`) and falls back to `camera_info_url` only for cameras the framework gives none.
- **Typing in settings:** no "Press Enter" hint; a valid entry is passed on half a second after the last keystroke
  (`typedValueReportDelay`), an unfinished one (e.g. only "-") waits and is named when the field is left. The text
  field keeps its own controller and focus, so the owner's updates do not reset the cursor while typing.
- **Reset to default:** a reset button next to a setting while its value differs from the default. Camera
  settings: the default is `par_setup.yaml`'s value for the driver (set on the running driver; "Save to profile"
  then removes the override); settings `par_setup.yaml` does not list get no button. Sensor node and app settings:
  the value read without a profile; resetting removes the profile's key on Save (`null` in
  `POST /api/node-settings/save`). `CameraSetting.has_default_value` / `default_value` carry it.

**Why:** Vitus calibrates the Blackfly himself; only the Azure Kinect brings its own calibration. Entering values
should not need an extra key, and a changed value should be easy to undo.

**Alternatives considered:** reading `camerainfo_url` as a second parameter name (rejected: a special case per
driver spelling, while the framework knows the file for every camera it starts); passing each keystroke on at once
(rejected: a camera driver would reconfigure for every digit typed); one "Reset all" per page (not done: per
setting undoes one change without losing the others).

## 2026-11-10: Setup wizard: auto-save, top-aligned pages, area bar below the app bar

**What changed:**
- **Auto-save** (`NodeSettingsEditorView`): every change of a sensor node or app setting (switch, dropdown, slider
  release, reset, a valid typed entry after the typing pause) is saved into the profile at once; Save, Discard and
  the pending count are gone, a failed save shows under its setting.
- **Top-aligned pages:** a spinner, error or note that stands alone on a page sits at its top left
  (`top_aligned_page_content.dart`) instead of in the middle (profile loading, hub errors, Sensor nodes, Apps,
  Store).
- **Area bar:** the areas (Overview, Projectors, Cameras, Sensor nodes, Apps, Store) are a `NavigationBar` in the app
  bar's `bottom` instead of a navigation rail on the left; without a profile only Overview is enabled.

**Why:** Vitus wants changes kept without an extra click, page content where reading starts, and the full window
width for the areas.

**Alternatives considered:** a `TabBar` for the areas (rejected: it needs a controller kept in step with the areas
opened from code and has no disabled tabs); saving only when leaving a tab (rejected: a change could be lost when
the window closes).

## 2026-11-10: Setup wizard: undrawn devices listed, camera tabs, debug windows, smaller fixes

**What changed:**
- **Overview:** the drawing shows only cameras with a measured pose (`getDrawnCameras` in `setup_side_view.dart`);
  the dashed placeholder cameras and the "selected" label are gone. Below it, "Not in the drawing yet" lists each
  camera and the projector that is missing there with what it still needs and, where it can run, a Calibrate button;
  "Calibration" keeps the steps that do not decide about the drawing (lens calibrations). Without anything measured,
  the drawing is left out.
- **Cameras:** one tab per camera (`AddableTabsView`, as for sensor nodes and apps) instead of chips, the title and
  its helper text. The tab in front is the profile's main camera: bringing another tab to the front stores it
  (`PUT …/selected-camera`). Tabs are ordered by name, so they stay in place when the main camera changes. Remove sits
  in the tab; the main camera first hands its role to another camera. `AddableTabsView` got `onAddPressed` (a dialog
  instead of the menu) and `onShownTabChanged`, and follows a changed `shownTabTitle`.
- **Projectors:** "Refresh" instead of "Search again"; the page content takes the full width.
- **Settings rows** (`setting_row_view.dart`): the name is right-aligned when it shares the line with its control,
  and rows have more room between them.
- **Debug node** (`sensor_nodes_api.py`): the run passes `debug:=true` to `par.launch.py`, so every enabled node with
  a `debug` parameter opens its preview window.
- **Apps:** the hint that reading the settings starts the app shows only while they are read
  (`NodeSettingsEditorView`).

**Why:** a placeholder pose says nothing about where a camera is, so drawing it suggests a position nobody
measured; the list says what is missing instead. A scroll view shrinks to narrow content when its parent does not
fix its width, which put the scroll bar in the middle of the page. A name far left of its control is hard to match
to it in a wide window.

**Alternatives considered:** keeping the dashed placeholders and listing them as well (rejected by Vitus: the
drawing should show measured positions only); camera tabs that only show, with a "Use this camera" button (rejected
by Vitus: the wizard starts only the main camera, so every tab would need the extra click); debug only for the node
in front through a new launch argument (rejected by Vitus in favour of the existing `debug:=true` for all enabled
nodes).

## 2026-11-10: Setup wizard: RViz as an app that runs alongside, clearer names

**What changed:**
- **RViz in the Apps area:** `GET /api/apps` lists RViz (when `rviz2` and `rviz_bridge` are installed) with the new
  field `uses_projector: false`. Adding it under Apps stores `par_launch.rviz: true`, the switch `par.launch.py`
  already starts RViz by; it is not written into `par_launch.apps`, is left out of the Run menu's choice of the app
  on the projector, and `PUT …/projector-app` refuses it. Its tab shows the description and Disable, no settings.
- **Names:** `CameraSetting` is `NodeSetting` (backend and app), since it describes any node's parameter; a
  camera's `is_selected` / `isSelected` is `is_main_camera` / `isMainCamera` (JSON field included); the sensor nodes
  screen's `_selectedPackageNames` is `_enabledPackageNames`; `profiles_api._suffix` is `_create_serial_suffix`.
- The run's error text and the remove-camera error no longer say "selected camera".

**Why:** RViz is the tool for looking at a setup while its app runs, so it has to start next to the projector app,
not instead of it. `par.launch.py` needs no change, because the switch exists. The names said less than the things
they hold, or used a word the interface no longer shows.

**Alternatives considered:** RViz as a choice in the Run menu like a projector app (rejected by Vitus: RViz and a
projector app could then never run together); an ament index entry type for desktop tools (not built: RViz is the
only one, so it stays a marked special case in `apps_api.py`).

## 2026-11-10: Camera unit chosen in the new-profile wizard, `camera_serial:=`, remaining renames

**What changed:**
- **`camera_serial:=<serial>`** (`launch_helpers.py`, declared in `par.launch.py`): names the unit of `camera:=` to
  open for one run. `get_camera_serial` returns it before the serial in the parameter files, so the unit's
  intrinsics and extrinsics file names follow, and `create_camera_serial_override_parameters` hands it to the
  driver (Brio, CU40, Blackfly, Kinect, RealSense) as text.
- **New-profile wizard:** adding a camera of a type with serial numbers in the Hardware step asks for the connected
  unit (`AddCameraDialog`, opened for one type). `CameraInstanceDraft.serial` goes to the previews before the
  profile exists (`POST /api/camera-preview/start`, field `serial`) and into the new profile
  (`POST /api/profiles`, field `camera_serial`).
- **Blackfly units are listed** (`cameras_api.py`): from the USB devices of the vendor under
  `/sys/bus/usb/devices`, whose serial text is the serial number in hexadecimal.
- **Names:** `ProjectorApp…` is `InstalledApp…` (the list holds RViz too; JSON field `installed_apps`); storing the
  main camera is `set_main_camera` / `setProfileMainCamera` on the route `/main-camera`.

**Why:** the preview of a profile that is not saved yet starts with `par_setup.yaml` alone, which names no unit.
A driver that opens nothing without a serial then shows no image, and a driver that opens the first unit it finds
may show the wrong one when two are connected. The unit has to be known before the first preview, and the profile
has to store the same one.

**Alternatives considered:** opening the first connected unit when no serial is set (rejected by Vitus: with two
units of a type the wizard could not say which one); a serial in `par_setup.yaml` (rejected: it is a value of one
setup, not a default); a temporary profile file for the preview (rejected: a launch argument is the ROS way to
override one value for one run and leaves no file behind); listing Blackflys through the Spinnaker SDK (rejected:
needs its Python bindings, a new dependency, while USB already reports the serial).

## 2026-11-10: framework nodes take relative camera stream names (multi-camera step 1)

**What changed:** `launch_helpers` has `CAMERA_STREAM_NAMES` (the streams a camera may offer, named relative to its
namespace by the image_pipeline convention), `CAMERA_NAMESPACE` (`/camera`) and `create_camera_stream_remappings()`.
Every framework node that `par.launch.py`, `calibration.launch.py`, `projection_calibration.launch.py` and the two
camera pose launch files start gets these remappings, PAR apps as well (executable apps on their node, launch-file
apps through `SetRemap` in a `GroupAction` around the include), and the rendering manager bridge. `rviz_bridge` and
`templates/sensor_processing_node.py` use relative names now. The node repos changed their absolute names to
relative ones in the same step.

**Why:** step 1 of the multi-camera plan: nodes use relative names (ROS 2 convention), so that later each node can
run in its camera's namespace (`/cameras/<name>/`) without remapping. While there is one camera in `/camera` and the
nodes run in the root namespace, their relative camera stream names would resolve to `/image_raw` etc., so the
launch files point them at `/camera/...`; all other relative names (`fiducials`, `pages`, `projection_mapping`, ...)
resolve to the same root names as before. Checked with a real start (Blackfly, fiducials_detector, page_locator,
projection calibration server): the same topics and services as before, frames arriving.

**Alternatives considered:** starting every node in `/camera` right away (would also move their outputs, e.g.
`/fiducials` to `/camera/fiducials`, before the apps can follow); keeping absolute names and remapping per run
(not the ROS 2 convention, a remap per topic and node).

## 2026-11-10: camera registry, cameras in /cameras/<camera> (multi-camera step 2)

**What changed:** camera types register in the ament index (resource type `par_framework_cameras`), like PAR apps
and sensor nodes. An entry names the package and launch file that start the driver, the body frame, the streams the
camera offers and where its intrinsics come from (`templates/par_camera/` is the blueprint, checked by
`launch_helpers.read_camera_entry`). Core ships entries and launch files for the drivers it does not own:
`camera_webcam`, `camera_blackfly`, `camera_realsense`, `camera_kinect`, `camera_event` (`launch/camera_*.launch.py`).
`launch_helpers.create_camera_actions` includes a type's launch file with the arguments `namespace`, `camera_name`,
`serial`, `camera_info_url`, `params_files`, and adds the mount transform `world -> <camera>_<body_frame>`. Every
camera runs in `/cameras/<camera>` (the camera's name is its type until profiles name their cameras), with its
frames named after it (the Kinect's through `tf_prefix`: `kinect_camera_base`, ...). Removed:
`CAMERA_DRIVER_REMAPPINGS`, the `DEFAULT_TOPIC_NAME_*` constants, `create_camera_nodes` and the per-type `create_*`
functions, `create_camera_serial_override_parameters`, `CAMERA_DETECTOR_PARAMETER_OVERRIDES`, `DEPTH_CAMERA_NAMES`,
`get_camera_base_frame_id`. The detector options `use_depth` and `use_compressed` now follow from the camera's
streams (`DETECTOR_PARAMETER_BY_CAMERA_STREAM`). The driver sections in `par_setup.yaml` are single-level
wildcards (`/cameras/*/blackfly`, ...); a profile sets one camera under `/cameras/<camera>/<driver node>`. RViz
gets its camera topics remapped onto the running camera. `run_cameracalibrator.sh` needs `CAMERA_NAMESPACE`.

**Why:** step 2 of the multi-camera plan. A new camera type needs no change in core, and every camera gets its own
namespace and frames, which several cameras need. The framework nodes stay in the root namespace for now, with their
camera streams remapped onto `/cameras/<camera>/...`, so their outputs (`/fiducials`, `/pages`, ...) keep their
names until apps can follow them (later steps). `/cameras/*/` matches exactly one namespace level, checked with a
parameter test: type defaults reach every camera in `/cameras/` but not the capture camera (`/capture_camera/...`).
Checked with a real start: Blackfly (detectors read `/cameras/blackfly/image_raw`, `/fiducials` arrives with
`blackfly_optical_frame`, TF from `world` reaches it, the unit's intrinsics and pose files are used) and webcam
(camera only); Kinect, RealSense and event camera were started without hardware, and their drivers came up with the
expected namespace and remappings.

**Alternatives considered:** a data-only entry (package, executable, remappings) with core building the node
(every driver quirk would need a new field and code in core); the wildcard `/**/<node>` (would also reach the
capture camera's driver, which must not get the main camera's image size and exposure); starting the framework
nodes in the camera's namespace now (would move their outputs before the apps can follow).

## 2026-11-10: Brio and CU40 sections as camera type defaults (multi-camera step 3)

**What changed:** `par_setup.yaml` keys the Brio's and the CU40's driver sections as `/cameras/*/logitech_brio_node`
and `/cameras/*/see3cam_cu40_node`, like the other camera types. Their entries and launch files live in their own
repos (`logitech_brio`, `see3cam_cu40`), which now register the camera types `brio` and `cu40`.

**Why:** step 3 of the multi-camera plan: the drivers the framework owns ship their own camera entry, and their
nodes run in `/cameras/<camera>`, where these sections reach them. Checked: both start through `par.launch.py
camera:=brio|cu40` in their namespace with these defaults and their unit's intrinsics URL (no camera connected, so
the nodes stopped after opening; frames and streams not seen yet).

**Alternatives considered:** core shipping the entries for its own drivers too (against the rule that a package
useful outside the framework brings its own registration).

## 2026-11-10: cameras named in the profile, every camera started (multi-camera step 4)

**What changed:** `par_launch.cameras` maps each camera's name to its unit, `'<type>'` or `'<type>:<serial>'`, e.g.
`{overhead: 'blackfly:22260470', capture: 'blackfly:25290614'}` (`launch_helpers.read_profile_cameras`, checked
with messages naming the fix; the last parameter file that sets it sets all cameras, so a profile's list replaces
`par_setup.yaml`'s default `{kinect: kinect}` instead of being merged with it). `par.launch.py` starts every camera
in `/cameras/<name>`; the framework nodes, the projection calibration server and RViz use the first one (the main
camera). `camera:=` starts one camera: a name of the list, or `<type>[:<serial>]` for a unit no profile names
(named after its type). The calibration launch files measure one camera (`get_camera_to_calibrate`, `camera:=`
among several); the depth pose launch works for any camera offering `depth_registered/image_raw`. Extrinsics
files and placeholder poses are per camera name (`camera_pose_<name>.yaml`, `/<name>_tf_publisher`), intrinsics stay
per unit (`camera_info_<type>_<serial>.yaml`). Removed: `par_launch.camera`, `additional_cameras`, `capture_camera`
(refused with a message), `camera_serial:=`, `CAMERA_SERIAL_SOURCE_BY_CAMERA` (the serial goes to the camera's
launch file, which alone knows the driver's parameter name), `create_capture_camera_node` and its section. Every
Blackfly uses `config/blackfly_s_software_trigger.yaml` (the driver's mapping plus a software trigger), so a camera
in trigger mode is an ordinary camera whose own section switches the trigger on (example in `par_setup.yaml`).

**Why:** step 4 of the multi-camera plan, with cameras named by role as ROS 2 robots name their sensors: a
replaced unit keeps its name, topics, pose and projection mapping; only its intrinsics belong to the unit. Starting
every camera already here (planned for a later step) keeps the capture camera working once its special case is
gone. Checked with a scratch profile and both Blackflys: two namespaces, two TF chains, separate `set_camera_info`
services, the detectors on the main camera, and one frame per software trigger on the second camera (0 Hz between
triggers, the main camera at its full rate); the camera choice and the error messages with a few profiles.

**Alternatives considered:** a list of `'<name>=<type>:<serial>'` texts (replaced as a whole by ROS's merge, but
harder to read and write); no default camera in `par_setup.yaml` (a launch without profile would need `camera:=`);
a fallback from `/<name>_tf_publisher` to the type's placeholder (a camera without its own pose would silently
share another's); the capture camera's own mapping file chosen per camera (needs the launch file to read the
parameter files; the trigger mapping is harmless for freely running cameras).
