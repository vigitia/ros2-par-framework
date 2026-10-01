# Written by Claude Code
"""
Measure the camera's pose from the clear table and store it, then exit.

Collects depth images registered to the colour image, fits the table plane and writes the pose of
the camera body frame (base_frame) in world to camera_pose_file: height and tilt from the plane,
the rotation about the vertical from placeholder_rotation. Exits with 0 when stored, 1 otherwise,
so a launch file can go on to the projector calibration only after a good measurement.
"""

import time

from cv_bridge import CvBridge
import numpy as np
from rcl_interfaces.msg import ParameterDescriptor
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image
from tf2_ros import Buffer, TransformException, TransformListener

from .camera_pose_calibrator import (camera_pose, fit_table_plane, matrix_from_quaternion,
                                     MAX_ABOVE_FRACTION, MAX_TABLE_RMS_M, MIN_TABLE_FRACTION,
                                     points_from_depth, sample_grid, save)

NODE_NAME = 'camera_pose_calibrator_node'
# The framework's camera topics (launch_helpers remaps each camera driver onto them): depth
# registered to the colour image (a depth camera such as the Azure Kinect), and the colour
# camera's intrinsics
TOPIC_NAME_DEPTH = '/camera/depth_registered/image_raw'
TOPIC_NAME_CAMERA_INFO = '/camera/camera_info'
# Camera frames are published best-effort or reliable; a best-effort subscriber takes both
FRAME_QOS = QoSProfile(reliability=QoSReliabilityPolicy.BEST_EFFORT,
                       history=QoSHistoryPolicy.KEEP_LAST, depth=1)


