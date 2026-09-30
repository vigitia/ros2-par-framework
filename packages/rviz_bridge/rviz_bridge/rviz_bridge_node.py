# Written by Claude Code
"""Republish framework outputs as RViz markers: objects, hands, fiducials, projection."""

from custom_interfaces.msg import (FiducialsList, HandLandmarksList, ObjectList,
                                   ProjectionCorners, ProjectionMapping)
from geometry_msgs.msg import Point
import numpy as np
from par_geometry.par_geometry import (homography_from_msg, pixels_to_table,
                                       projector_to_table, rotation_matrix)
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo
from std_msgs.msg import ColorRGBA, Header
from tf2_ros import Buffer, TransformException, TransformListener
from visualization_msgs.msg import Marker, MarkerArray

NODE_NAME = 'rviz_bridge_node'
TOPIC_NAME_OBJECTS = '/objects'
TOPIC_NAME_CAMERA_INFO = '/camera/brio/camera_info'
TOPIC_NAME_PROJECTION_CORNERS = '/projection_corners'
TOPIC_NAME_OBJECT_MARKERS = '/objects/markers'
TOPIC_NAME_PROJECTION_MARKERS = '/projection_corners/markers'
TOPIC_NAME_HANDS = '/hand_landmarks'
TOPIC_NAME_HAND_MARKERS = '/hand_landmarks/markers'
TOPIC_NAME_FIDUCIALS = '/fiducials'
TOPIC_NAME_FIDUCIAL_MARKERS = '/fiducials/markers'
TOPIC_NAME_PROJECTION_MAPPING = '/projection_mapping'
TOPIC_NAME_MAPPING_MARKERS = '/projection_mapping/markers'
# The table is the plane z = 0 of this frame
TABLE_FRAME = 'world'
CORNER_NAMES = ('top_left', 'top_right', 'bottom_right', 'bottom_left')

# Outlines are lifted slightly, so they don't flicker into the RViz grid; labels float above
# the object
OUTLINE_HEIGHT = 0.002
LABEL_HEIGHT = 0.05
LINE_WIDTH = 0.005
TEXT_SIZE = 0.04
OUTLINE_COLOR = ColorRGBA(r=0.1, g=0.9, b=0.2, a=1.0)
LABEL_COLOR = ColorRGBA(r=1.0, g=1.0, b=1.0, a=1.0)
# The projection area lies just below the object outlines, so objects stay visible on top of it
AREA_HEIGHT = 0.001
AREA_OUTLINE_COLOR = ColorRGBA(r=0.2, g=0.5, b=1.0, a=1.0)
AREA_FILL_COLOR = ColorRGBA(r=0.2, g=0.5, b=1.0, a=0.25)
# The calibrated projector outline, between the clicked area and the object outlines
PROJECTOR_HEIGHT = 0.0015
PROJECTOR_COLOR = ColorRGBA(r=1.0, g=0.2, b=0.8, a=1.0)
# Hands are drawn where their landmarks' camera rays hit the table, like a shadow straight below
# the camera, just above the object outlines
HAND_HEIGHT = 0.003
JOINT_SIZE = 0.008
HAND_COLORS = {'Left': ColorRGBA(r=1.0, g=0.6, b=0.1, a=1.0),
               'Right': ColorRGBA(r=0.9, g=0.2, b=0.9, a=1.0)}
NUM_HAND_LANDMARKS = 21
# Pairs of landmark ids forming the bones, as mediapipe's
# HandLandmarksConnections.HAND_CONNECTIONS; copied, so rviz_bridge does not need mediapipe
# just for this list
HAND_CONNECTIONS = ((0, 1), (1, 2), (2, 3), (3, 4),         # thumb
                    (0, 5), (5, 6), (6, 7), (7, 8),         # index finger
                    (9, 10), (10, 11), (11, 12),            # middle finger
                    (13, 14), (14, 15), (15, 16),           # ring finger
                    (0, 17), (17, 18), (18, 19), (19, 20),  # pinky
                    (5, 9), (9, 13), (13, 17))              # palm
