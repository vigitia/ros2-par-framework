# Written by Claude Code
"""Own the projection corners: load them at startup, publish them latched, store new ones."""

from custom_interfaces.msg import ProjectionCorners
from custom_interfaces.srv import SetProjectionCorners
from geometry_msgs.msg import Point
from rcl_interfaces.msg import ParameterDescriptor
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

from .projection_corners import CORNERS, load, save, validate

NODE_NAME = 'projection_corners_node'
TOPIC_NAME_CORNERS = '/projection_corners'
SERVICE_NAME_SET_CORNERS = '/set_projection_corners'
PARAMETER_FILE = 'projection_corners_file'

# Latched like /tf_static: the corners change rarely, and a node that starts later still gets the
# last value. Subscribers must request Transient Local too, or they only receive the next change.
LATCHED_QOS = QoSProfile(reliability=QoSReliabilityPolicy.RELIABLE,
                         durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
                         history=QoSHistoryPolicy.KEEP_LAST,
                         depth=1)


class ProjectionCornersNode(Node):
    """Holds the projection corners the way the camera node holds its calibration."""

    def __init__(self):
        super().__init__(NODE_NAME)
        self.declare_parameter(PARAMETER_FILE, '', ParameterDescriptor(
            description='YAML file the corners are loaded from and saved to. The launch files '
                        'put it next to par_setup.yaml.',
            read_only=True))
        self.file = self.get_parameter(PARAMETER_FILE).value
        if not self.file:
            raise RuntimeError(f'Parameter {PARAMETER_FILE} is not set, start the node through '
                               f'par.launch.py or calibration.launch.py')

        self.publisher = self.create_publisher(ProjectionCorners, TOPIC_NAME_CORNERS, LATCHED_QOS)
        self.create_service(SetProjectionCorners, SERVICE_NAME_SET_CORNERS, self.on_set_corners)

        corners = load(self.file)
        if corners is None:
            self.get_logger().info(f'No projection corners in {self.file} yet, select them with '
                                   f'surface_selector')
            return
        error = validate(corners)
        if error:
            self.get_logger().error(f'Ignoring the corners in {self.file}: {error}')
            return
        self.get_logger().info(f'Loaded projection corners from {self.file}')
        self.publisher.publish(self.to_msg(corners))

    def on_set_corners(self, request, response):
        corners = self.to_dict(request.corners)
        error = validate(corners)
        if error is None:
            try:
                save(self.file, corners)
            except OSError as e:
                error = f'could not write {self.file}: {e}'
        if error:
            self.get_logger().error(f'Rejected new projection corners: {error}')
            response.success, response.message = False, error
            return response

        self.get_logger().info(f'Saved new projection corners to {self.file}')
        msg = request.corners
        msg.header.stamp = self.get_clock().now().to_msg()
        self.publisher.publish(msg)
        response.success = True
        return response

    def to_msg(self, corners):
        msg = ProjectionCorners(image_width=corners['image_width'],
                                image_height=corners['image_height'])
        # No image belongs to stored corners: stamp them with the time they are published
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = corners['frame_id']
        for name in CORNERS:
            x, y = corners[name]
            setattr(msg, name, Point(x=float(x), y=float(y)))
        return msg

    @staticmethod
    def to_dict(msg):
        corners = {'frame_id': msg.header.frame_id, 'image_width': msg.image_width,
                   'image_height': msg.image_height}
        for name in CORNERS:
            point = getattr(msg, name)
            corners[name] = [point.x, point.y]
        return corners


def main(args=None):
    rclpy.init(args=args)
    try:
        node = ProjectionCornersNode()
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
