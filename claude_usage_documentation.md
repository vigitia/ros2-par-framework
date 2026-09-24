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
