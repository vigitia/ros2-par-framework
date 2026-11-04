# Written by Claude Code
"""
Blueprint for <pkg>/<pkg>_node.py of a node that processes camera frames.

Collects what the framework's processing nodes (fiducials_detector, hand_landmarks,
object_detector, page_locator, gesture_detector, projection_mask) share. To start a node:
  1. Copy this file to <pkg>/<pkg>_node.py.
  2. Replace example_detector / ExampleDetector with the package and its logic class, and
     ExampleResult / ExampleResultList with the node's messages in par_framework_interfaces.
  3. Delete the blocks marked "Optional" that the node doesn't need.
  4. Replace this docstring with what the node subscribes to and publishes.

Only the ROS work lives here (topics, parameters, message conversion, main()). The processing
itself goes into <pkg>/<pkg>.py, which imports nothing from rclpy or message packages and takes
plain Python/NumPy values, so it can be tested with plain pytest.
"""

import time

import cv2
from cv_bridge import CvBridge
from message_filters import ApproximateTimeSynchronizer, Subscriber
import numpy as np
from par_framework_interfaces.msg import ExampleResult, ExampleResultList
from rcl_interfaces.msg import ParameterDescriptor
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import CameraInfo, CompressedImage, Image

from .example_detector import ExampleDetector

NODE_NAME = 'example_detector_node'

# The framework's neutral camera topics, onto which the launch files remap every camera driver.
# Nodes hard-code them; another topic is chosen by remapping, not by parameter.
TOPIC_NAME_FRAME = '/camera/image_raw'
# With use_compressed: its compressed variant, named by the image_transport convention (JPEGs a
# camera driver passes through without decoding them)
TOPIC_NAME_FRAME_COMPRESSED = TOPIC_NAME_FRAME + '/compressed'
TOPIC_NAME_FRAME_DEPTH = '/camera/depth_registered/image_raw'
TOPIC_NAME_CAMERA_INFO = '/camera/camera_info'
# The node's own output, relative, so a namespace in the launch file moves it along
TOPIC_NAME_RESULTS = 'example_results'

# History depth of the result publisher (reliable, one message per frame)
PUBLISHER_QUEUE_SIZE = 10
# Per-frame warnings are throttled to one per this period, so they don't flood the log
WARNING_THROTTLE_PERIOD_SEC = 5.0

# Camera drivers may publish frames and camera_info best effort. A reliable subscriber (also what
# passing an int as qos_profile means) is QoS-incompatible with them and silently receives
# nothing, while a best-effort one connects to best-effort and reliable publishers alike. Depth 1:
# only the newest frame matters, processing an old one would publish outdated results.
FRAME_QOS = QoSProfile(reliability=QoSReliabilityPolicy.BEST_EFFORT,
                       history=QoSHistoryPolicy.KEEP_LAST, depth=1)

# Optional, with use_depth: pairing colour and depth frames
SYNC_LEEWAY_TIME_SEC = 0.01
# Colour frames arriving without any depth for this long means no depth camera: no pair is ever
# formed and nothing is published, which the node then says
DEPTH_MISSING_TIMEOUT_SEC = 2.0
DEPTH_CHECK_PERIOD_SEC = 1.0
# REP 118: depth images in 16UC1 are in millimetres, 32FC1 in metres
M_PER_MM = 0.001

# Parameter names as constants: descriptions and warnings can name them without typos
PARAMETER_USE_COMPRESSED = 'use_compressed'
PARAMETER_USE_DEPTH = 'use_depth'
PARAMETER_DEBUG = 'debug'


