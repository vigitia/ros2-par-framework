<!-- Written by Claude Code -->
# Blueprint: a camera type

How a camera driver becomes a camera type of the framework, so that `par.launch.py` can start it (`camera:=<type>`)
without knowing the driver. Copy the files into the driver's repo, replace `example_camera`, and add the
`setup.py` lines below. For a third-party driver the framework cannot change, core ships the entry and the launch
file instead (e.g. `blackfly`, `kinect` in `packages/par-framework-core/`).

| File | What it does |
|---|---|
| `resource/par_framework_cameras/example_camera` | the camera type's **entry**: name, launch file, body frame, streams, intrinsics |
| `launch/example_camera.launch.py` | starts the driver in the camera's namespace and maps its names onto the framework's |

`COLCON_IGNORE` keeps this folder out of a `colcon build` in the repo root; don't copy it.

## What the framework does with it

For a camera of this type with the name `<camera>` (the type itself, until profiles name their cameras), core:

1. reads the entry (`launch_helpers.read_camera_entry`, which checks every key and fails with a message naming the
   fix);
2. includes the launch file with `namespace:=/cameras/<camera>`, `camera_name:=<camera>`, `serial`,
   `camera_info_url` (for `intrinsics: calibratable`) and `params_files`;
3. publishes the mount transform `world -> <camera>_<body_frame>` (measured pose or placeholder);
4. points every framework node's relative stream names (`image_raw`, `camera_info`, ...) at `/cameras/<camera>/...`,
   and sets detector options from `streams` (e.g. `use_depth` when the camera offers `depth_registered/image_raw`).

## The launch file's job

- Start the driver in `namespace`, so that every topic and service ends up below it.
- Map the driver's own names onto the stream names listed in the entry: drivers often publish below their node name
  (`<namespace>/<node>/image_raw`) or create a service at the root (`/set_camera_info`).
- Name every TF frame after `camera_name` (`<camera>_link`, `<camera>_optical_frame`), through the driver's frame
  parameter or TF prefix. ROS 2 cannot remap frame names: a driver with fixed frame names can only run once per
  setup, or needs a fork.
- Pass `serial` and `camera_info_url` under the driver's own parameter names.
- Import nothing from `par_framework_core`, so the driver's repo builds without the framework.

## setup.py

```python
data_files=[
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    # The camera type's entry in the framework's camera list
    ('share/ament_index/resource_index/par_framework_cameras',
        ['resource/par_framework_cameras/example_camera']),
    ('share/' + package_name, ['package.xml']),
    ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
],
```

A C++ (`ament_cmake`) package registers the same way with
`ament_index_register_resource(par_framework_cameras CONTENT_FILE resource/par_framework_cameras/<type>)`.

```bash
ament_index par_framework_cameras             # every installed camera type
ament_index par_framework_cameras blackfly    # its entry
```

## The entry

| Key | Meaning |
|---|---|
| `display_name`, `description` | shown in the setup wizard |
| `package`, `launch_file` | the launch file is `share/<package>/launch/<launch_file>` |
| `body_frame` | the mount transform's child is `<camera>_<body_frame>` |
| `streams` | what the camera offers below its namespace, from `launch_helpers.CAMERA_STREAM_NAMES` |
| `intrinsics` | `calibratable`, `factory` or `none` |

Rejected: data only in the entry (package, executable, remappings, serial parameter name) and core building the
node, because every driver quirk (a fixed node name, two processes, a settings mapping file) would need a new field
and new code in core; a launch file is ordinary code and ROS 2 drivers usually ship one already.
