# Written by Claude Code
"""Own the table-to-projector mapping: load it, publish it latched, store new ones."""

from custom_interfaces.msg import ProjectionMapping
from custom_interfaces.srv import SetProjectionMapping
from rcl_interfaces.msg import ParameterDescriptor
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

from .projection_mapping import load, save, validate

NODE_NAME = 'projection_mapping_node'
TOPIC_NAME_MAPPING = '/projection_mapping'
SERVICE_NAME_SET_MAPPING = '/set_projection_mapping'
PARAMETER_FILE = 'projection_mapping_file'

# Latched like /tf_static: the mapping changes rarely, and a node that starts later still gets
# the last value. Subscribers must request Transient Local too, or they only receive the next
# change.
LATCHED_QOS = QoSProfile(reliability=QoSReliabilityPolicy.RELIABLE,
                         durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
                         history=QoSHistoryPolicy.KEEP_LAST, depth=1)


class ProjectionMappingNode(Node):
    """Holds the table-to-projector homography the way the camera node holds its calibration."""

    def __init__(self):
        super().__init__(NODE_NAME)
        self.declare_parameter(PARAMETER_FILE, '', ParameterDescriptor(
            description='YAML file the mapping is loaded from and saved to. The launch files put '
                        'it next to par_setup.yaml.',
            read_only=True))
        self.file = self.get_parameter(PARAMETER_FILE).value
        if not self.file:
            raise RuntimeError(f'Parameter {PARAMETER_FILE} is not set, start the node through '
                               f'a par_framework_core launch file')

        self.publisher = self.create_publisher(ProjectionMapping, TOPIC_NAME_MAPPING, LATCHED_QOS)
        self.create_service(SetProjectionMapping, SERVICE_NAME_SET_MAPPING, self.on_set_mapping)

        mapping = load(self.file)
        if mapping is None:
            self.get_logger().info(f'No projection mapping in {self.file} yet, calibrate with '
                                   f'projection_calibration.launch.py')
            return
        error = validate(mapping)
        if error:
            self.get_logger().error(f'Ignoring the mapping in {self.file}: {error}')
            return
        self.get_logger().info(f'Loaded projection mapping from {self.file}')
        self.publisher.publish(self.to_msg(mapping))

    def on_set_mapping(self, request, response):
        mapping = self.to_dict(request.mapping)
        error = validate(mapping)
        if error is None:
            try:
                save(self.file, mapping)
            except OSError as e:
                error = f'could not write {self.file}: {e}'
        if error:
            self.get_logger().error(f'Rejected new projection mapping: {error}')
            response.success, response.message = False, error
            return response

        self.get_logger().info(f'Saved new projection mapping to {self.file} (reprojection error '
                               f'{mapping["reprojection_error"]:.2f} px)')
        msg = request.mapping
        msg.header.stamp = self.get_clock().now().to_msg()
        self.publisher.publish(msg)
        response.success = True
        return response

    def to_msg(self, mapping):
        msg = ProjectionMapping(projector_width=mapping['projector_width'],
                                projector_height=mapping['projector_height'],
                                homography=[float(v) for row in mapping['homography']
                                            for v in row],
                                reprojection_error=float(mapping['reprojection_error']))
        # No image belongs to a stored mapping: stamp it with the time it is published
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = mapping['frame_id']
        return msg

    @staticmethod
    def to_dict(msg):
        values = [float(v) for v in msg.homography]
        return {'frame_id': msg.header.frame_id,
                'projector_width': msg.projector_width,
                'projector_height': msg.projector_height,
                'homography': [values[0:3], values[3:6], values[6:9]],
                'reprojection_error': float(msg.reprojection_error)}


def main(args=None):
    rclpy.init(args=args)
    try:
        node = ProjectionMappingNode()
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
