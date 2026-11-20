<!-- Written by Claude Code -->
# Blueprint: a PAR app

How an app becomes known to the framework, so that `par.launch.py` can start it and the setup wizard lists it,
without either of them knowing the app. Copy the files into the app's repo and replace `example_app`.

| File | What it does |
|---|---|
| `resource/par_framework_apps/example_app` | the app's **entry**: name, description, how it starts, what it needs |
| `resource/example_app` | the empty marker every ROS package installs (registers it as a package) |
| `setup.py` | installs the entry into the ament index, plus `launch/` and a built frontend |
| `package.xml` | what the app needs **installed** |
| `launch/example_app.launch.py` | only for an app with more than one process: starts everything the app owns |

`COLCON_IGNORE` keeps this folder out of a `colcon build` in the repo root; don't copy it.

## The ament index

ROS 2 finds installed things through the ament index: below `<prefix>/share/ament_index/resource_index/`, one
folder per resource type, and in it one marker file per package, named like the package. Its content may be
anything ([design](https://github.com/ament/ament_cmake/blob/master/ament_cmake_core/doc/resource_index.md)). ROS
uses it for its own lists: `packages` (every installed package), `rclcpp_components`, pluginlib's plugins for
RViz, rqt and image_transport, `rosidl_interfaces`.

PAR apps register under the type **`par_framework_apps`**, with their entry as the content. Anything can then list
them without crawling folders or parsing manifests:

```bash
ament_index par_framework_apps             # every installed PAR app
ament_index par_framework_apps demo_app    # its entry
```

```python
from par_framework_core.launch_helpers import get_par_app_package_names, read_par_app_entry
```

`read_par_app_entry` checks every key and fails with a message naming the fix, also for unknown keys, so a typo
doesn't silently leave a required node off. A C++ (`ament_cmake`) app registers the same way with
`ament_index_register_resource(par_framework_apps CONTENT_FILE resource/par_framework_apps/<pkg>)`.

Rejected: an `<export>` tag in `package.xml` (every manifest would have to be found and parsed); setuptools entry
points (how `ros2cli` finds its verbs, but only for Python packages); a list of apps in the framework or the wizard
(every new app would need a change there).

## The entry

| Key | Required | Meaning |
|---|---|---|
| `display_name` | yes | shown in the setup wizard |
| `description` | yes | one sentence on what the app shows on the table |
| `executable` | one of the two | a `console_scripts` entry point, started as one node |
| `launch_file` | one of the two | a file in `share/<pkg>/launch/`, for an app with more processes |
| `required_launch_switches` | no | framework nodes that must run next to the app (`par_launch` switches) |
| `inputs` | no | the cameras the app reads, each with its topic names below the camera's namespace |
| `used_calibrations` | no | `camera_intrinsics`, `camera_pose`, `projection_mapping`, `projector_center` |
| `settings_node_names` | no | full names of the app's nodes whose parameters the setup wizard edits, e.g. `/example_app_node` |

**Installed vs. running.** What the app needs *installed* goes into `package.xml` (`<exec_depend>`), where rosdep
and the app store read it. What must *run* next to it goes into `required_launch_switches`: shared framework nodes
such as `fiducials_detector` and `page_locator`. `par.launch.py` switches them on for the app and starts each once,
so two apps never run a detector twice. An app never starts them itself.

**Inputs.** Every camera runs in `/cameras/<camera>/`, and so do the sensor nodes on it (`/cameras/overhead/pages`).
The app runs in the root namespace and subscribes to relative names; `par.launch.py` remaps them onto the camera the
profile binds to the input (`par_launch.app_inputs: {example_app: {camera: overhead}}`, set in the wizard's Apps
area; an unbound input reads the only camera of the run). An app with one input subscribes to the plain names
(`pages`), an app with several prefixes each name with its input (`tracking/pages`, `capture/image_raw`). The
required sensor nodes run on every camera the app reads.

**Calibrations don't block.** The app starts without the calibrations it uses; the wizard shows which ones are
missing. The app must work uncalibrated (camera pixels), like every framework node.

**Settings.** The setup wizard's Apps area edits the parameters of the nodes in `settings_node_names`. It reads
them once: it starts the app alone with `par_setup.yaml` (no profile, no camera), reads names, descriptors and
values through the standard ROS 2 parameter services, stops the app and caches the result until the package is
installed again. Saving writes what differs from `par_setup.yaml` into the profile under the node's full name; the
app reads it at its next start. So declare every setting with a `ParameterDescriptor` (description, range,
`read_only` where a change needs a restart), read the values when the node starts, and let the app start without a
camera image (it is started this way for a few seconds; a window it opens shows meanwhile).

## How it is started

A profile chooses the one app that owns the projector:

```yaml
par_launch:
  ros__parameters:
    projector_app: example_app      # none or a PAR app's package
    projector_display_id: 1         # SDL/pygame display number, 0 = primary
```

or for one run: `ros2 launch par_framework_core par.launch.py projector_app:=example_app`.

- **`executable`:** `par.launch.py` starts it as a node with `par_setup.yaml` and the profile as parameter files,
  plus `display_id` (from `projector_display_id`) and `debug` when given. It sets no node name: the node keeps the
  one it gives itself, which its sections in the parameter files use.
- **`launch_file`:** `par.launch.py` includes it with the arguments `params_file`, `profile` and `display_id`, which
  the launch file declares (see `launch/example_app.launch.py`).

**An app starts everything it owns in its launch file**, also processes that are no ROS nodes, such as a web
frontend or a backend server: `ExecuteProcess` ties them to the launch, so they start with it and stop on Ctrl+C.
A frontend is built before (`npm run build`) and installed with the package, so starting needs no build tool.

**Apps that draw on the projector** declare a parameter `display_id` (SDL/pygame display number) and open their
fullscreen window there.

## Later

- `exclusive`: whether the app draws on the projector itself (like `demo_app`) or as a client of the rendering
  manager, so that several apps can run at once (card "Setup Wizard", "App store and launcher").
