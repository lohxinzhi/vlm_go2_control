"""Prepare JPEG bytes without resizing or mutating the retained RGB8 image."""
import base64
import hashlib
from dataclasses import dataclass, field
import cv2
import numpy as np


@dataclass(frozen=True)
class PreparedImage:
    jpeg: bytes = field(repr=False)
    width: int
    height: int
    rgb_sha256: str
    jpeg_sha256: str

    def data_uri(self):
        # Called only at the request boundary, never in disabled preflight.
        return 'data:image/jpeg;base64,' + base64.b64encode(self.jpeg).decode('ascii')


def prepare_image(rgb, quality=90):
    if not isinstance(quality, int) or not 1 <= quality <= 100:
        raise ValueError('INVALID_IMAGE_OPTIONS: JPEG quality must be 1..100')
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or not rgb.size:
        raise ValueError('INVALID_IMAGE: expected nonempty uint8 RGB image')
    ok, encoded = cv2.imencode('.jpg', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                               [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError('IMAGE_ENCODING_FAILED: JPEG encoding failed')
    payload = encoded.tobytes()
    return PreparedImage(payload, rgb.shape[1], rgb.shape[0],
                         hashlib.sha256(rgb.tobytes()).hexdigest(),
                         hashlib.sha256(payload).hexdigest())
