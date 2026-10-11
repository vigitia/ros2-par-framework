# Written by Claude Code
"""
Own the projection calibrations: load them at startup, publish them latched, store new ones.

Two calibrations, each with its own file, latched topic and set service: the projection corners
clicked in surface_selector, and the table-to-projector mapping fitted by projection_calibrator.
"""

from collections import namedtuple

from custom_interfaces.msg import ProjectionCorners, ProjectionMapping
from custom_interfaces.srv import SetProjectionCorners, SetProjectionMapping
from geometry_msgs.msg import Point
from rcl_interfaces.msg import ParameterDescriptor
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

from .projection_calibration_server import (CORNERS, load, save_corners, save_mapping,
                                            validate_corners, validate_mapping)

NODE_NAME = 'projection_calibration_server_node'
TOPIC_NAME_CORNERS = '/projection_corners'
TOPIC_NAME_MAPPING = '/projection_mapping'
SERVICE_NAME_SET_CORNERS = '/set_projection_corners'
SERVICE_NAME_SET_MAPPING = '/set_projection_mapping'
PARAMETER_CORNERS_FILE = 'projection_corners_file'
PARAMETER_MAPPING_FILE = 'projection_mapping_file'

# Latched like /tf_static: the calibrations change rarely, and a node that starts later still gets
# the last value. Subscribers must request Transient Local too, or they only receive the next
# change.
LATCHED_QOS = QoSProfile(reliability=QoSReliabilityPolicy.RELIABLE,
                         durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
                         history=QoSHistoryPolicy.KEEP_LAST, depth=1)

# What differs between the calibrations: a name for the log, the file, how to check, store and
# convert it, and the publisher of its latched topic
Calibration = namedtuple('Calibration', 'what path validate save to_msg to_dict publisher')


class ProjectionCalibrationServerNode(Node):
    """Holds the projection calibrations the way the camera node holds its calibration."""

    def __init__(self):
        super().__init__(NODE_NAME)
        self.corners = Calibration(
            'projection corners', self.file_parameter(PARAMETER_CORNERS_FILE, 'corners'),
            validate_corners, save_corners, corners_to_msg, corners_to_dict,
            self.create_publisher(ProjectionCorners, TOPIC_NAME_CORNERS, LATCHED_QOS))
        self.mapping = Calibration(
            'projection mapping', self.file_parameter(PARAMETER_MAPPING_FILE, 'mapping'),
            validate_mapping, save_mapping, mapping_to_msg, mapping_to_dict,
            self.create_publisher(ProjectionMapping, TOPIC_NAME_MAPPING, LATCHED_QOS))
        self.create_service(SetProjectionCorners, SERVICE_NAME_SET_CORNERS, self.on_set_corners)
        self.create_service(SetProjectionMapping, SERVICE_NAME_SET_MAPPING, self.on_set_mapping)

        self.publish_stored(self.corners, 'select them with calibration.launch.py')
        self.publish_stored(self.mapping, 'calibrate with projection_calibration.launch.py')

    def file_parameter(self, name, what):
        self.declare_parameter(name, '', ParameterDescriptor(
            description=f'YAML file that stores the projection {what}, loaded at startup and '
                        f'rewritten by its set service. The launch files put it in '
                        f'config/calibration/extrinsics.',
            read_only=True))
        path = self.get_parameter(name).value
        if not path:
            raise RuntimeError(f'Parameter {name} is not set, start the node through a '
                               f'par_framework_core launch file')
        return path

    def publish_stored(self, calibration, hint):
        """Publish the calibration stored in its file, unless there is none or it is unusable."""
        # A hand-edited or truncated file may lack keys or hold the wrong types. That is logged
        # like any other invalid content, so one broken file does not keep the other calibration
        # from being served
        try:
            data = load(calibration.path)
            if data is None:
                self.get_logger().info(f'No {calibration.what} in {calibration.path} yet, {hint}')
                return
            error = calibration.validate(data)
            if error is None:
                msg = calibration.to_msg(data)
        except (OSError, KeyError, TypeError, ValueError) as e:
            error = f'{type(e).__name__}: {e}'
        if error:
            self.get_logger().error(f'Ignoring the {calibration.what} in {calibration.path}: '
                                    f'{error}')
            return
        self.get_logger().info(f'Loaded {calibration.what} from {calibration.path}')
        self.publish(calibration, msg)

    def on_set_corners(self, request, response):
        return self.store(self.corners, request.corners, response)

    def on_set_mapping(self, request, response):
        return self.store(self.mapping, request.mapping, response,
                          f' (reprojection error {request.mapping.reprojection_error:.2f} px)')

    def store(self, calibration, msg, response, note=''):
        """Check and save the calibration in msg, then publish it; answer whether that worked."""
        data = calibration.to_dict(msg)
        error = calibration.validate(data)
        if error is None:
            try:
                calibration.save(calibration.path, data)
            except OSError as e:
                error = f'could not write {calibration.path}: {e}'
        if error:
            self.get_logger().error(f'Rejected new {calibration.what}: {error}')
            response.success, response.message = False, error
            return response

        self.get_logger().info(f'Saved new {calibration.what} to {calibration.path}{note}')
        self.publish(calibration, msg)
        response.success = True
        return response

    def publish(self, calibration, msg):
        # No image belongs to a stored calibration: stamp it with the time it is published
        msg.header.stamp = self.get_clock().now().to_msg()
        calibration.publisher.publish(msg)


def corners_to_msg(corners):
    msg = ProjectionCorners(image_width=corners['image_width'],
                            image_height=corners['image_height'])
    msg.header.frame_id = corners['frame_id']
    for name in CORNERS:
        x, y = corners[name]
        setattr(msg, name, Point(x=float(x), y=float(y)))
    return msg


def corners_to_dict(msg):
    corners = {'frame_id': msg.header.frame_id, 'image_width': msg.image_width,
               'image_height': msg.image_height}
    for name in CORNERS:
        point = getattr(msg, name)
        corners[name] = [point.x, point.y]
    return corners


def mapping_to_msg(mapping):
    msg = ProjectionMapping(projector_width=mapping['projector_width'],
                            projector_height=mapping['projector_height'],
                            homography=[float(v) for row in mapping['homography'] for v in row],
                            reprojection_error=float(mapping['reprojection_error']))
    msg.header.frame_id = mapping['frame_id']
    return msg


def mapping_to_dict(msg):
    values = [float(v) for v in msg.homography]
    return {'frame_id': msg.header.frame_id,
            'projector_width': msg.projector_width,
            'projector_height': msg.projector_height,
            'homography': [values[0:3], values[3:6], values[6:9]],
            'reprojection_error': float(msg.reprojection_error)}


def main(args=None):
    rclpy.init(args=args)
    try:
        node = ProjectionCalibrationServerNode()
    except RuntimeError as e:
        rclpy.logging.get_logger(NODE_NAME).fatal(str(e))
        rclpy.try_shutdown()
        return 1
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
