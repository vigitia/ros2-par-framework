<!-- Written by Claude Code -->
# par_framework_core

Launch files (`par.launch.py` and its parts) and `config/par_setup.yaml` of the PAR framework. No nodes, no camera
types.

`par.launch.py` and the setup wizard know no camera driver, app or sensor node by name: each registers itself in the
**ament index** with an **entry**, a YAML mapping that is the content of its marker file. ROS 2 finds installed
things this way: below `<prefix>/share/ament_index/resource_index/`, one folder per resource type, in it one marker
file per package ([design](https://github.com/ament/ament_cmake/blob/master/ament_cmake_core/doc/resource_index.md)).
ROS uses the same mechanism for `packages`, `rclcpp_components` and pluginlib's plugins.

| Resource type | Registered by | Entry checked by |
|---|---|---|
| `par_framework_cameras` | a camera type (file name = type) | `camera_types.read_camera_entry` |
| `par_framework_apps` | a PAR app (file name = package) | `par_apps.read_par_app_entry` |
| `par_framework_sensor_nodes` | a sensor processing node (file name = package) | `sensor_nodes.read_sensor_node_entry` |

Every key is checked; an unknown key (e.g. a typo) fails at start with a message naming the fix, so a node is never
silently left out. A Python package installs its entry with one line in `setup.py`'s `data_files`, e.g.

```python
('share/ament_index/resource_index/par_framework_cameras',
    ['resource/par_framework_cameras/<type>']),
```

a C++ (`ament_cmake`) package with
`ament_index_register_resource(par_framework_cameras CONTENT_FILE resource/par_framework_cameras/<type>)`.

```bash
ament_index par_framework_cameras             # every installed camera type
ament_index par_framework_cameras blackfly    # its entry
```

Rejected: an `<export>` tag in `package.xml` (every manifest would have to be found and parsed); setuptools entry
points (Python packages only); a list in the framework or the wizard (every new package would need a change there).

## Camera types

A camera type is an entry plus a launch file that starts the driver. A driver written for the framework ships both
in its own repo (`logitech_brio`, `see3cam_cu40`); for a third-party driver, `packages/par_camera_adapters/` ships
them (e.g. `resource/par_framework_cameras/webcam` and `launch/camera_webcam.launch.py` there).

For a camera of this type that a profile names `<camera>` (`par_launch.cameras: {<camera>: '<type>:<serial>'}`;
`camera:=<type>[:<serial>]` names it after its type), core:

1. reads the entry;
2. includes the launch file with `namespace:=/cameras/<camera>`, `camera_name:=<camera>`, `serial`,
   `camera_info_url` (for `intrinsics: calibratable`) and `params_files` (`launch_helpers.CAMERA_LAUNCH_ARGUMENT_NAMES`;
   all but the first two may be empty);
3. publishes the mount transform `world -> <camera>_<body_frame>` (measured pose or placeholder);
4. runs the sensor nodes the profile lists for the camera in its namespace, where their relative stream names
   (`image_raw`, `camera_info`, ...) resolve to `/cameras/<camera>/...`, and sets detector options from `streams`
   (e.g. `use_depth` when the camera offers `depth_registered/image_raw`).

**The launch file's job:**

- Start the driver in `namespace`, so that every topic and service ends up below it.
- Map the driver's own names onto the stream names listed in the entry: drivers often publish below their node name
  (`<namespace>/<node>/image_raw`) or create a service at the root (`/set_camera_info`).
- Name every TF frame after `camera_name` (`<camera>_link`, `<camera>_optical_frame`), through the driver's frame
  parameter or TF prefix. ROS 2 cannot remap frame names: a driver with fixed frame names can only run once per
  setup, or needs a fork.
- Pass `serial` and `camera_info_url` under the driver's own parameter names, and `serial` as text (launch would
  read a serial of digits as a number).
- Import nothing from `par_framework_core`, so the driver's repo builds without the framework.

| Key | Meaning |
|---|---|
| `display_name`, `description` | shown in the setup wizard |
| `package`, `launch_file` | the launch file is `share/<package>/launch/<launch_file>` |
| `body_frame` | the mount transform's child is `<camera>_<body_frame>`, e.g. `link` |
| `streams` | what the camera offers below its namespace, from `camera_types.CAMERA_STREAM_NAMES` |
| `intrinsics` | `calibratable` (a file per unit, written through `set_camera_info` by `scripts/run_cameracalibrator.sh`, passed as `camera_info_url`), `factory` (the driver publishes its own) or `none` (no `camera_info`) |
| `required_packages` (optional) | ROS packages the launch file starts besides `package`, e.g. a released driver for an entry in `par_camera_adapters`; the type counts as installed when all of them are |
| `parameters_file` (optional) | the type's default parameter file, relative to `share/<package>/`, e.g. `config/realsense.yaml`; loaded before `par_setup.yaml` and the profile, which override it. For third-party drivers; a driver written for the framework sets its defaults in its code |
| `serial` (optional) | `none` (default: one unit per setup), `typed` (the launch file passes `serial`) or `listed` (also listed in the setup wizard, needs one lookup below) |
| `v4l_by_id_prefix` | `listed` UVC camera: units are `/dev/v4l/by-id/<prefix>_<serial>-video-index0` |
| `usb_vendor_id`, `usb_serial_base` | `listed` USB camera: units are the USB devices of this vendor (`'1e10'`, as `lsusb` shows it), their serial text read in base 10 (default) or 16 |
| `usb_product_id` (optional, with `usb_vendor_id`) | only the USB devices of this product (`'097c'`), for a vendor with other USB devices or a camera that shows up as several USB devices |

Rejected: data only in the entry (package, executable, remappings, serial parameter name) and core building the
node, because every driver quirk (a fixed node name, two processes, a settings mapping file) would need a new field
and new code in core; a launch file is ordinary code and ROS 2 drivers usually ship one already.

## PAR apps

An app registers its entry so that `par.launch.py` can start it and the setup wizard lists it. What the app needs
*installed* goes into `package.xml` (`<exec_depend>`); what must *run* next to it goes into
`required_launch_switches`.

| Key | Required | Meaning |
|---|---|---|
| `display_name` | yes | shown in the setup wizard |
| `description` | yes | one sentence on what the app shows on the surface |
| `executable` | one of the two | a `console_scripts` entry point, started as one node |
| `launch_file` | one of the two | a file in `share/<package>/launch/`, for an app with more processes |
| `required_launch_switches` | no | framework nodes that must run next to the app (`par_launch` switches, e.g. `fiducials_detector`, `page_locator`) |
| `inputs` | no | the cameras the app reads, each with its topic names below the camera's namespace, e.g. `{camera: [pages, camera_info, projection_mapping]}` |
| `used_calibrations` | no | `camera_intrinsics`, `camera_pose`, `projection_mapping`, `projector_center` |
| `settings_node_names` | no | full names of the app's nodes whose parameters the setup wizard edits, e.g. `/example_app_node` |

**Shared nodes.** `par.launch.py` switches the `required_launch_switches` on for the app and starts each once, so
two apps never run a detector twice. An app never starts them itself.

**Inputs.** Every camera runs in `/cameras/<camera>/`, and so do the sensor nodes on it (`/cameras/overhead/pages`).
The app runs in the root namespace and subscribes to relative names; `par.launch.py` remaps them onto the camera the
profile binds to the input (`par_launch.app_inputs: {example_app: {camera: overhead}}`, set in the wizard's Apps
area; an unbound input reads the only camera of the run). An app with one input subscribes to the plain names
(`pages`), an app with several prefixes each name with its input (`tracking/pages`, `capture/image_raw`). The
required sensor nodes run on every camera the app reads.

**Calibrations don't block.** The app starts without the calibrations it uses; the wizard shows which ones are
missing. The app must work uncalibrated (camera pixels), like every framework node.

**Settings.** The setup wizard's Apps area edits the parameters of the nodes in `settings_node_names`. It reads
them once: it starts the app alone with its own defaults (no profile, no camera), reads names, descriptors and
values through the standard ROS 2 parameter services, stops the app and caches the result until the package is
installed again. Saving writes what differs from those defaults into the profile under the node's full name. So
declare every setting with a `ParameterDescriptor` (description, range, `read_only` where a change needs a
restart), read the values when the node starts, and let the app start without a camera image.

**How it is started.** A profile chooses the one app that owns the projector (`par_launch.projector_app`, plus
`projector_display_id`, the SDL/pygame display number), or one run does: `projector_app:=<package>`.

- `executable`: started as a node with `par_setup.yaml` and the profile as parameter files, plus `display_id` and
  `debug` when given. It keeps the node name it gives itself, which its sections in the parameter files use.
- `launch_file`: included with the arguments `params_file`, `profile` and `display_id`, which the launch file
  declares. It starts everything the app owns, also processes that are no ROS nodes (a web frontend, a backend
  server) through `ExecuteProcess`, so they start with the launch and stop on Ctrl+C. A frontend is built before
  and installed with the package, so starting needs no build tool.

Apps that draw on the projector declare a parameter `display_id` and open their fullscreen window there.

## Sensor processing nodes

Detectors, `page_locator`, `projection_mask` and the like. Convention: the package name is the `par_launch` key that
lists the cameras the node runs on (e.g. `example_detector: [overhead]`), its `console_scripts` entry point has the
same name, and `par.launch.py` starts it as `<package>_node` in each listed camera's namespace
(`/cameras/<camera>/<package>_node`), where its relative topic names resolve to that camera's streams. Its
settings: defaults under `/cameras/*/<package>_node` in a parameter file, per camera under
`/cameras/<camera>/<package>_node`.

| Key | Meaning |
|---|---|
| `display_name`, `description` | shown in the setup wizard |
| `required_sensor_nodes` | other sensor nodes whose output this node reads; started along with it on the same camera and selected with it in the wizard. `[]` when the node reads only the camera |
