"""ROS-independent pre-request path and structured call metadata, without log I/O."""
from datetime import datetime, timezone
import time
from .image_encoding import prepare_image
from .prompts import select_prompt
from .providers import create_provider
from .types import QueryOptions, VLMResult


def query_scene(scene, mode, provider, model=None, options=None, *, environ=None,
                client_factory=None, question=''):
    options = options or QueryOptions()
    started = time.monotonic()
    metadata = {'scene_id': scene.scene_id, 'operation': mode or 'describe',
                'provider': provider, 'model': model or '',
                'question': question.strip() if mode == 'vqa' else '',
                'started_at_utc': datetime.now(timezone.utc).isoformat(),
                'started_monotonic_sec': started}
    result = VLMResult(provider=provider, model=model or '')
    try:
        prompt, version = select_prompt(mode, question)
        adapter = create_provider(provider, model, environ=environ, client_factory=client_factory)
        result.model = adapter.config.model
        image = prepare_image(scene.frame.rgb, options.jpeg_quality)
        metadata.update(model=adapter.config.model, prompt_version=version,
                        width=image.width, height=image.height,
                        image_rgb_sha256=image.rgb_sha256, image_jpeg_sha256=image.jpeg_sha256,
                        jpeg_quality=options.jpeg_quality, max_output_tokens=options.max_output_tokens)
        result = adapter.query(image, prompt, options)
    except ValueError as exc:
        code, _, message = str(exc).partition(': ')
        result.error_type, result.error_message = code, message
    except Exception:
        result.error_type = 'PREPARATION_ERROR'
        result.error_message = 'Unable to prepare the scene request'
    ended = time.monotonic()
    metadata.update(ended_at_utc=datetime.now(timezone.utc).isoformat(),
                    ended_monotonic_sec=ended, total_latency_sec=ended-started,
                    provider_latency_sec=result.latency_sec,
                    input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                    total_tokens=result.total_tokens, raw_usage=result.raw_usage,
                    status='SUCCESS' if result.success else result.error_type,
                    error_message=result.error_message)
    metadata['attempts'] = result.metadata.get('attempts', [])
    metadata['attempt_count'] = len(metadata['attempts'])
    metadata['response'] = result.answer
    result.metadata = metadata
    return result
