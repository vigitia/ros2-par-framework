# Written by Claude Code
"""Republish framework outputs as RViz markers, starting with /objects projected onto the table."""

from custom_interfaces.msg import ObjectList
from geometry_msgs.msg import Point
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo
from std_msgs.msg import ColorRGBA, Header
from tf2_ros import Buffer, TransformException, TransformListener
from visualization_msgs.msg import Marker, MarkerArray

from .rviz_bridge import pixels_to_table, rotation_matrix

NODE_NAME = 'rviz_bridge_node'
TOPIC_NAME_OBJECTS = '/objects'
TOPIC_NAME_CAMERA_INFO = '/camera/brio/camera_info'
TOPIC_NAME_OBJECT_MARKERS = '/objects/markers'
# The table is the plane z = 0 of this frame
TABLE_FRAME = 'world'

# Outlines are lifted slightly, so they don't flicker into the RViz grid; labels float above
# the object
OUTLINE_HEIGHT = 0.002
LABEL_HEIGHT = 0.05
LINE_WIDTH = 0.005
TEXT_SIZE = 0.04
OUTLINE_COLOR = ColorRGBA(r=0.1, g=0.9, b=0.2, a=1.0)
LABEL_COLOR = ColorRGBA(r=1.0, g=1.0, b=1.0, a=1.0)
WARNING_PERIOD_SEC = 5.0

# The Brio publishes best effort, a reliable subscriber would receive nothing
CAMERA_INFO_QOS = QoSProfile(reliability=QoSReliabilityPolicy.BEST_EFFORT,
                             history=QoSHistoryPolicy.KEEP_LAST, depth=1)
QUEUE_SIZE = 10


class RvizBridgeNode(Node):
    """Turns framework messages RViz cannot display into markers it can."""

    def __init__(self):
        super().__init__(NODE_NAME)
        self.camera_info = None
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.create_subscription(CameraInfo, TOPIC_NAME_CAMERA_INFO, self.on_camera_info,
                                 CAMERA_INFO_QOS)
        self.create_subscription(ObjectList, TOPIC_NAME_OBJECTS, self.on_objects, QUEUE_SIZE)
        self.object_marker_publisher = self.create_publisher(MarkerArray,
                                                             TOPIC_NAME_OBJECT_MARKERS,
                                                             QUEUE_SIZE)

    def on_camera_info(self, msg):
        self.camera_info = msg

    def on_objects(self, msg):
        # Uncalibrated, the camera matrix is all zeros and pixels have no direction
        if self.camera_info is None or self.camera_info.k[0] == 0.0:
            self.get_logger().warning(
                f'No calibrated camera info on {TOPIC_NAME_CAMERA_INFO} yet, objects are not '
                f'shown', throttle_duration_sec=WARNING_PERIOD_SEC)
            return
        # The transform is static, so the latest one (Time()) is also the one at the image's
        # capture time
        try:
            transform = self.tf_buffer.lookup_transform(TABLE_FRAME, msg.header.frame_id, Time())
        except TransformException as e:
            self.get_logger().warning(
                f'No transform {TABLE_FRAME} <- {msg.header.frame_id} yet, objects are not '
                f'shown: {e}', throttle_duration_sec=WARNING_PERIOD_SEC)
            return

        q = transform.transform.rotation
        t = transform.transform.translation
        rotation = rotation_matrix(q.x, q.y, q.z, q.w)
        translation = np.array([t.x, t.y, t.z])
        k = np.reshape(self.camera_info.k, (3, 3))
        d = np.array(self.camera_info.d)

        markers = MarkerArray()
        # Removes the previous frame's markers first, so objects that are gone disappear
        markers.markers.append(Marker(action=Marker.DELETEALL))
        header = Header(stamp=msg.header.stamp, frame_id=TABLE_FRAME)
        for obj in msg.objects:
            # The hull has far fewer points than the contour and is enough for an outline
            pixels = ([(p.x, p.y) for p in obj.hull_contour or obj.contour]
                      or [(obj.center_x, obj.center_y)])
            hits = pixels_to_table(pixels, k, d, rotation, translation)
            if len(hits) == 0:
                continue

            outline = Marker(header=header, ns='outline', id=obj.object_id,
                             type=Marker.LINE_STRIP, color=OUTLINE_COLOR)
            outline.scale.x = LINE_WIDTH
            # Repeating the first point closes the outline
            outline.points = [Point(x=x, y=y, z=OUTLINE_HEIGHT)
                              for x, y, _ in np.vstack([hits, hits[:1]])]

            center = hits.mean(axis=0)
            label = Marker(header=header, ns='label', id=obj.object_id,
                           type=Marker.TEXT_VIEW_FACING, color=LABEL_COLOR,
                           # No space: RViz draws it far too wide at this text size
                           text=f'{obj.class_name}#{obj.object_id}')
            label.scale.z = TEXT_SIZE
            label.pose.position = Point(x=center[0], y=center[1], z=LABEL_HEIGHT)
            label.pose.orientation.w = 1.0

            markers.markers += [outline, label]

        self.object_marker_publisher.publish(markers)


def main(args=None):
    rclpy.init(args=args)
    node = RvizBridgeNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
