# Written by Claude Code
"""Named setup profiles: par_setup.yaml and par_setup_<name>.yaml, edited with comments kept."""

from datetime import datetime
import math
import os
import re
import shutil

from ament_index_python.packages import get_package_share_directory
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import PlainScalarString
import yaml

DEFAULT_PROFILE = 'default'
PROFILE_FILE = re.compile(r'par_setup_([A-Za-z0-9_-]+)\.yaml')
# The keys of a mount pose, in par_setup.yaml and in the pose files
POSE_KEYS = ('translation.x', 'translation.y', 'translation.z',
             'rotation.x', 'rotation.y', 'rotation.z', 'rotation.w')
MANUAL_POSE_HEADER = (
    '# Pose of the camera body frame in world (the table plane is z = 0), entered by hand in the\n'
    '# setup wizard (height and tilt). Used instead of the placeholder in par_setup.yaml while\n'
    '# this file exists; camera_pose_calibrator replaces it with a measurement.\n')


def config_dir():
    """Return par_framework_core's config folder in the source tree."""
    # realpath follows the --symlink-install link back to the source folder, where the
    # calibrations are stored too (launch_helpers.next_to_params_file)
    installed = os.path.join(get_package_share_directory('par_framework_core'), 'config',
                             'par_setup.yaml')
    return os.path.dirname(os.path.realpath(installed))


def repo_root():
    """Return the root of the framework repository (config is three folders below it)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(config_dir())))


def profile_path(name):
    """Return the file of the profile name."""
    file_name = 'par_setup.yaml' if name == DEFAULT_PROFILE else f'par_setup_{name}.yaml'
    return os.path.join(config_dir(), file_name)


def list_profiles():
    """Return the profile names, the default first."""
    names = sorted(m.group(1) for m in map(PROFILE_FILE.fullmatch, os.listdir(config_dir())) if m)
    return [DEFAULT_PROFILE] + names


def create_profile(name, source):
    """Create profile name as a copy of profile source."""
    if name == DEFAULT_PROFILE or not PROFILE_FILE.fullmatch(f'par_setup_{name}.yaml'):
        raise ValueError(f'"{name}" is no valid profile name: letters, digits, _ and - only')
    path = profile_path(name)
    if os.path.exists(path):
        raise FileExistsError(f'profile "{name}" exists already')
    shutil.copyfile(profile_path(source), path)


def delete_profile(name):
    """Delete profile name; the default (par_setup.yaml, tracked in git) can't be deleted."""
    if name == DEFAULT_PROFILE:
        raise ValueError('the default profile par_setup.yaml can not be deleted')
    os.remove(profile_path(name))


class Profile:
    """One profile, loaded round-trip: save() writes back the comments and layout of the file."""

    def __init__(self, name):
        self.name = name
        self.path = profile_path(name)
        self.yaml = YAML()
        # The file's own layout: 2-space indentation, lines up to its 120 columns
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.yaml.width = 120
        self.yaml.preserve_quotes = True
        with open(self.path) as f:
            self.data = self.yaml.load(f)

    def value(self, node, key, default=None):
        """Return parameter key of node, or default."""
        return self.data.get(node, {}).get('ros__parameters', {}).get(key, default)

    def set_value(self, node, key, value):
        """Set parameter key of node, adding the node's section if it is missing."""
        if node not in self.data:
            self.data[node] = CommentedMap(ros__parameters=CommentedMap())
        if isinstance(value, str):
            # preserve_quotes would otherwise keep the quotes of the value it replaces (e.g. of a
            # new profile's ''); plain where YAML allows it, quoted where it must be
            value = PlainScalarString(value)
        parameters = self.data[node]['ros__parameters']
        if key in parameters or not parameters:
            parameters[key] = value
            return
        # ruamel keeps the blank line and comments after a section (the next section's heading) as
        # the comment of its last key. Moved to the new last key, they stay in front of the next
        # section instead of ending up between its heading and itself.
        last = list(parameters)[-1]
        comment = parameters.ca.items.pop(last, None)
        parameters[key] = value
        if comment is not None:
            parameters.ca.items[key] = comment

    def save(self):
        with open(self.path, 'w') as f:
            self.yaml.dump(self.data, f)


def pose_file(camera):
    """Return the camera's pose file, which the launch files prefer to the profile's pose."""
    return os.path.join(config_dir(), f'camera_pose_{camera}.yaml')


def current_pose(profile, camera):
    """
    Return (pose, source) of the camera's mount pose, as the launch files will use it.

    pose holds the POSE_KEYS. source is 'measured' (camera_pose_calibrator), 'entered' (by hand,
    save_manual_pose) or 'placeholder' (the profile's /<camera>_tf_publisher, no pose file).
    """
    path = pose_file(camera)
    if os.path.exists(path):
        with open(path) as f:
            pose = yaml.safe_load(f)
        return pose, 'measured' if 'measured' in pose else 'entered'
    return {key: profile.value(f'/{camera}_tf_publisher', key) for key in POSE_KEYS}, 'placeholder'


def save_manual_pose(camera, pose, height_m, tilt_deg):
    """Write the camera's pose file: pose with new height and tilt, marked as entered by hand."""
    pose = {key: float(pose[key]) for key in POSE_KEYS}
    pose.update(pose_from_height_tilt(height_m, tilt_deg))
    pose['entered'] = datetime.now().isoformat(timespec='seconds')
    with open(pose_file(camera), 'w') as f:
        f.write(MANUAL_POSE_HEADER)
        yaml.safe_dump(pose, f, sort_keys=False)


def pose_from_height_tilt(height_m, tilt_deg):
    """
    Return the mount pose keys of a camera height_m above the table, tilted tilt_deg.

    The camera body frame has x forward and z up (as /brio_tf_publisher). 0 degrees is straight
    down, the placeholder's pitch of 90 degrees; positive tilts the view towards world +x.
    """
    pitch = math.radians(90.0 - tilt_deg)
    return {'translation.z': float(height_m),
            'rotation.x': 0.0, 'rotation.y': math.sin(pitch / 2),
            'rotation.z': 0.0, 'rotation.w': math.cos(pitch / 2)}


def height_tilt_from_pose(pose):
    """Return (height_m, tilt_deg) of the mount pose keys, the inverse of pose_from_height_tilt."""
    # Only the rotation about y is read: the pose the form writes has no other
    pitch = 2 * math.atan2(pose['rotation.y'], pose['rotation.w'])
    return pose['translation.z'], 90.0 - math.degrees(pitch)