# Fiducials lie flat on the table like the objects; yellow, as orange is the left hand
FIDUCIAL_COLOR = ColorRGBA(r=1.0, g=0.85, b=0.1, a=1.0)
# The corners arrive once, the calibration and TF possibly later: the area is redrawn periodically
AREA_PERIOD_SEC = 1.0
WARNING_PERIOD_SEC = 5.0

# The Brio publishes best effort, a reliable subscriber would receive nothing
CAMERA_INFO_QOS = QoSProfile(reliability=QoSReliabilityPolicy.BEST_EFFORT,
                             history=QoSHistoryPolicy.KEEP_LAST, depth=1)
# /projection_corners is latched: without Transient Local, corners stored before this node started
# would never arrive
LATCHED_QOS = QoSProfile(reliability=QoSReliabilityPolicy.RELIABLE,
                         durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
                         history=QoSHistoryPolicy.KEEP_LAST, depth=1)
QUEUE_SIZE = 10


class RvizBridgeNode(Node):
    """Turns framework messages RViz cannot display into markers it can."""

    def __init__(self):
        super().__init__(NODE_NAME)
        self.camera_info = None
        self.projection_corners = None
        self.projection_mapping = None
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.create_subscription(CameraInfo, TOPIC_NAME_CAMERA_INFO, self.on_camera_info,
                                 CAMERA_INFO_QOS)
        self.create_subscription(ObjectList, TOPIC_NAME_OBJECTS, self.on_objects, QUEUE_SIZE)
        self.create_subscription(ProjectionCorners, TOPIC_NAME_PROJECTION_CORNERS,
                                 self.on_projection_corners, LATCHED_QOS)
        self.create_subscription(HandLandmarksList, TOPIC_NAME_HANDS, self.on_hands, QUEUE_SIZE)
        self.create_subscription(FiducialsList, TOPIC_NAME_FIDUCIALS, self.on_fiducials,
                                 QUEUE_SIZE)
        self.fiducial_marker_publisher = self.create_publisher(MarkerArray,
                                                               TOPIC_NAME_FIDUCIAL_MARKERS,
                                                               QUEUE_SIZE)
        self.hand_marker_publisher = self.create_publisher(MarkerArray, TOPIC_NAME_HAND_MARKERS,
                                                           QUEUE_SIZE)
        self.object_marker_publisher = self.create_publisher(MarkerArray,
                                                             TOPIC_NAME_OBJECT_MARKERS,
                                                             QUEUE_SIZE)
        self.area_marker_publisher = self.create_publisher(MarkerArray,
                                                           TOPIC_NAME_PROJECTION_MARKERS,
                                                           QUEUE_SIZE)
        self.create_subscription(ProjectionMapping, TOPIC_NAME_PROJECTION_MAPPING,
                                 self.on_projection_mapping, LATCHED_QOS)
        self.mapping_marker_publisher = self.create_publisher(MarkerArray,
                                                              TOPIC_NAME_MAPPING_MARKERS,
                                                              QUEUE_SIZE)
        self.create_timer(AREA_PERIOD_SEC, self.publish_projection_area)
        # RViz subscribes Volatile, so a late RViz needs the outline repeated as well
        self.create_timer(AREA_PERIOD_SEC, self.publish_projector_outline)

    def on_camera_info(self, msg):
        self.camera_info = msg

    def on_projection_corners(self, msg):
        self.projection_corners = msg
        self.publish_projection_area()

    def on_projection_mapping(self, msg):
        self.projection_mapping = msg
        self.publish_projector_outline()

    def publish_projector_outline(self):
        """Draw where the calibrated projector image lies on the table."""
        mapping = self.projection_mapping
        if mapping is None:
            return
        width, height = mapping.projector_width, mapping.projector_height
        # The projector's corners back onto the table: no camera needed, only the mapping
        corners = projector_to_table(homography_from_msg(mapping),
                                     [(0, 0), (width, 0), (width, height), (0, height)])
        points = [Point(x=x, y=y, z=PROJECTOR_HEIGHT) for x, y in corners]
        outline = Marker(header=Header(stamp=self.get_clock().now().to_msg(),
                                       frame_id=mapping.header.frame_id),
                         ns='projector_outline', id=0, type=Marker.LINE_STRIP,
                         color=PROJECTOR_COLOR, points=points + points[:1])
        outline.scale.x = LINE_WIDTH
        outline.pose.orientation.w = 1.0
        self.mapping_marker_publisher.publish(MarkerArray(markers=[outline]))

    def on_objects(self, msg):
        projection = self.__projection(msg.header.frame_id, 'objects')
        if projection is None:
            return

        markers = MarkerArray()
        # Removes the previous frame's markers first, so objects that are gone disappear
        markers.markers.append(Marker(action=Marker.DELETEALL))
        header = Header(stamp=msg.header.stamp, frame_id=TABLE_FRAME)
        for obj in msg.objects:
            if obj.hull_contour_3d:
                # Measured with a depth camera (object_detector with use_depth): the top outline
                # drawn where it is, moved from the optical frame into the table frame
                _, _, rotation, translation = projection
                camera = np.array([(p.x, p.y, p.z) for p in obj.hull_contour_3d])
                hits = camera @ rotation.T + translation
            else:
                # The hull has far fewer points than the contour and is enough for an outline
                pixels = ([(p.x, p.y) for p in obj.hull_contour or obj.contour]
                          or [(obj.center_x, obj.center_y)])
                hits = pixels_to_table(pixels, *projection)
                if len(hits) == 0:
                    continue
                hits[:, 2] = OUTLINE_HEIGHT

            outline = Marker(header=header, ns='outline', id=obj.object_id,
                             type=Marker.LINE_STRIP, color=OUTLINE_COLOR)
            outline.scale.x = LINE_WIDTH
            # Repeating the first point closes the outline
            outline.points = [Point(x=x, y=y, z=z) for x, y, z in np.vstack([hits, hits[:1]])]

            center = hits.mean(axis=0)
            label = Marker(header=header, ns='label', id=obj.object_id,
                           type=Marker.TEXT_VIEW_FACING, color=LABEL_COLOR,
                           # No space: RViz draws it far too wide at this text size
                           text=f'{obj.class_name}#{obj.object_id}')
            label.scale.z = TEXT_SIZE
            label.pose.position = Point(x=center[0], y=center[1], z=center[2] + LABEL_HEIGHT)
            label.pose.orientation.w = 1.0

            markers.markers += [outline, label]

        self.object_marker_publisher.publish(markers)

    def on_hands(self, msg):
        projection = self.__projection(msg.header.frame_id, 'hands')
        if projection is None:
            return

        markers = MarkerArray()
        # Removes the previous frame's markers first, so hands that are gone disappear
        markers.markers.append(Marker(action=Marker.DELETEALL))
        header = Header(stamp=msg.header.stamp, frame_id=TABLE_FRAME)
        for hand in msg.hands:
            # One entry per landmark, None where it has no position
            if len(hand.hand_landmarks_3d) == NUM_HAND_LANDMARKS:
                # Measured with a depth camera (hand_landmarks with use_depth): drawn where they
                # are, moved from the optical frame into the table frame
                _, _, rotation, translation = projection
                camera = np.array([(lm.x, lm.y, lm.z) for lm in hand.hand_landmarks_3d])
                table = camera @ rotation.T + translation
                # z <= 0 (in front of the camera is z > 0): -1, -1, -1 marks "no depth"
                points = [Point(x=x, y=y, z=z) if depth > 0 else None
                          for (x, y, z), depth in zip(table, camera[:, 2])]
            else:
                hits = pixels_to_table([(lm.x, lm.y) for lm in hand.hand_landmarks],
                                       *projection)
                # Rays that miss the table are dropped, which would shift the ids the bones
                # refer to
                if len(hits) != NUM_HAND_LANDMARKS:
                    continue
                points = [Point(x=x, y=y, z=HAND_HEIGHT) for x, y, _ in hits]
            valid = [point for point in points if point is not None]
            if not valid:
                continue
            color = HAND_COLORS.get(hand.handedness, LABEL_COLOR)

            joints = Marker(header=header, ns='hand_joints', id=hand.id, type=Marker.SPHERE_LIST,
                            color=color, points=valid)
            joints.scale.x = joints.scale.y = joints.scale.z = JOINT_SIZE
            # LINE_LIST draws one line per pair of points; bones to a landmark without a position
            # are left out
            bone_points = [points[i] for connection in HAND_CONNECTIONS
                           if None not in (points[connection[0]], points[connection[1]])
                           for i in connection]
            bones = Marker(header=header, ns='hand_bones', id=hand.id, type=Marker.LINE_LIST,
                           color=color, points=bone_points)
            bones.scale.x = LINE_WIDTH
            # Above the wrist (landmark 0), or the first landmark with a position
            anchor = points[0] if points[0] is not None else valid[0]
            label = Marker(header=header, ns='hand_label', id=hand.id,
                           type=Marker.TEXT_VIEW_FACING, color=LABEL_COLOR,
                           text=f'{hand.handedness}#{hand.id}')
            label.scale.z = TEXT_SIZE
            label.pose.position = Point(x=anchor.x, y=anchor.y, z=anchor.z + LABEL_HEIGHT)
            for marker in (joints, bones, label):
                marker.pose.orientation.w = 1.0

            markers.markers += [joints, bones, label]

        self.hand_marker_publisher.publish(markers)

    def on_fiducials(self, msg):
        projection = self.__projection(msg.header.frame_id, 'fiducials')
        if projection is None:
            return

        markers = MarkerArray()
        # Removes the previous frame's markers first, so fiducials that are gone disappear
        markers.markers.append(Marker(action=Marker.DELETEALL))
        header = Header(stamp=msg.header.stamp, frame_id=TABLE_FRAME)
        for fiducial in msg.fiducials:
            # OpenCV's corner order: clockwise from the marker's top left
            if len(fiducial.corners_3d) == 4:
                # Measured with a depth camera (fiducials_detector with use_depth): drawn where
                # the marker is, moved from the optical frame into the table frame
                _, _, rotation, translation = projection
                camera = np.array([(p.x, p.y, p.z) for p in fiducial.corners_3d])
                hits = camera @ rotation.T + translation
            else:
                corners = [(fiducial.x0, fiducial.y0), (fiducial.x1, fiducial.y1),
                           (fiducial.x2, fiducial.y2), (fiducial.x3, fiducial.y3)]
                hits = pixels_to_table(corners, *projection)
                # Rays that miss the table are dropped, which would shift which corner is which
                if len(hits) != len(corners):
                    continue
                hits[:, 2] = OUTLINE_HEIGHT
            points = [Point(x=x, y=y, z=z) for x, y, z in hits]
            center = hits.mean(axis=0)

            outline = Marker(header=header, ns='fiducial_outline', id=fiducial.id,
                             type=Marker.LINE_STRIP, color=FIDUCIAL_COLOR,
                             points=points + points[:1])
            outline.scale.x = LINE_WIDTH
            # From the centre to the middle of the first edge, the marker's top: shows its
            # rotation, the same edge fiducials_detector computes its angle from
            top = (hits[0] + hits[1]) / 2
            direction = Marker(header=header, ns='fiducial_direction', id=fiducial.id,
                               type=Marker.LINE_LIST, color=FIDUCIAL_COLOR,
                               points=[Point(x=center[0], y=center[1], z=center[2]),
                                       Point(x=top[0], y=top[1], z=top[2])])
            direction.scale.x = LINE_WIDTH
            label = Marker(header=header, ns='fiducial_label', id=fiducial.id,
                           type=Marker.TEXT_VIEW_FACING, color=LABEL_COLOR,
                           # No space: RViz draws it far too wide at this text size
                           text=f'#{fiducial.id}')
            label.scale.z = TEXT_SIZE
            label.pose.position = Point(x=center[0], y=center[1], z=center[2] + LABEL_HEIGHT)
            for marker in (outline, direction, label):
                marker.pose.orientation.w = 1.0

            markers.markers += [outline, direction, label]

        self.fiducial_marker_publisher.publish(markers)

    def publish_projection_area(self):
        corners = self.projection_corners
        if corners is None:
            return
        # The corners are pixels of one camera resolution; at another one they point elsewhere
        if self.camera_info is not None and (
                (corners.image_width, corners.image_height)
                != (self.camera_info.width, self.camera_info.height)):
            self.get_logger().warning(
                f'Projection corners were selected at {corners.image_width}x'
                f'{corners.image_height}, the camera runs at {self.camera_info.width}x'
                f'{self.camera_info.height}: select them again',
                throttle_duration_sec=WARNING_PERIOD_SEC)
            return
        projection = self.__projection(corners.header.frame_id, 'the projection area')
        if projection is None:
            return

        pixels = [(getattr(corners, name).x, getattr(corners, name).y) for name in CORNER_NAMES]
        hits = pixels_to_table(pixels, *projection)
        if len(hits) < len(CORNER_NAMES):
            self.get_logger().warning(
                'Not all projection corners hit the table plane, the area is not shown',
                throttle_duration_sec=WARNING_PERIOD_SEC)
            return
        points = [Point(x=x, y=y, z=AREA_HEIGHT) for x, y, _ in hits]
        header = Header(stamp=self.get_clock().now().to_msg(), frame_id=TABLE_FRAME)

        outline = Marker(header=header, ns='projection_area', id=0, type=Marker.LINE_STRIP,
                         color=AREA_OUTLINE_COLOR, points=points + points[:1])
        outline.scale.x = LINE_WIDTH
        # The quadrilateral as the two triangles top_left, top_right, bottom_right and
        # top_left, bottom_right, bottom_left
        fill = Marker(header=header, ns='projection_area', id=1, type=Marker.TRIANGLE_LIST,
                      color=AREA_FILL_COLOR,
                      points=[points[0], points[1], points[2], points[0], points[2], points[3]])
        fill.scale.x = fill.scale.y = fill.scale.z = 1.0
        for marker in (outline, fill):
            marker.pose.orientation.w = 1.0
        self.area_marker_publisher.publish(MarkerArray(markers=[outline, fill]))

    def __projection(self, frame_id, what):
        """Return (k, d, rotation, translation) for pixels_to_table, or None with a warning."""
        # Uncalibrated, the camera matrix is all zeros and pixels have no direction
        if self.camera_info is None or self.camera_info.k[0] == 0.0:
            self.get_logger().warning(
                f'No calibrated camera info on {TOPIC_NAME_CAMERA_INFO} yet, {what} not shown',
                throttle_duration_sec=WARNING_PERIOD_SEC)
            return None
        # Intrinsics of another camera than the one that saw the pixels, e.g. a missing remapping
        if self.camera_info.header.frame_id != frame_id:
            self.get_logger().warning(
                f'camera_info is for frame {self.camera_info.header.frame_id}, but the pixels of '
                f'{what} are in frame {frame_id}: wrong intrinsics?',
                throttle_duration_sec=WARNING_PERIOD_SEC)
        # The transform is static, so the latest one (Time()) is also the one at the image's
        # capture time
        try:
            transform = self.tf_buffer.lookup_transform(TABLE_FRAME, frame_id, Time())
        except TransformException as e:
            self.get_logger().warning(
                f'No transform {TABLE_FRAME} <- {frame_id} yet, {what} not shown: {e}',
                throttle_duration_sec=WARNING_PERIOD_SEC)
            return None

        q = transform.transform.rotation
        t = transform.transform.translation
        return (np.reshape(self.camera_info.k, (3, 3)), np.array(self.camera_info.d),
                rotation_matrix(q.x, q.y, q.z, q.w), np.array([t.x, t.y, t.z]))


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
