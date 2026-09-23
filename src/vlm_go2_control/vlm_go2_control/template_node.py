"""Provide a basic ROS 2 Python node for custom Go2 control logic."""

import rclpy
from rclpy.node import Node


class VlmGo2ControlNode(Node):
    """Template node for integrating VLM output with Go2 control."""

    def __init__(self) -> None:
        """Initialize the node and its ROS interfaces."""
        # This name is how the node appears in the ROS graph.
        super().__init__('vlm_go2_control')

        # Declare configurable parameters here. Their values can be overridden
        # from a launch file or with ROS command-line arguments.
        self.declare_parameter('update_period', 1.0)
        update_period = self.get_parameter('update_period').value

        # Add publishers, subscriptions, services, or action clients here.
        # Example:
        # self.publisher = self.create_publisher(MessageType, 'topic_name', 10)
        # self.subscription = self.create_subscription(
        #     MessageType, 'topic_name', self.topic_callback, 10)

        # The timer provides a simple location for periodically running your
        # control loop. Remove it if your node will be entirely event-driven.
        self.timer = self.create_timer(update_period, self.control_callback)

        self.get_logger().info('VLM Go2 control node started')

    def control_callback(self) -> None:
        """Run one iteration of the control loop."""
        # TODO: Read your latest inputs, run the VLM/control logic, and publish
        # the resulting Go2 command here.
        pass


def main(args=None) -> None:
    """Initialize ROS 2, run the node, and release resources on shutdown."""
    rclpy.init(args=args)
    node = VlmGo2ControlNode()

    try:
        # Keep processing timers, subscriptions, services, and other callbacks.
        rclpy.spin(node)
    except KeyboardInterrupt:
        # Ctrl+C is a normal way to stop a ROS 2 node during development.
        pass
    finally:
        node.destroy_node()

        # A signal handler may already have shut down the ROS context.
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
