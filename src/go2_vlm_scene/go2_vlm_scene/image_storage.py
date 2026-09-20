"""Diagnostic encoding; all internal frames are RGB8."""
from pathlib import Path
import cv2


def save_scene(scene, directory, image_format='png', jpeg_quality=95):
    suffix = image_format.lower()
    if suffix not in ('png', 'jpg', 'jpeg'):
        raise ValueError('image_save_format must be png, jpg, or jpeg')
    if not 1 <= jpeg_quality <= 100:
        raise ValueError('jpeg_quality must be between 1 and 100')
    target_dir = Path(directory).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f'{scene.scene_id}.{suffix}'
    bgr = cv2.cvtColor(scene.frame.rgb, cv2.COLOR_RGB2BGR)
    options = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality] if suffix != 'png' else []
    success, encoded = cv2.imencode(f'.{suffix}', bgr, options)
    if not success:
        raise OSError('image encoding failed')
    # Exclusive creation: even saving the same scene twice cannot overwrite.
    with target.open('xb') as stream:
        stream.write(encoded.tobytes())
    return str(target)
