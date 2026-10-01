# Written by Claude Code
"""Newest camera frame for the wizard's preview, received on a background thread."""

import threading

import cv2
from cv_bridge import CvBridge
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import Image

PREVIEW_WIDTH_PX = 640
# Camera frames are published best-effort; a reliable subscriber would receive nothing
FRAME_QOS = QoSProfile(reliability=QoSReliabilityPolicy.BEST_EFFORT,
                       history=QoSHistoryPolicy.KEEP_LAST, depth=1)


class PreviewNode(Node):
    """Keeps the newest frame of one image topic, small and in RGB, in self.frame."""

    def __init__(self, topic):
        super().__init__('par_setup_wizard_preview')
        self.bridge = CvBridge()
        self.frame = None
        self.create_subscription(Image, topic, self.on_image, FRAME_QOS)

    def on_image(self, msg):
        # bgr8 also converts the Kinect's bgra8
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        height = frame.shape[0] * PREVIEW_WIDTH_PX // frame.shape[1]
        self.frame = cv2.cvtColor(cv2.resize(frame, (PREVIEW_WIDTH_PX, height)), cv2.COLOR_BGR2RGB)


class Preview:
    """Runs a PreviewNode on its own thread until stop()."""

    def __init__(self, topic):
        self.node = PreviewNode(topic)
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.thread.start()

    def frame(self):
        return self.node.frame

    def stop(self):
        self.executor.shutdown()
        self.thread.join(timeout=2.0)
        self.node.destroy_node()
