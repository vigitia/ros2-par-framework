# Written by Claude Code
"""Republish framework outputs as RViz markers: objects, hands, fiducials, pages, projection."""

from geometry_msgs.msg import Point
import numpy as np
from par_framework_interfaces.msg import (FiducialsList, HandLandmarksList, ObjectList, PageList,
                                          ProjectionCorners, ProjectionMapping)
from par_geometry import (homography_from_msg, pixels_to_table, projector_to_table,
                          quaternion_to_rotation_matrix)
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
TOPIC_NAME_CAMERA_INFO = '/camera/camera_info'
TOPIC_NAME_PROJECTION_CORNERS = '/projection_corners'
TOPIC_NAME_OBJECT_MARKERS = '/objects/markers'
TOPIC_NAME_PROJECTION_MARKERS = '/projection_corners/markers'
TOPIC_NAME_HANDS = '/hand_landmarks'
TOPIC_NAME_HAND_MARKERS = '/hand_landmarks/markers'
TOPIC_NAME_FIDUCIALS = '/fiducials'
TOPIC_NAME_FIDUCIAL_MARKERS = '/fiducials/markers'
TOPIC_NAME_PAGES = '/pages'
TOPIC_NAME_PAGE_MARKERS = '/pages/markers'
TOPIC_NAME_PROJECTION_MAPPING = '/projection_mapping'
TOPIC_NAME_MAPPING_MARKERS = '/projection_mapping/markers'
# The tabletop is the plane z = 0 of this frame
TABLE_FRAME_ID = 'world'
# The corner fields of a ProjectionCorners message, in drawing order
PROJECTION_CORNER_FIELD_NAMES = ('top_left', 'top_right', 'bottom_right', 'bottom_left')

# Outlines are lifted slightly, so they don't flicker into the RViz grid; labels float above
# the object
OUTLINE_HEIGHT_M = 0.002
LABEL_HEIGHT_M = 0.05
LINE_WIDTH_M = 0.005
# Height of an upper-case letter, which is what a text marker's scale.z sets
TEXT_HEIGHT_M = 0.04
# Diameter of the sphere at an object's measured centre (center_3d)
OBJECT_CENTER_DIAMETER_M = 0.015
OBJECT_OUTLINE_COLOR = ColorRGBA(r=0.1, g=0.9, b=0.2, a=1.0)
LABEL_COLOR = ColorRGBA(r=1.0, g=1.0, b=1.0, a=1.0)
# The projection area lies just below the object outlines, so objects stay visible on top of it
PROJECTION_AREA_HEIGHT_M = 0.001
PROJECTION_AREA_OUTLINE_COLOR = ColorRGBA(r=0.2, g=0.5, b=1.0, a=1.0)
PROJECTION_AREA_FILL_COLOR = ColorRGBA(r=0.2, g=0.5, b=1.0, a=0.25)
# The calibrated projector outline, between the clicked area and the object outlines
PROJECTOR_OUTLINE_HEIGHT_M = 0.0015
PROJECTOR_COLOR = ColorRGBA(r=1.0, g=0.2, b=0.8, a=1.0)
# Diameter of the sphere at the projector's optical centre, from which the light cone starts
PROJECTOR_CENTER_DIAMETER_M = 0.03
# Hands are drawn where their landmarks' camera rays hit the table, like a shadow straight below
# the camera, just above the object outlines
HAND_HEIGHT_M = 0.003
HAND_JOINT_DIAMETER_M = 0.008
HAND_COLORS = {'Left': ColorRGBA(r=1.0, g=0.6, b=0.1, a=1.0),
               'Right': ColorRGBA(r=0.9, g=0.2, b=0.9, a=1.0)}
