"""Capture and save via the server; the server determines the output directory."""
import argparse
import json
import sys
import rclpy
from rclpy.utilities import remove_ros_args
from go2_vlm_interfaces.srv import CaptureScene


def main(args=None):
    argv = sys.argv if args is None else ['capture_scene', *args]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=10.0)
    options = parser.parse_args(remove_ros_args(argv)[1:])
    if options.timeout <= 0:
        parser.error('--timeout must be positive')
    rclpy.init(args=argv[1:])
    node = rclpy.create_node('scene_capture_client')
    try:
        client = node.create_client(CaptureScene, '/go2_vlm/capture_scene')
        if not client.wait_for_service(timeout_sec=options.timeout):
            raise RuntimeError('capture service unavailable')
        future = client.call_async(CaptureScene.Request(save_image=True))
        rclpy.spin_until_future_complete(node, future, timeout_sec=options.timeout)
        if not future.done():
            raise RuntimeError('capture request timed out; the server may still complete it')
        response = future.result()
        if not response.success:
            raise RuntimeError(response.error_message)
        print(json.dumps({'scene_id': response.scene_id, 'saved_path': response.saved_path,
                          'frame_id': response.frame_id,
                          'image_stamp': {'sec': response.image_stamp.sec,
                                          'nanosec': response.image_stamp.nanosec}}))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        node.destroy_node()
        rclpy.shutdown()
