"""Persistent operator-captured dataset and image-bound human ground truth."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import cv2
import numpy as np
import yaml
from ..image_encoding import prepare_image

SCENE_IDS = tuple(f'scene_{i:02d}' for i in range(1, 11))
TARGET_PLAN = [('living_room', 'green', 'cube'), ('bedroom_1', 'red', 'triangular_prism'),
               ('bedroom_2', 'blue', 'cylinder'), ('master_bedroom', 'yellow', 'cube'),
               ('kitchen', 'purple', 'cylinder')]
MODELS = {'openai': 'gpt-4o-mini', 'gemini': 'gemini-3.8-flash'}
# Run from the repository/workspace root, or select it explicitly.
WORKSPACE = Path(os.environ.get('GO2_WORKSPACE') or Path.cwd()).expanduser().resolve()
DEFAULT_DATASET = WORKSPACE / '.runtime/go2_vlm_scene/evaluation'


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError('Duplicate YAML key')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_yaml(path):
    value = yaml.load(Path(path).read_text(), Loader=UniqueLoader)
    if not isinstance(value, dict):
        raise ValueError('Expected a YAML mapping')
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def workspace_dataset(path):
    root = Path(path).expanduser().resolve()
    if not root.is_relative_to(WORKSPACE) or root.is_relative_to(WORKSPACE / 'install'):
        raise ValueError('Dataset must be in the workspace, outside installation resources')
    return root


@contextmanager
def dataset_lock(root):
    # Serializes capture/validation/run against this tool's writes.
    with (Path(root) / '.dataset.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def init_dataset(root):
    root = Path(root)
    for folder in ('images', 'results', 'reports'):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / 'results/results.jsonl').touch(exist_ok=True)
    template_dir = Path(__file__).resolve().parents[2] / 'config'
    if not template_dir.exists():
        from ament_index_python.packages import get_package_share_directory
        template_dir = Path(get_package_share_directory('go2_vlm_scene')) / 'config'
    for source, target in [('evaluation_aliases.yaml', 'aliases.yaml'), ('evaluation_pricing.yaml', 'pricing.yaml')]:
        if not (root / target).exists():
            with (root / target).open('xb') as stream:
                stream.write((template_dir / source).read_bytes())
    rooms = TARGET_PLAN
    plan, truth = {}, {}
    for i, scene_id in enumerate(SCENE_IDS):
        room, color, shape = rooms[i // 2]
        plan[scene_id] = {'room': room, 'difficulty': 'clear' if i % 2 == 0 else 'difficult',
                          'planned_target': {'color': color, 'shape': shape}}
        # Planning labels are deliberately NOT copied into ground truth.
        truth[scene_id] = {'image': f'images/{scene_id}.png', 'room': None, 'difficulty': None,
            'expected_visible_targets': [], 'supported_scene_phrases': [], 'unsupported_scene_phrases': [],
            'human_confirmed': False, 'confirmed_by': None, 'confirmed_at': None,
            'confirmed_image_sha256': None, 'notes': ''}
    for filename, data in [('scene_plan.yaml', {'version': 1, 'planning_only_not_ground_truth': True, 'scenes': plan}),
                            ('ground_truth.yaml', {'version': 1, 'scenes': truth})]:
        if not (root / filename).exists():
            with (root / filename).open('x') as stream:
                yaml.safe_dump(data, stream, sort_keys=False)


def decode_png(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Lossless RGB PNG required; keep Stage 1 image_save_format=png')
    bgr = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if bgr is None or bgr.dtype != np.uint8 or bgr.ndim != 3 or bgr.shape[2] != 3:
        raise ValueError('Expected a nonempty 8-bit three-channel PNG')
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def save_capture(root, scene_id, source, capture, overwrite=False):
    root = Path(root)
    if scene_id not in SCENE_IDS:
        raise ValueError('scene-id must be scene_01 through scene_10')
    target = root / 'images' / f'{scene_id}.png'
    meta_path = target.with_suffix('.json')
    with dataset_lock(root):
        if (target.exists() or meta_path.exists()) and not overwrite:
            raise FileExistsError('Scene exists; use --overwrite only for an intentional replacement')
        data = Path(source).read_bytes()
        rgb = decode_png(data)
        stamp = capture.get('image_stamp', {})
        if (not capture.get('scene_id') or not capture.get('frame_id') or
                type(stamp.get('sec')) is not int or type(stamp.get('nanosec')) is not int):
            raise ValueError('Capture provenance and image timestamp required')
        metadata = {'scene_id': scene_id, 'source': 'Stage 1 CaptureScene /rgb_image',
            'captured_scene_id': capture['scene_id'], 'image_stamp': stamp,
            'frame_id': capture['frame_id'], 'saved_at_utc': utc_now(),
            'png_sha256': digest(data), 'rgb_sha256': digest(rgb.tobytes()),
            'width': rgb.shape[1], 'height': rgb.shape[0]}
        # Clear image-bound approval even on explicit overwrite with identical bytes.
        truth = load_yaml(root / 'ground_truth.yaml')
        truth['scenes'][scene_id].update(human_confirmed=False, confirmed_by=None,
            confirmed_at=None, confirmed_image_sha256=None)
        (root / 'ground_truth.yaml').write_text(yaml.safe_dump(truth, sort_keys=False))
        for path, payload in [(target, data), (meta_path, (json.dumps(metadata, indent=2) + '\n').encode())]:
            temporary = path.with_suffix(path.suffix + '.tmp')
            with temporary.open('wb') as stream:
                stream.write(payload)
            temporary.replace(path)
        return metadata


def validate_dataset(root):
    root = Path(root)
    errors, scenes, seen = [], [], set()
    try:
        truth = load_yaml(root / 'ground_truth.yaml')['scenes']
        plan = load_yaml(root / 'scene_plan.yaml')['scenes']
        if not isinstance(truth, dict) or not isinstance(plan, dict):
            raise ValueError('Scene mappings required')
        if set(truth) != set(SCENE_IDS) or set(plan) != set(SCENE_IDS):
            errors.append('Exactly scene_01 through scene_10 are required in plan and ground truth')
    except (OSError, ValueError, KeyError, yaml.YAMLError):
        return [], ['Ground truth/scene plan missing or malformed']
    for index, scene_id in enumerate(SCENE_IDS):
        room, color, shape = TARGET_PLAN[index // 2]
        required_plan = {'room':room, 'difficulty':'clear' if index % 2 == 0 else 'difficult',
                         'planned_target':{'color':color,'shape':shape}}
        if plan.get(scene_id) != required_plan:
            errors.append(scene_id + ': scene plan must retain the required five targets and two difficulties')
            continue
        item = truth.get(scene_id, {})
        try:
            if not isinstance(item, dict):
                raise ValueError('Ground truth entry must be a mapping')
            if item.get('image') != f'images/{scene_id}.png':
                raise ValueError('Image path must match stable scene ID')
            path = root / item['image']
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Image path escapes dataset')
            data = path.read_bytes()
            rgb = decode_png(data)
            png_hash = digest(data)
            rgb_hash = digest(rgb.tobytes())
            if rgb_hash in seen:
                raise ValueError('Duplicate RGB image: ten distinct camera views required')
            seen.add(rgb_hash)
            meta = json.loads(path.with_suffix('.json').read_text())
            if not isinstance(meta, dict):
                raise ValueError('Capture metadata must be a mapping')
            if (meta.get('scene_id') != scene_id or meta.get('png_sha256') != png_hash or
                    meta.get('rgb_sha256') != rgb_hash or meta.get('width') != rgb.shape[1] or
                    meta.get('height') != rgb.shape[0]):
                raise ValueError('Image hash/dimensions do not match capture metadata')
            stamp = meta.get('image_stamp')
            if (not meta.get('frame_id') or not isinstance(stamp, dict) or
                    type(stamp.get('sec')) is not int or type(stamp.get('nanosec')) is not int or
                    not 0 <= stamp['nanosec'] < 1000000000 or not meta.get('captured_scene_id')):
                raise ValueError('Capture timestamp/frame provenance required')
            if item.get('human_confirmed') is not True or not item.get('confirmed_by') or not item.get('confirmed_at'):
                raise ValueError('Human image review and named confirmation required')
            if item.get('confirmed_image_sha256') != png_hash:
                raise ValueError('Human confirmation hash does not match saved PNG')
            if item.get('room') != plan[scene_id]['room'] or item.get('difficulty') != plan[scene_id]['difficulty']:
                raise ValueError('Human-confirmed room/difficulty must match planned view')
            targets = item.get('expected_visible_targets')
            if not isinstance(targets, list) or not targets or any(
                    not isinstance(t, dict) or set(t) != {'color', 'shape'} or
                    not isinstance(t['color'], str) or not isinstance(t['shape'], str) for t in targets):
                raise ValueError('Human-authored visible color/shape labels required')
            if plan[scene_id]['planned_target'] not in targets:
                raise ValueError('Planned target must actually be visible and human-confirmed; recapture otherwise')
            for field in ('supported_scene_phrases', 'unsupported_scene_phrases'):
                if not isinstance(item.get(field), list) or any(not isinstance(v, str) or not v.strip() for v in item[field]):
                    raise ValueError('Scene evidence phrases must be lists of nonempty strings')
            scenes.append({'scene_id': scene_id, 'truth': item, 'capture': meta,
                           'png_sha256': png_hash, 'image': prepare_image(rgb, 90)})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            message = str(exc) if isinstance(exc, ValueError) else 'Image or metadata missing/malformed'
            errors.append(f'{scene_id}: {message}')
    return scenes, errors