NUM_HAND_LANDMARKS = 21
# Pairs of landmark ids forming the bones, as mediapipe's
# HandLandmarksConnections.HAND_CONNECTIONS; copied, so rviz_bridge does not need mediapipe
# just for this list
HAND_CONNECTIONS = ((0, 1), (1, 2), (2, 3), (3, 4),  # thumb
                    (0, 5), (5, 6), (6, 7), (7, 8),  # index finger
                    (9, 10), (10, 11), (11, 12),  # middle finger
                    (13, 14), (14, 15), (15, 16),  # ring finger
                    (0, 17), (17, 18), (18, 19), (19, 20),  # pinky
                    (5, 9), (9, 13), (13, 17))  # palm
# Fiducials lie flat on the table like the objects; yellow, as orange is the left hand
FIDUCIAL_COLOR = ColorRGBA(r=1.0, g=0.85, b=0.1, a=1.0)
# Pages lie on the table, just below the fiducials printed on them
PAGE_HEIGHT_M = 0.0018
PAGE_COLOR = ColorRGBA(r=0.1, g=0.9, b=0.9, a=1.0)
# The corners and the mapping arrive once, the camera calibration and TF possibly later: the
# projection area and the projector outline are redrawn periodically
CALIBRATION_REDRAW_INTERVAL_SEC = 1.0
WARNING_THROTTLE_PERIOD_SEC = 5.0

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

        self._create_subscriptions()
        self._create_publishers()

        # Periodically send projection_area and projector_outline
        self.create_timer(CALIBRATION_REDRAW_INTERVAL_SEC, self.publish_projection_area)
        self.create_timer(CALIBRATION_REDRAW_INTERVAL_SEC, self.publish_projector_outline)

    def _create_subscriptions(self):
        self.create_subscription(CameraInfo, TOPIC_NAME_CAMERA_INFO, self.on_camera_info,
                                 CAMERA_INFO_QOS)
        self.create_subscription(ObjectList, TOPIC_NAME_OBJECTS, self.on_objects, QUEUE_SIZE)
        self.create_subscription(ProjectionCorners, TOPIC_NAME_PROJECTION_CORNERS,
                                 self.on_projection_corners, LATCHED_QOS)
        self.create_subscription(HandLandmarksList, TOPIC_NAME_HANDS, self.on_hands, QUEUE_SIZE)
        self.create_subscription(FiducialsList, TOPIC_NAME_FIDUCIALS, self.on_fiducials,
                                 QUEUE_SIZE)
        self.create_subscription(PageList, TOPIC_NAME_PAGES, self.on_pages, QUEUE_SIZE)
        self.create_subscription(ProjectionMapping, TOPIC_NAME_PROJECTION_MAPPING,
                                 self.on_projection_mapping, LATCHED_QOS)

    def _create_publishers(self):
        self.fiducial_marker_publisher = self.create_publisher(MarkerArray,
                                                               TOPIC_NAME_FIDUCIAL_MARKERS,
                                                               QUEUE_SIZE)
        self.page_marker_publisher = self.create_publisher(MarkerArray, TOPIC_NAME_PAGE_MARKERS,
                                                           QUEUE_SIZE)
        self.hand_marker_publisher = self.create_publisher(MarkerArray, TOPIC_NAME_HAND_MARKERS,
                                                           QUEUE_SIZE)
        self.object_marker_publisher = self.create_publisher(MarkerArray,
                                                             TOPIC_NAME_OBJECT_MARKERS,
                                                             QUEUE_SIZE)
        self.area_marker_publisher = self.create_publisher(MarkerArray,
                                                           TOPIC_NAME_PROJECTION_MARKERS,
                                                           QUEUE_SIZE)
        self.mapping_marker_publisher = self.create_publisher(MarkerArray,
                                                              TOPIC_NAME_MAPPING_MARKERS,
                                                              QUEUE_SIZE)

    def on_camera_info(self, msg):
        self.camera_info = msg

    def on_projection_corners(self, msg):
        self.projection_corners = msg
        self.publish_projection_area()

    def on_projection_mapping(self, msg):
        self.projection_mapping = msg
        self.publish_projector_outline()

    # Co-authored by Claude Code: the projector's optical centre and its light cone
    def publish_projector_outline(self):
        """Draw where the calibrated projector image lies on the table, and the projector."""
        mapping = self.projection_mapping
        if mapping is None:
            return
        width_px = mapping.projector_width
        height_px = mapping.projector_height
        image_corners_px = [(0, 0), (width_px, 0), (width_px, height_px), (0, height_px)]
        # The projector's corners back onto the table: no camera needed, only the mapping
        table_corners_m = projector_to_table(homography_from_msg(mapping), image_corners_px)
        corner_points = [Point(x=x, y=y, z=PROJECTOR_OUTLINE_HEIGHT_M)
                         for x, y in table_corners_m]
        header = Header(stamp=self.get_clock().now().to_msg(), frame_id=mapping.header.frame_id)
        outline_marker = Marker(header=header, ns='projector_outline', id=0,
                                type=Marker.LINE_STRIP, color=PROJECTOR_COLOR,
                                points=corner_points + corner_points[:1])
        outline_marker.scale.x = LINE_WIDTH_M
        center_marker = Marker(header=header, ns='projector_center', id=0, type=Marker.SPHERE,
                               color=PROJECTOR_COLOR)
        center_marker.scale.x = PROJECTOR_CENTER_DIAMETER_M
        center_marker.scale.y = PROJECTOR_CENTER_DIAMETER_M
        center_marker.scale.z = PROJECTOR_CENTER_DIAMETER_M
        # One line from the optical centre to each image corner: the edges of the light cone
        cone_marker = Marker(header=header, ns='projector_cone', id=0, type=Marker.LINE_LIST,
                             color=PROJECTOR_COLOR)
        cone_marker.scale.x = LINE_WIDTH_M
        if mapping.projector_center_valid:
            center_marker.pose.position = mapping.projector_center
            for corner_point in corner_points:
                cone_marker.points.append(mapping.projector_center)
                cone_marker.points.append(corner_point)
        else:
            # Without a calibrated centre, one shown for an earlier mapping must go
            center_marker.action = Marker.DELETE
            cone_marker.action = Marker.DELETE
        projector_markers = [outline_marker, center_marker, cone_marker]
        for marker in projector_markers:
            marker.pose.orientation.w = 1.0
        self.mapping_marker_publisher.publish(MarkerArray(markers=projector_markers))

    def on_objects(self, msg):
        camera_parameters = self._get_camera_parameters(msg.header.frame_id, 'objects')
        if camera_parameters is None:
            return

        markers = MarkerArray()
        # Removes the previous frame's markers first, so objects that are gone disappear
        markers.markers.append(Marker(action=Marker.DELETEALL))
        header = Header(stamp=msg.header.stamp, frame_id=TABLE_FRAME_ID)
        for detected_object in msg.objects:
            object_id = detected_object.object_id
            if detected_object.hull_contour_3d:
                # Measured with a depth camera (object_detector with use_depth): the top outline
                # drawn where it is, moved from the optical frame into the table frame
                _, _, rotation, translation_m = camera_parameters
                hull_camera_m = np.array([(point.x, point.y, point.z)
                                          for point in detected_object.hull_contour_3d])
                outline_table_m = hull_camera_m @ rotation.T + translation_m
                # The centre of its top, where its depth was measured
                center_3d = detected_object.center_3d
                center_camera_m = np.array([center_3d.x, center_3d.y, center_3d.z])
                x, y, z = center_camera_m @ rotation.T + translation_m
                center_marker = Marker(header=header, ns='center', id=object_id,
                                       type=Marker.SPHERE, color=OBJECT_OUTLINE_COLOR)
                center_marker.scale.x = OBJECT_CENTER_DIAMETER_M
                center_marker.scale.y = OBJECT_CENTER_DIAMETER_M
                center_marker.scale.z = OBJECT_CENTER_DIAMETER_M
                center_marker.pose.position = Point(x=x, y=y, z=z)
                center_marker.pose.orientation.w = 1.0
                markers.markers.append(center_marker)
            else:
                # The hull has far fewer points than the contour and is enough for an outline
                if detected_object.hull_contour:
                    contour_points = detected_object.hull_contour
                else:
                    contour_points = detected_object.contour
                outline_pixels = [(point.x, point.y) for point in contour_points]
                if not outline_pixels:
                    outline_pixels = [(detected_object.center_x, detected_object.center_y)]
                outline_table_m = pixels_to_table(outline_pixels, *camera_parameters)
                if len(outline_table_m) == 0:
                    continue
                outline_table_m[:, 2] = OUTLINE_HEIGHT_M

            outline_marker = Marker(header=header, ns='outline', id=object_id,
                                    type=Marker.LINE_STRIP, color=OBJECT_OUTLINE_COLOR)
            outline_marker.scale.x = LINE_WIDTH_M
            # Repeating the first point closes the outline
            closed_outline_m = np.vstack([outline_table_m, outline_table_m[:1]])
            outline_marker.points = [Point(x=x, y=y, z=z) for x, y, z in closed_outline_m]

            label_anchor_m = outline_table_m.mean(axis=0)
            label_marker = Marker(header=header, ns='label', id=object_id,
                                  type=Marker.TEXT_VIEW_FACING, color=LABEL_COLOR,
                                  # No space: RViz draws it far too wide at this text size
                                  text=f'{detected_object.class_name}#{object_id}')
            label_marker.scale.z = TEXT_HEIGHT_M
            label_marker.pose.position = Point(x=label_anchor_m[0], y=label_anchor_m[1],
                                               z=label_anchor_m[2] + LABEL_HEIGHT_M)
            label_marker.pose.orientation.w = 1.0

            markers.markers += [outline_marker, label_marker]

        self.object_marker_publisher.publish(markers)

    def on_hands(self, msg):
        camera_parameters = self._get_camera_parameters(msg.header.frame_id, 'hands')
        if camera_parameters is None:
            return

        markers = MarkerArray()
        # Removes the previous frame's markers first, so hands that are gone disappear
        markers.markers.append(Marker(action=Marker.DELETEALL))
        header = Header(stamp=msg.header.stamp, frame_id=TABLE_FRAME_ID)
        for hand in msg.hands:
            # One entry per landmark, None where it has no position
            if len(hand.hand_landmarks_3d) == NUM_HAND_LANDMARKS:
                # Measured with a depth camera (hand_landmarks with use_depth): drawn where they
                # are, moved from the optical frame into the table frame
                _, _, rotation, translation_m = camera_parameters
                landmarks_camera_m = np.array([(landmark.x, landmark.y, landmark.z)
                                               for landmark in hand.hand_landmarks_3d])
                landmarks_table_m = landmarks_camera_m @ rotation.T + translation_m
                landmark_points = []
                for (x, y, z), depth_m in zip(landmarks_table_m, landmarks_camera_m[:, 2]):
                    # z <= 0 (in front of the camera is z > 0): -1, -1, -1 marks "no depth"
                    if depth_m > 0:
                        landmark_points.append(Point(x=x, y=y, z=z))
                    else:
                        landmark_points.append(None)
            else:
                landmark_pixels = [(landmark.x, landmark.y) for landmark in hand.hand_landmarks]
                landmarks_table_m = pixels_to_table(landmark_pixels, *camera_parameters)
                # Rays that miss the table are dropped, which would shift the ids the bones
                # refer to
                if len(landmarks_table_m) != NUM_HAND_LANDMARKS:
                    continue
                landmark_points = [Point(x=x, y=y, z=HAND_HEIGHT_M)
                                   for x, y, _ in landmarks_table_m]
            positioned_points = [point for point in landmark_points if point is not None]
            if not positioned_points:
                continue
            hand_color = HAND_COLORS.get(hand.handedness, LABEL_COLOR)

            joints_marker = Marker(header=header, ns='hand_joints', id=hand.id,
                                   type=Marker.SPHERE_LIST, color=hand_color,
                                   points=positioned_points)
            joints_marker.scale.x = HAND_JOINT_DIAMETER_M
            joints_marker.scale.y = HAND_JOINT_DIAMETER_M
            joints_marker.scale.z = HAND_JOINT_DIAMETER_M
            # LINE_LIST draws one line per pair of points; bones to a landmark without a position
            # are left out
            bone_points = []
            for start_id, end_id in HAND_CONNECTIONS:
                start_point = landmark_points[start_id]
                end_point = landmark_points[end_id]
                if start_point is not None and end_point is not None:
                    bone_points += [start_point, end_point]
            bones_marker = Marker(header=header, ns='hand_bones', id=hand.id,
                                  type=Marker.LINE_LIST, color=hand_color, points=bone_points)
            bones_marker.scale.x = LINE_WIDTH_M
            # Above the wrist (landmark 0), or the first landmark with a position
            if landmark_points[0] is not None:
                label_anchor = landmark_points[0]
            else:
                label_anchor = positioned_points[0]
            label_marker = Marker(header=header, ns='hand_label', id=hand.id,
                                  type=Marker.TEXT_VIEW_FACING, color=LABEL_COLOR,
                                  text=f'{hand.handedness}#{hand.id}')
            label_marker.scale.z = TEXT_HEIGHT_M
            label_marker.pose.position = Point(x=label_anchor.x, y=label_anchor.y,
                                               z=label_anchor.z + LABEL_HEIGHT_M)
            hand_markers = [joints_marker, bones_marker, label_marker]
            for marker in hand_markers:
                marker.pose.orientation.w = 1.0

            markers.markers += hand_markers

        self.hand_marker_publisher.publish(markers)

    def on_fiducials(self, msg):
        camera_parameters = self._get_camera_parameters(msg.header.frame_id, 'fiducials')
        if camera_parameters is None:
            return

        markers = MarkerArray()
        # Removes the previous frame's markers first, so fiducials that are gone disappear
        markers.markers.append(Marker(action=Marker.DELETEALL))
        header = Header(stamp=msg.header.stamp, frame_id=TABLE_FRAME_ID)
        for fiducial in msg.fiducials:
            # OpenCV's corner order: clockwise from the marker's top left
            if len(fiducial.corners_3d) == 4:
                # Measured with a depth camera (fiducials_detector with use_depth): drawn where
                # the marker is, moved from the optical frame into the table frame
                _, _, rotation, translation_m = camera_parameters
                corners_camera_m = np.array([(point.x, point.y, point.z)
                                             for point in fiducial.corners_3d])
                corners_table_m = corners_camera_m @ rotation.T + translation_m
            else:
                corner_pixels = [(fiducial.x0, fiducial.y0), (fiducial.x1, fiducial.y1),
                                 (fiducial.x2, fiducial.y2), (fiducial.x3, fiducial.y3)]
                corners_table_m = pixels_to_table(corner_pixels, *camera_parameters)
                # Rays that miss the table are dropped, which would shift which corner is which
                if len(corners_table_m) != len(corner_pixels):
                    continue
                corners_table_m[:, 2] = OUTLINE_HEIGHT_M
            corner_points = [Point(x=x, y=y, z=z) for x, y, z in corners_table_m]
            center_m = corners_table_m.mean(axis=0)

            outline_marker = Marker(header=header, ns='fiducial_outline', id=fiducial.id,
                                    type=Marker.LINE_STRIP, color=FIDUCIAL_COLOR,
                                    points=corner_points + corner_points[:1])
            outline_marker.scale.x = LINE_WIDTH_M
            # From the centre to the middle of the first edge, the marker's top: shows its
            # rotation, the same edge fiducials_detector computes its angle from
            top_edge_middle_m = (corners_table_m[0] + corners_table_m[1]) / 2
            direction_points = [Point(x=center_m[0], y=center_m[1], z=center_m[2]),
                                Point(x=top_edge_middle_m[0], y=top_edge_middle_m[1],
                                      z=top_edge_middle_m[2])]
            direction_marker = Marker(header=header, ns='fiducial_direction', id=fiducial.id,
                                      type=Marker.LINE_LIST, color=FIDUCIAL_COLOR,
                                      points=direction_points)
            direction_marker.scale.x = LINE_WIDTH_M
            label_marker = Marker(header=header, ns='fiducial_label', id=fiducial.id,
                                  type=Marker.TEXT_VIEW_FACING, color=LABEL_COLOR,
                                  # No space: RViz draws it far too wide at this text size
                                  text=f'#{fiducial.id}')
            label_marker.scale.z = TEXT_HEIGHT_M
            label_marker.pose.position = Point(x=center_m[0], y=center_m[1],
                                               z=center_m[2] + LABEL_HEIGHT_M)
            fiducial_markers = [outline_marker, direction_marker, label_marker]
            for marker in fiducial_markers:
                marker.pose.orientation.w = 1.0

            markers.markers += fiducial_markers

        self.fiducial_marker_publisher.publish(markers)

    def on_pages(self, msg):
        camera_parameters = self._get_camera_parameters(msg.header.frame_id, 'pages')
        if camera_parameters is None:
            return

        markers = MarkerArray()
        # Removes the previous frame's markers first, so pages that are gone disappear
        markers.markers.append(Marker(action=Marker.DELETEALL))
        header = Header(stamp=msg.header.stamp, frame_id=TABLE_FRAME_ID)
        for page in msg.pages:
            # Paper lies on the table, so the table plane is where its corners are, with or
            # without a depth camera
            corner_pixels = [(page.x0, page.y0), (page.x1, page.y1), (page.x2, page.y2),
                             (page.x3, page.y3)]
            corners_table_m = pixels_to_table(corner_pixels, *camera_parameters)
            # Rays that miss the table are dropped, which would shift which corner is which
            if len(corners_table_m) != len(corner_pixels):
                continue
            corners_table_m[:, 2] = PAGE_HEIGHT_M
            corner_points = [Point(x=x, y=y, z=z) for x, y, z in corners_table_m]
            center_m = corners_table_m.mean(axis=0)

            outline_marker = Marker(header=header, ns='page_outline', id=page.id,
                                    type=Marker.LINE_STRIP, color=PAGE_COLOR,
                                    points=corner_points + corner_points[:1])
            outline_marker.scale.x = LINE_WIDTH_M
            label_marker = Marker(header=header, ns='page_label', id=page.id,
                                  type=Marker.TEXT_VIEW_FACING, color=LABEL_COLOR,
                                  # No space: RViz draws it far too wide at this text size
                                  text=f'page#{page.id}')
            label_marker.scale.z = TEXT_HEIGHT_M
            label_marker.pose.position = Point(x=center_m[0], y=center_m[1],
                                               z=center_m[2] + LABEL_HEIGHT_M)
            page_markers = [outline_marker, label_marker]
            for marker in page_markers:
                marker.pose.orientation.w = 1.0

            markers.markers += page_markers

        self.page_marker_publisher.publish(markers)

    def publish_projection_area(self):
        corners = self.projection_corners
        if corners is None:
            return
        # The corners are pixels of one camera resolution; at another one they point elsewhere
        camera_info = self.camera_info
        if camera_info is not None:
            corners_resolution_px = (corners.image_width, corners.image_height)
            camera_resolution_px = (camera_info.width, camera_info.height)
            if corners_resolution_px != camera_resolution_px:
                self.get_logger().warning(
                    f'Projection corners were selected at {corners.image_width}x'
                    f'{corners.image_height}, the camera runs at {camera_info.width}x'
                    f'{camera_info.height}: select them again',
                    throttle_duration_sec=WARNING_THROTTLE_PERIOD_SEC)
                return
        camera_parameters = self._get_camera_parameters(corners.header.frame_id,
                                                        'the projection area')
        if camera_parameters is None:
            return

        corner_pixels = []
        for field_name in PROJECTION_CORNER_FIELD_NAMES:
            corner = getattr(corners, field_name)
            corner_pixels.append((corner.x, corner.y))
        corners_table_m = pixels_to_table(corner_pixels, *camera_parameters)
        if len(corners_table_m) < len(PROJECTION_CORNER_FIELD_NAMES):
            self.get_logger().warning(
                'Not all projection corners hit the table plane, the area is not shown',
                throttle_duration_sec=WARNING_THROTTLE_PERIOD_SEC)
            return
        corner_points = [Point(x=x, y=y, z=PROJECTION_AREA_HEIGHT_M)
                         for x, y, _ in corners_table_m]
        header = Header(stamp=self.get_clock().now().to_msg(), frame_id=TABLE_FRAME_ID)

        outline_marker = Marker(header=header, ns='projection_area', id=0,
                                type=Marker.LINE_STRIP, color=PROJECTION_AREA_OUTLINE_COLOR,
                                points=corner_points + corner_points[:1])
        outline_marker.scale.x = LINE_WIDTH_M
        # The quadrilateral as the two triangles top_left, top_right, bottom_right and
        # top_left, bottom_right, bottom_left
        top_left, top_right, bottom_right, bottom_left = corner_points
        triangle_points = [top_left, top_right, bottom_right, top_left, bottom_right, bottom_left]
        fill_marker = Marker(header=header, ns='projection_area', id=1,
                             type=Marker.TRIANGLE_LIST, color=PROJECTION_AREA_FILL_COLOR,
                             points=triangle_points)
        fill_marker.scale.x = 1.0
        fill_marker.scale.y = 1.0
        fill_marker.scale.z = 1.0
        area_markers = [outline_marker, fill_marker]
        for marker in area_markers:
            marker.pose.orientation.w = 1.0
        self.area_marker_publisher.publish(MarkerArray(markers=area_markers))

    def _get_camera_parameters(self, frame_id, subject):
        """
        Return (camera_matrix, distortion_coefficients, rotation, translation_m) or None.

        The tuple is what pixels_to_table takes after the pixels; subject names what is not shown
        in the warning when the camera calibration or the transform is missing.
        """
        camera_info = self.camera_info
        # Uncalibrated, the camera matrix is all zeros and pixels have no direction
        if camera_info is None or camera_info.k[0] == 0.0:
            self.get_logger().warning(
                f'No calibrated camera info on {TOPIC_NAME_CAMERA_INFO} yet, {subject} not shown',
                throttle_duration_sec=WARNING_THROTTLE_PERIOD_SEC)
            return None
        # Intrinsics of another camera than the one that saw the pixels, e.g. a missing remapping
        if camera_info.header.frame_id != frame_id:
            self.get_logger().warning(
                f'camera_info is for frame {camera_info.header.frame_id}, but the pixels of '
                f'{subject} are in frame {frame_id}: wrong intrinsics?',
                throttle_duration_sec=WARNING_THROTTLE_PERIOD_SEC)
        # The transform is static, so the latest one (Time()) is also the one at the image's
        # capture time
        try:
            transform = self.tf_buffer.lookup_transform(TABLE_FRAME_ID, frame_id, Time())
        except TransformException as error:
            self.get_logger().warning(
                f'No transform {TABLE_FRAME_ID} <- {frame_id} yet, {subject} not shown: {error}',
                throttle_duration_sec=WARNING_THROTTLE_PERIOD_SEC)
            return None

        rotation_quaternion = transform.transform.rotation
        translation = transform.transform.translation
        camera_matrix = np.reshape(camera_info.k, (3, 3))
        distortion_coefficients = np.array(camera_info.d)
        rotation = quaternion_to_rotation_matrix(rotation_quaternion.x, rotation_quaternion.y,
                                                 rotation_quaternion.z, rotation_quaternion.w)
        translation_m = np.array([translation.x, translation.y, translation.z])
        return camera_matrix, distortion_coefficients, rotation, translation_m


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
