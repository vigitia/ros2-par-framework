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
