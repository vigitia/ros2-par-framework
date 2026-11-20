# Written by Claude Code
"""
Where each camera sits relative to the table, as the launch files publish it.

The measured camera_pose_<camera name>.yaml in the profile's extrinsics folder while it exists,
else a placeholder pose from the parameter files.
"""

import math
import os

from par_framework_core.setup_files import (get_extrinsics_relative_path,
                                            get_path_in_config_folder, read_merged_parameters)
import yaml


# What a camera pose needs, in the measured camera_pose_<camera>.yaml and in the placeholder
POSE_TRANSLATION_KEYS = [f'translation.{axis}' for axis in 'xyz']
POSE_ROTATION_KEYS = [f'rotation.{axis}' for axis in 'xyzw']
CAMERA_POSE_KEYS = POSE_TRANSLATION_KEYS + POSE_ROTATION_KEYS
# A camera's mount transform publisher is /<camera name><CAMERA_TF_PUBLISHER_NAME_SUFFIX>. A
# parameter file section of that name holds the camera's own placeholder pose; without one, the
# camera gets the generic placeholder below
CAMERA_TF_PUBLISHER_NAME_SUFFIX = '_tf_publisher'
# Parameter file section with the placeholder pose of every camera that has neither a measured
# pose nor its own placeholder section. No node has this name, so no node reads it
PLACEHOLDER_CAMERA_POSE_SECTION_NAME = 'placeholder_camera_pose'
# Rotation of a camera's optical frame (z forward, y down) in its body frame (x forward, z up), REP
# 103, as quaternion x, y, z, w: roll -90 deg, yaw -90 deg
OPTICAL_FRAME_ROTATION_QUATERNION_XYZW = (-0.5, 0.5, -0.5, 0.5)


def get_camera_tf_publisher_name(camera_name):
    """Return the node name of a camera's mount transform publisher: <camera>_tf_publisher."""
    return f'{camera_name}{CAMERA_TF_PUBLISHER_NAME_SUFFIX}'


def read_published_camera_pose(params_file_paths, profile_name, camera_name):
    """
    Return the pose a launch publishes for the camera, as (pose, source text, is measured).

    The measurement while it exists: camera_pose_<camera name>.yaml in the profile's extrinsics
    folder, written by camera_pose_calibrator. Else the placeholder (read_placeholder_camera_pose).
    pose is the file's or section's content unchecked; get_invalid_pose_keys checks it. Raises
    OSError or yaml.YAMLError when the measured file cannot be read.
    """
    measured_pose_relative_path = get_extrinsics_relative_path(profile_name, 'camera_pose',
                                                               camera_name)
    measured_pose_path = get_path_in_config_folder(measured_pose_relative_path)
    if os.path.exists(measured_pose_path):
        with open(measured_pose_path) as measured_pose_file:
            camera_pose = yaml.safe_load(measured_pose_file)
        return camera_pose, measured_pose_path, True
    placeholder_pose, pose_source_text = read_placeholder_camera_pose(params_file_paths,
                                                                      camera_name)
    return placeholder_pose, pose_source_text, False


def read_placeholder_camera_pose(params_file_paths, camera_name):
    """
    Return the camera's placeholder pose from the parameter files, as (pose, source text).

    The camera's own section /<camera name>_tf_publisher when a parameter file has one (e.g. a
    profile placing one camera of several elsewhere), else the generic
    PLACEHOLDER_CAMERA_POSE_SECTION_NAME section. pose is the section's content unchecked (None
    when neither section exists); get_invalid_pose_keys checks it.
    """
    merged_parameters = read_merged_parameters(params_file_paths)
    camera_section_name = f'/{get_camera_tf_publisher_name(camera_name)}'
    placeholder_section_name = PLACEHOLDER_CAMERA_POSE_SECTION_NAME
    if camera_section_name in merged_parameters:
        placeholder_section_name = camera_section_name
    placeholder_section = merged_parameters.get(placeholder_section_name) or {}
    placeholder_pose = placeholder_section.get('ros__parameters')
    params_file_paths_text = ' + '.join(params_file_paths)
    pose_source_text = f'the placeholder {placeholder_section_name} in {params_file_paths_text}'
    return placeholder_pose, pose_source_text


def get_invalid_pose_keys(pose):
    """Return the CAMERA_POSE_KEYS that pose lacks or that hold no finite number."""
    if not isinstance(pose, dict):
        return list(CAMERA_POSE_KEYS)
    invalid_keys = []
    for pose_key in CAMERA_POSE_KEYS:
        pose_value = pose.get(pose_key)
        # bool is a subclass of int in Python, but true is no coordinate
        is_number = isinstance(pose_value, (int, float)) and not isinstance(pose_value, bool)
        if not is_number or not math.isfinite(pose_value):
            invalid_keys.append(pose_key)
    return invalid_keys