class CameraPoseCalibratorNode(Node):
    """Collects depth frames of the table and stores the camera pose measured from them."""

    def __init__(self):
        super().__init__(NODE_NAME)
        self.declare_parameter('camera_pose_file', '', ParameterDescriptor(
            description='File the measured pose is written to.', read_only=True))
        self.declare_parameter('base_frame', 'camera_base', ParameterDescriptor(
            description='Camera frame whose pose in world is measured (the child frame of the '
                        'mount transform).', read_only=True))
        self.declare_parameter('placeholder_rotation', [0.0, 0.7071068, 0.0, 0.7071068],
                               ParameterDescriptor(
            description='Quaternion (x, y, z, w) of the placeholder pose. Its direction of the '
                        'world x axis is kept, the rest is measured.', read_only=True))
        self.declare_parameter('frames', 30, ParameterDescriptor(
            description='Depth frames whose median is fitted.', read_only=True))
        self.declare_parameter('timeout_sec', 20.0, ParameterDescriptor(
            description='Give up when the frames have not arrived after this long.',
            read_only=True))
        self.pose_file = self.get_parameter('camera_pose_file').value
        self.base_frame = self.get_parameter('base_frame').value
        self.frames = self.get_parameter('frames').value
        self.timeout = self.get_parameter('timeout_sec').value

        self.bridge = CvBridge()
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.camera_info = None
        self.samples = []
        self.grid = None
        self.optical_frame = None
        self.create_subscription(CameraInfo, TOPIC_NAME_CAMERA_INFO, self.on_camera_info,
                                 FRAME_QOS)
        self.create_subscription(Image, TOPIC_NAME_DEPTH, self.on_depth, FRAME_QOS)
        self.start_time = time.monotonic()
        self.create_timer(1.0, self.check_timeout)
        # Set once the pose is stored or the measurement failed; main() then ends the node
        self.done = False
        self.succeeded = False
        self.get_logger().info(f'[CameraPoseCalibratorNode]: Measuring the camera pose from '
                               f'{self.frames} depth frames, keep the table clear')
        if not self.pose_file:
            self.fail('camera_pose_file is empty, there is nowhere to store the pose')

    def on_camera_info(self, msg):
        self.camera_info = msg

    def on_depth(self, msg):
        if self.done or self.camera_info is None:
            return
        depth = self.bridge.imgmsg_to_cv2(msg)
        # REP 118: 16UC1 is in millimetres, 32FC1 in metres
        depth = depth.astype(np.float32) * (0.001 if msg.encoding == '16UC1' else 1.0)
        if depth.shape[:2] != (self.camera_info.height, self.camera_info.width):
            self.fail(f'depth image is {depth.shape[1]}x{depth.shape[0]}, camera_info '
                      f'{self.camera_info.width}x{self.camera_info.height}: the depth must be '
                      f'registered to the colour image')
            return
        if self.grid is None:
            self.grid = sample_grid(*depth.shape[:2])
            self.optical_frame = msg.header.frame_id
        u, v = self.grid
        self.samples.append(depth[v, u])
        if len(self.samples) >= self.frames:
            self.measure()

    def check_timeout(self):
        if self.done or time.monotonic() - self.start_time < self.timeout:
            return
        if self.camera_info is None:
            reason = f'no camera_info on {TOPIC_NAME_CAMERA_INFO}'
        else:
            reason = f'{len(self.samples)} of {self.frames} depth frames on {TOPIC_NAME_DEPTH}'
        self.fail(f'{reason} after {self.timeout:.0f} s (is the depth camera running?)')

    def measure(self):
        # Median per sample over all frames, ignoring pixels without depth (0), against noise
        # Masked instead of NaN: a pixel without depth in any frame is no warning, its median is 0
        z = np.ma.median(np.ma.masked_less_equal(np.array(self.samples), 0), axis=0).filled(0)
        k = np.reshape(self.camera_info.k, (3, 3))
        points = points_from_depth(*self.grid, z, k, np.array(self.camera_info.d))
        normal, centroid, fraction, rms, above = fit_table_plane(points)
        if (above > MAX_ABOVE_FRACTION or fraction < MIN_TABLE_FRACTION
                or rms > MAX_TABLE_RMS_M):
            self.fail(f'{100 * above:.0f} % of the image is above the table (at most '
                      f'{100 * MAX_ABOVE_FRACTION:.0f} %), {100 * fraction:.0f} % is table (at '
                      f'least {100 * MIN_TABLE_FRACTION:.0f} %), RMS {1000 * rms:.1f} mm (at most '
                      f'{1000 * MAX_TABLE_RMS_M:.0f} mm): clear the table and try again')
            return
        try:
            transform = self.tf_buffer.lookup_transform(self.base_frame, self.optical_frame,
                                                        Time())
        except TransformException as e:
            self.fail(f'no transform {self.base_frame} <- {self.optical_frame}: {e}')
            return
        q, t = transform.transform.rotation, transform.transform.translation
        to_base = matrix_from_quaternion((q.x, q.y, q.z, q.w))
        normal_base = to_base @ normal
        point_base = to_base @ centroid + (t.x, t.y, t.z)
        placeholder = matrix_from_quaternion(self.get_parameter('placeholder_rotation').value)
        # The placeholder's world axes in base coordinates are the rows of its rotation
        translation, rotation = camera_pose(normal_base, point_base, placeholder[0])
        tilt = np.degrees(np.arccos(np.clip(normal_base @ placeholder[2], -1.0, 1.0)))
        save(self.pose_file, translation, rotation, fraction, rms)
        self.get_logger().info(
            f'[CameraPoseCalibratorNode]: Stored in {self.pose_file}: {self.base_frame} '
            f'{translation[2]:.3f} m above the table, tilted {tilt:.2f} deg against the '
            f'placeholder; table {100 * fraction:.0f} % of the image, RMS {1000 * rms:.1f} mm')
        self.done = self.succeeded = True

    def fail(self, reason):
        self.get_logger().error(f'[CameraPoseCalibratorNode]: No pose stored: {reason}')
        self.done = True


def main(args=None):
    rclpy.init(args=args)
    node = CameraPoseCalibratorNode()
    try:
        # Spinning step by step instead of rclpy.spin() lets the node end itself once done
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.1)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    return 0 if node.succeeded else 1


if __name__ == '__main__':
    main()
