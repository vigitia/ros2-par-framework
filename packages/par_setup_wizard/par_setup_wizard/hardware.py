# Written by Claude Code
"""Find the cameras the framework supports, without ROS."""

import glob
import os

# What each camera is called in par_launch. All publish on the same image topic,
# launch_helpers.CAMERA_IMAGE
CAMERAS = {'brio': 'Logitech Brio', 'kinect': 'Azure Kinect', 'webcam': 'Generic webcam'}
# Video devices that are not a generic webcam: the Brio, and the Kinect's colour camera
NOT_WEBCAMS = ('BRIO', 'Azure_Kinect')
# The Kinect's depth camera: Microsoft's vendor id and its product id (lsusb)
KINECT_USB_ID = ('045e', '097c')


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ''


def detect_cameras():
    """
    Return {camera: description} of the connected cameras, camera being brio, kinect or webcam.

    The webcam's description is its name in /dev/v4l/by-id.
    """
    found = {}
    # The by-id names stay the same across replugs, unlike /dev/videoN (as logitech_brio finds it)
    brios = glob.glob('/dev/v4l/by-id/*BRIO*-video-index0')
    if brios:
        found['brio'] = os.path.basename(brios[0])
    for device in glob.glob('/sys/bus/usb/devices/*'):
        if (_read(f'{device}/idVendor'), _read(f'{device}/idProduct')) == KINECT_USB_ID:
            found['kinect'] = f'serial {_read(f"{device}/serial") or "unknown"}'
    # ponytail: the first other camera wins; with several, video_device in the profile picks one
    webcams = [path for path in sorted(glob.glob('/dev/v4l/by-id/*-video-index0'))
               if not any(name in path for name in NOT_WEBCAMS)]
    if webcams:
        found['webcam'] = os.path.basename(webcams[0])
    return found
