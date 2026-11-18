# Written by Claude Code
"""
The setup wizard backend's one ROS node, for every API that needs the ROS graph.

It keeps the latest frame of every camera feed and the latest message of every sensor node output
the app has asked for while a camera launch runs (camera_launch_session.py starts and stops both),
and answers the other APIs' questions about the graph: which node publishes a camera's image,
which image topics a node publishes. Parameter clients and service clients of the other APIs are
created on it too.
"""

import re
import threading
import time

from par_framework_core.launch_helpers import CAMERAS_NAMESPACE
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import Image

# Outputs of sensor nodes (sensor_nodes_api.py) are usually published reliably, frames best
# effort; a best-effort subscriber gets both
OUTPUT_MESSAGE_QOS = QoSProfile(reliability=QoSReliabilityPolicy.BEST_EFFORT,
                                history=QoSHistoryPolicy.KEEP_LAST, depth=1)
# The message type of the topics offered as feeds
FEED_MESSAGE_TYPE_NAME = 'sensor_msgs/msg/Image'
# The stream whose publisher is the camera's driver node, below the camera's namespace
CAMERA_IMAGE_STREAM_NAME = 'image_raw'
# The image topics of every camera, this backend's or another program's (e.g. the framework)
CAMERA_IMAGE_TOPIC_PATTERN = re.compile(
    re.escape(CAMERAS_NAMESPACE) + r'/[^/]+/' + re.escape(CAMERA_IMAGE_STREAM_NAME))
# The node's name in the ROS graph
BACKEND_ROS_NODE_NAME = 'setup_wizard_camera_preview'


class CameraPreviewRosNode(Node):
    """
    The backend's ROS node for the camera preview and the APIs built on it.

    Keeps the latest frame of every feed and the latest message of every sensor node output the
    app has asked for while a camera launch runs; the other APIs use it for the ROS graph,
    parameters and services. Subscribe and stop receiving while holding the session lock, so no
    subscription outlives the camera launch it belongs to.
    """

    def __init__(self):
        super().__init__(BACKEND_ROS_NODE_NAME)
        self._latest_image_message_lock = threading.Lock()
        self._latest_image_message_by_topic = {}
        self._image_subscription_by_topic = {}
        self._output_receiver_by_topic = {}

    def subscribe_to_feed(self, topic_name):
        """Subscribe to a feed unless already subscribed; its first frame arrives later."""
        if topic_name in self._image_subscription_by_topic:
            return
        # Frames are published BEST_EFFORT; a reliable subscriber would receive nothing
        frame_qos = QoSProfile(depth=1, history=QoSHistoryPolicy.KEEP_LAST,
                               reliability=QoSReliabilityPolicy.BEST_EFFORT)

        def keep_latest_image_message(image_message):
            with self._latest_image_message_lock:
                self._latest_image_message_by_topic[topic_name] = image_message

        self._image_subscription_by_topic[topic_name] = self.create_subscription(
            Image, topic_name, keep_latest_image_message, frame_qos)

    def stop_receiving(self):
        """Unsubscribe from every feed and output, so they cost nothing while no launch runs."""
        for image_subscription in self._image_subscription_by_topic.values():
            self.destroy_subscription(image_subscription)
        self._image_subscription_by_topic = {}
        with self._latest_image_message_lock:
            self._latest_image_message_by_topic = {}
        # The next launch may publish other types on the same topics, so they are subscribed anew
        for output_receiver in self._output_receiver_by_topic.values():
            self.destroy_subscription(output_receiver.subscription)
        self._output_receiver_by_topic = {}

    def get_output_receiver(self, topic_name):
        """Return the OutputMessageReceiver of a subscribed output topic, None before."""
        return self._output_receiver_by_topic.get(topic_name)

    def subscribe_to_output_topic(self, topic_name, type_name, message_class):
        """Subscribe to a sensor node's output topic; return its OutputMessageReceiver."""
        output_receiver = OutputMessageReceiver(type_name)
        output_receiver.subscription = self.create_subscription(
            message_class, topic_name, output_receiver.keep_latest_message, OUTPUT_MESSAGE_QOS)
        self._output_receiver_by_topic[topic_name] = output_receiver
        return output_receiver

    def get_latest_image_message(self, topic_name):
        with self._latest_image_message_lock:
            return self._latest_image_message_by_topic.get(topic_name)

    def get_camera_image_publishers(self, image_topic_name=None):
        """
        Return the publishers of a camera image as {endpoint GID: full node name or None}.

        image_topic_name None: of every camera's image_raw below /cameras.
        """
        image_topic_names = [image_topic_name]
        if image_topic_name is None:
            image_topic_names = []
            for topic_name, _ in self.get_topic_names_and_types():
                if CAMERA_IMAGE_TOPIC_PATTERN.fullmatch(topic_name):
                    image_topic_names.append(topic_name)
        # The node name is None while ROS knows the publisher but not yet its node, as right after
        # a camera starts (it reports placeholders like _NODE_NAMESPACE_UNKNOWN_ then).
        node_name_by_publisher_gid = {}
        for each_image_topic_name in image_topic_names:
            for endpoint_info in self.get_publishers_info_by_topic(each_image_topic_name):
                full_node_name = None
                if endpoint_info.node_namespace.startswith('/'):
                    full_node_name = join_node_name(endpoint_info.node_namespace,
                                                    endpoint_info.node_name)
                node_name_by_publisher_gid[tuple(endpoint_info.endpoint_gid)] = full_node_name
        return node_name_by_publisher_gid

    def list_feed_topic_names(self, full_node_name):
        """Return the sensor_msgs/Image topics the node publishes, sorted."""
        node_namespace, node_name = full_node_name.rsplit('/', 1)
        if not node_namespace:
            node_namespace = '/'
        feed_topic_names = []
        topic_names_and_types = self.get_publisher_names_and_types_by_node(node_name,
                                                                           node_namespace)
        for topic_name, type_names in topic_names_and_types:
            if FEED_MESSAGE_TYPE_NAME in type_names:
                feed_topic_names.append(topic_name)
        return sorted(feed_topic_names)


class OutputMessageReceiver:
    """Keeps the latest message of one output topic of a sensor node."""

    def __init__(self, type_name):
        self.type_name = type_name
        self.subscription = None
        self.latest_message_lock = threading.Lock()
        self.latest_message = None
        self.latest_message_monotonic_s = None

    def keep_latest_message(self, output_message):
        with self.latest_message_lock:
            self.latest_message = output_message
            self.latest_message_monotonic_s = time.monotonic()


def join_node_name(node_namespace, node_name):
    """Return a node's full name from its namespace and its name, e.g. /cameras/top/webcam_node."""
    if node_namespace.endswith('/'):
        return node_namespace + node_name
    return f'{node_namespace}/{node_name}'