class ExampleDetectorNode(Node):
    """Turns camera frames into one ExampleResultList per frame, in camera pixels."""

    def __init__(self):
        super().__init__(node_name=NODE_NAME)

        self._declare_parameters()

        self.cv_bridge = CvBridge()
        self.example_detector = ExampleDetector(debug=self.get_parameter(PARAMETER_DEBUG).value)

        self.camera_info = None
        self._create_subscriptions()

        self.results_publisher = self.create_publisher(msg_type=ExampleResultList,
                                                       topic=TOPIC_NAME_RESULTS,
                                                       qos_profile=PUBLISHER_QUEUE_SIZE)

    def _declare_parameters(self):
        # All read-only: subscriptions and the detector are created once at startup, a later
        # change would have no effect. Values per setup go into par_setup.yaml, keyed by the
        # node's full name.
        self.declare_parameter(PARAMETER_USE_COMPRESSED, False, ParameterDescriptor(
            description=f'Subscribe to {TOPIC_NAME_FRAME_COMPRESSED} '
                        f'(sensor_msgs/CompressedImage) instead of {TOPIC_NAME_FRAME}. Only for '
                        f'camera drivers that publish it.',
            read_only=True))
        self.declare_parameter(PARAMETER_USE_DEPTH, False, ParameterDescriptor(
            description=f'Also subscribe to {TOPIC_NAME_FRAME_DEPTH} (depth registered to the '
                        f'colour image, from a depth camera) and add 3D positions in metres in '
                        f'the optical frame.',
            read_only=True))
        self.declare_parameter(PARAMETER_DEBUG, False, ParameterDescriptor(
            description='Show the frames with the results in an OpenCV window (needs a '
                        'display). Only for testing.',
            read_only=True))

    def _create_subscriptions(self):
        # Optional: raw frames, or with use_compressed their compressed variant
        if self.get_parameter(PARAMETER_USE_COMPRESSED).value:
            frame_msg_type = CompressedImage
            topic_name_frame = TOPIC_NAME_FRAME_COMPRESSED
        else:
            frame_msg_type = Image
            topic_name_frame = TOPIC_NAME_FRAME

        self.camera_info_subscription = self.create_subscription(
            msg_type=CameraInfo,
            topic=TOPIC_NAME_CAMERA_INFO,
            callback=self._on_camera_info,
            qos_profile=FRAME_QOS)

        if self.get_parameter(PARAMETER_USE_DEPTH).value:
            self._create_frame_and_depth_subscriptions(frame_msg_type, topic_name_frame)
            return
        self.create_subscription(msg_type=frame_msg_type,
                                 topic=topic_name_frame,
                                 callback=self._on_frame_received,
                                 qos_profile=FRAME_QOS)

    def _on_camera_info(self, camera_info_msg):
        self.camera_info = camera_info_msg
        # Uncalibrated, the camera matrix is all zeros: keep listening until calibrated
        # intrinsics arrive
        if camera_info_msg.k[0] == 0.0:
            return
        # camera_info comes with every frame, but the intrinsics stay the same while the camera
        # runs. Simplification: intrinsics stored with set_camera_info while this node runs take
        # effect only after a restart. Upgrade: subscribe again on a slow timer.
        self.destroy_subscription(self.camera_info_subscription)
        self.get_logger().info(f'Calibrated camera info received, no longer subscribed to '
                               f'{TOPIC_NAME_CAMERA_INFO}')

    # Optional, with use_depth (down to _get_depth_image_on_frame_grid)
    def _create_frame_and_depth_subscriptions(self, frame_msg_type, topic_name_frame):
        """Process colour and depth frames in pairs, and warn when no depth arrives."""
        frame_subscriber = Subscriber(self, frame_msg_type, topic_name_frame,
                                      qos_profile=FRAME_QOS)
        depth_subscriber = Subscriber(self, Image, TOPIC_NAME_FRAME_DEPTH, qos_profile=FRAME_QOS)
        self.frame_depth_synchronizer = ApproximateTimeSynchronizer(
            [frame_subscriber, depth_subscriber], PUBLISHER_QUEUE_SIZE, SYNC_LEEWAY_TIME_SEC)
        self.frame_depth_synchronizer.registerCallback(self._on_frame_and_depth_received)

        # Each subscriber also reports its own messages, so a missing depth camera shows up even
        # though the synchronizer then never forms a pair
        self.first_frame_time_sec = None
        self.last_frame_time_sec = None
        self.last_depth_time_sec = None
        frame_subscriber.registerCallback(self._on_frame_arrived)
        depth_subscriber.registerCallback(self._on_depth_arrived)
        self.create_timer(DEPTH_CHECK_PERIOD_SEC, self._warn_if_depth_missing)
        # The name after remapping, which is what the warnings must name
        self.depth_topic_name = depth_subscriber.sub.topic_name

    def _on_frame_arrived(self, frame_msg):
        self.last_frame_time_sec = time.monotonic()
        if self.first_frame_time_sec is None:
            self.first_frame_time_sec = self.last_frame_time_sec

    def _on_depth_arrived(self, depth_msg):
        self.last_depth_time_sec = time.monotonic()

    def _warn_if_depth_missing(self):
        if self.last_frame_time_sec is None:
            return
        now_sec = time.monotonic()
        # Not before DEPTH_MISSING_TIMEOUT_SEC of colour frames: a driver may only start
        # computing registered depth once it sees a subscriber
        frames_arrive = (now_sec - self.last_frame_time_sec < DEPTH_MISSING_TIMEOUT_SEC
                         and now_sec - self.first_frame_time_sec > DEPTH_MISSING_TIMEOUT_SEC)
        depth_missing = (self.last_depth_time_sec is None
                         or now_sec - self.last_depth_time_sec > DEPTH_MISSING_TIMEOUT_SEC)
        if frames_arrive and depth_missing:
            self.get_logger().warning(
                f'use_depth is true, but no depth frames arrive on {self.depth_topic_name}, so '
                f'nothing is published. Connect a depth camera or set use_depth to false.',
                throttle_duration_sec=WARNING_THROTTLE_PERIOD_SEC)

    def _on_frame_and_depth_received(self, frame_msg, depth_msg):
        depth_image_m = self.cv_bridge.imgmsg_to_cv2(depth_msg)
        if depth_msg.encoding == '16UC1':
            depth_image_m = depth_image_m.astype(np.float32) * M_PER_MM
        self._on_frame_received(frame_msg, depth_image_m)

    def _get_depth_image_on_frame_grid(self, depth_image_m, frame):
        """Return depth_image_m if it is on the frame's pixel grid, else None with a warning."""
        if depth_image_m.shape[:2] == frame.shape[:2]:
            return depth_image_m
        # A depth image on another pixel grid (e.g. a driver's unregistered depth remapped by
        # mistake) would give every result the depth of some other point
        depth_height_px, depth_width_px = depth_image_m.shape[:2]
        frame_height_px, frame_width_px = frame.shape[:2]
        self.get_logger().warning(
            f'depth image is {depth_width_px}x{depth_height_px}, the colour image '
            f'{frame_width_px}x{frame_height_px}: {self.depth_topic_name} must be registered to '
            f'the colour image, no 3D positions',
            throttle_duration_sec=WARNING_THROTTLE_PERIOD_SEC)
        return None

    def _on_frame_received(self, frame_msg, depth_image_m=None):
        """Process a raw or compressed frame, with depth (metres) for 3D positions."""
        frame_bgr = self._decode_frame_bgr(frame_msg)
        if frame_bgr is None:
            return
        if depth_image_m is not None:
            depth_image_m = self._get_depth_image_on_frame_grid(depth_image_m, frame_bgr)

        results = self.example_detector.detect(frame_bgr)
        # Optional: 3D positions need depth and calibrated intrinsics; without them the results
        # stay in camera pixels. Uncalibrated, the camera matrix is all zeros.
        if (depth_image_m is not None and self.camera_info is not None
                and self.camera_info.k[0] != 0.0):
            camera_matrix = np.reshape(self.camera_info.k, (3, 3))
            distortion_coefficients = np.array(self.camera_info.d)
            self.example_detector.add_positions_3d(results, depth_image_m, camera_matrix,
                                                   distortion_coefficients)

        # Published for every frame, also without results: an empty list is how subscribers
        # learn that something disappeared
        results_msg = self._create_results_msg(results, frame_msg.header)
        self.results_publisher.publish(results_msg)

    def _decode_frame_bgr(self, frame_msg):
        """Return the frame as 8-bit BGR, or None if a compressed frame can't be decoded."""
        if not isinstance(frame_msg, CompressedImage):
            # Asking cv_bridge for an encoding converts whatever the camera driver is set to
            # (bgr8, rgb8, mono8, ...). Ask for what the logic needs, e.g. mono8 or rgb8.
            return self.cv_bridge.imgmsg_to_cv2(frame_msg, desired_encoding='bgr8')

        jpeg_bytes = np.frombuffer(frame_msg.data, np.uint8)
        frame_bgr = cv2.imdecode(jpeg_bytes, cv2.IMREAD_COLOR)
        if frame_bgr is None:
            self.get_logger().warning(
                f'could not decode a frame on {TOPIC_NAME_FRAME_COMPRESSED} '
                f'(format "{frame_msg.format}"), skipped',
                throttle_duration_sec=WARNING_THROTTLE_PERIOD_SEC)
        return frame_bgr

    @staticmethod
    def _create_results_msg(results, frame_header):
        # The frame's header (capture stamp and camera frame_id): consumers match the results
        # to the frame they were found in, and the stamp carries no processing delay
        results_msg = ExampleResultList(header=frame_header)
        for result in results:
            results_msg.results.append(ExampleResult(id=int(result['id']),
                                                     x_px=float(result['x_px']),
                                                     y_px=float(result['y_px'])))
        return results_msg


def main(args=None):
    rclpy.init(args=args)
    node = ExampleDetectorNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except Exception:
        # rclpy's signal handler shuts the context down while spin is running. Depending on
        # timing a callback or the executor then fails with an RCLError ("context is invalid")
        # instead of ExternalShutdownException. Errors after the shutdown are just that race;
        # errors while the context is still valid are real and re-raised.
        if rclpy.ok():
            raise
    finally:
        node.destroy_node()
        # The signal handler may have shut the context down already, and a second
        # rclpy.shutdown() raises
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
