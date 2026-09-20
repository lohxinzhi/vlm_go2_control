"""Evaluation commands. Default to validation; live inference requires --execute."""
import argparse
import json
import sys
import yaml
from pathlib import Path
from .dataset import DEFAULT_DATASET, SCENE_IDS, init_dataset, save_capture, workspace_dataset, WORKSPACE
from .protocol import dry_run, run_evaluation
from .reporting import write_reports


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', default=str(DEFAULT_DATASET))
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--init', action='store_true')
    action.add_argument('--dry-run', action='store_true')
    action.add_argument('--execute', action='store_true', help='Explicitly authorize twenty logical API queries')
    options = parser.parse_args(args)
    try:
        root = workspace_dataset(options.dataset)
        if options.init:
            init_dataset(root)
            print('Dataset initialized; ground truth requires human image review. No API calls.')
            return
        if options.execute:
            result = run_evaluation(root)
            print('Evaluation finished: ' + result['run_status'])
            return
        report = dry_run(root)
        (root / 'reports').mkdir(parents=True, exist_ok=True)
        (root / 'reports/dry_run.json').write_text(json.dumps(report,indent=2)+'\n')
        results = root / 'results/results.jsonl'
        records = [json.loads(line) for line in results.read_text().splitlines()] if results.exists() else []
        write_reports(root, records, report)
        print(json.dumps(report,indent=2))
        if not report['valid']:
            raise SystemExit(2)
    except (OSError, ValueError, AssertionError, KeyError, TypeError, yaml.YAMLError):
        print('Evaluation stopped: invalid/missing dataset or existing run artifacts; no automatic restart. Inspect dry_run.json.', file=sys.stderr)
        raise SystemExit(1) from None


def capture_main(args=None):
    import rclpy
    from rclpy.utilities import remove_ros_args
    from go2_vlm_interfaces.srv import CaptureScene
    argv = sys.argv if args is None else ['capture_eval_scene', *args]
    parser = argparse.ArgumentParser(description='Save one operator-positioned Go2 camera scene; publishes no motion.')
    parser.add_argument('--dataset', default=str(DEFAULT_DATASET))
    parser.add_argument('--scene-id', required=True, choices=SCENE_IDS)
    parser.add_argument('--overwrite', action='store_true')
    options = parser.parse_args(remove_ros_args(argv)[1:])
    root = workspace_dataset(options.dataset)
    if not (root / 'ground_truth.yaml').exists():
        parser.error('Initialize the dataset using evaluate_scenes --init first')
    target = root / 'images' / (options.scene_id + '.png')
    if (target.exists() or target.with_suffix('.json').exists()) and not options.overwrite:
        parser.error('Scene already exists; explicit --overwrite required')
    rclpy.init(args=argv[1:])
    node = rclpy.create_node('evaluation_capture_client')
    try:
        client = node.create_client(CaptureScene, '/go2_vlm/capture_scene')
        if not client.wait_for_service(timeout_sec=10):
            raise RuntimeError('Capture service unavailable')
        future = client.call_async(CaptureScene.Request(save_image=True))
        rclpy.spin_until_future_complete(node,future,timeout_sec=15)
        if not future.done() or not future.result().success:
            raise RuntimeError('Capture failed; no automatic retry')
        response = future.result()
        source = Path(response.saved_path).resolve()
        if not source.is_relative_to(WORKSPACE):
            raise ValueError('Capture path outside workspace')
        metadata = save_capture(root, options.scene_id, source, {'scene_id':response.scene_id,
            'image_stamp':{'sec':response.image_stamp.sec,'nanosec':response.image_stamp.nanosec},
            'frame_id':response.frame_id}, overwrite=options.overwrite)
        print(json.dumps(metadata,indent=2))
        print('Image saved. Human review/confirmation in ground_truth.yaml is required before evaluation.')
    except Exception:
        print('Evaluation capture failed; details withheld; no automatic retry.',file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        node.destroy_node()
        rclpy.shutdown()
