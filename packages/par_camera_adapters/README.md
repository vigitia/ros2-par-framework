<!-- Written by Claude Code -->
# par_camera_adapters

Camera types of the PAR framework for **third-party ROS 2 camera drivers**, which cannot register themselves with
the framework. Each type is an entry in the ament index (`resource/par_framework_cameras/<type>`) plus a launch file
(`launch/camera_<type>.launch.py`) that starts the driver in the camera's namespace and maps its names onto the
framework's. Format and rules: `packages/par-framework-core/README.md`. Drivers we maintain ourselves ship their entry in
their own repo instead (`logitech_brio`, `see3cam_cu40`).

| Camera type | Driver | Launch file |
|---|---|---|
| `webcam` | `v4l2_camera`, any UVC camera | `camera_webcam.launch.py` |
| `realsense` | `realsense2_camera`, e.g. the D435 | `camera_realsense.launch.py` |
| `kinect` | `azure_kinect_ros_driver`, from source (`config/catalog_repos.list`), with the Azure Kinect SDK installed by hand | `camera_kinect.launch.py` |
| `blackfly` | `spinnaker_camera_driver`, FLIR Blackfly S | `camera_blackfly.launch.py` |
| `event` | `metavision_driver` + `event_camera_renderer`, OpenEB event cameras | `camera_event.launch.py` |

A type counts as installed when the packages its entry names under `required_packages` are. The drivers are not
declared in `package.xml`, so rosdep installs only the ones an installation chose: released drivers in
`config/installed_ros_packages.list`, drivers from source in `config/installed_repos.list` (both written by the setup
wizard).

```bash
ament_index par_framework_cameras             # every installed camera type
ament_index par_framework_cameras blackfly    # its entry
```

## Event camera (`event`)

An event camera reports brightness changes per pixel instead of frames. A camera of type `event`
(`cameras: {event: event}`, or `camera:=event`) starts like the other cameras, through the released
`metavision_driver` (OpenEB) as `/cameras/<name>/event`, with its settings under `/cameras/*/event` in
`config/event.yaml`. Next to it, `event_camera_renderer` (`/cameras/<name>/event_renderer`) collects the events into
`bgr8` images on `/cameras/<name>/image_raw`, at `fps` per second, and reads events only while something subscribes
to the images. The raw events are on `/cameras/<name>/events` for nodes that want them. The driver publishes no `camera_info`, so the
event camera has no intrinsics, and nothing that needs them (`camera_pixels_to_surface`, the frustum in RViz) works with it.
The detectors are built for normal images; how well they work on collected events depends on the scene.

**Vendor plugin.** OpenEB opens Prophesee's own cameras; other makers ship a HAL plugin, which has to match the OpenEB
version bundled with the driver
(`grep VERSION /opt/ros/$ROS_DISTRO/opt/openeb_vendor/include/metavision/sdk/version.h`). For a SilkyEvCam that is
Century Arks' "SilkyEvCam Plugin Installer for ubuntu" of the same version. Its installer refuses Ubuntu versions it
has no folder for; the newest folder's plugin can be installed by hand instead, from the unpacked installer:

```bash
sudo install -D -m 644 resources/24.04/libsilky_common_plugin.so /usr/lib/CenturyArks/hal/plugins/libsilky_common_plugin.so
sudo cp resources/ca_device.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules
```

Then replug the camera, and set the plugin folder in every shell that starts ROS (`par.launch.py` warns when it is
missing; bash: `~/.bashrc`, fish: `set -gx` in `~/.config/fish/config.fish`):

```bash
export MV_HAL_PLUGIN_PATH=/usr/lib/CenturyArks/hal/plugins
```

The package's two command-line tools are not needed by the driver.

**USB 3 only.** On a USB 2 link (`cat /sys/bus/usb/devices/*/speed` shows `480`, e.g. through a USB 2 extension cable),
changing a bias while events stream can abort the driver, and the camera then opens again only after replugging.
