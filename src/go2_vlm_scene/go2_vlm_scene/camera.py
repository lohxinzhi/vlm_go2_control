"""ROS-independent RGB buffer. Receipt order defines latest, not ROS clock order."""
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
import math
import time
import uuid

import numpy as np


class SceneError(ValueError):
    pass


@dataclass(frozen=True)
class Frame:
    rgb: np.ndarray
    stamp_sec: int
    stamp_nanosec: int
    frame_id: str
    received_at: float


@dataclass(frozen=True)
class Scene:
    scene_id: str
    frame: Frame


class CameraBuffer:
    def __init__(self, retained_count=10, stale_threshold_sec=2.0, clock=time.monotonic):
        if retained_count < 1:
            raise ValueError('retained_scene_count must be positive')
        if not math.isfinite(stale_threshold_sec) or stale_threshold_sec < 0:
            raise ValueError('stale_frame_threshold_sec must be finite and nonnegative')
        self.retained_count = retained_count
        self.stale_threshold_sec = stale_threshold_sec
        self.clock = clock
        self._latest = None
        self._scenes = OrderedDict()
        self._lock = RLock()

    @staticmethod
    def _freeze(rgb):
        array = np.asarray(rgb)
        if array.dtype != np.uint8 or array.ndim != 3 or array.shape[2] != 3 or not array.size:
            raise SceneError('INVALID_FRAME: expected nonempty uint8 RGB image')
        # Immutable bytes backing prevents callers re-enabling array writes.
        return np.frombuffer(array.tobytes(), dtype=np.uint8).reshape(array.shape)

    def update(self, rgb, stamp_sec, stamp_nanosec, frame_id, received_at=None):
        with self._lock:
            frame = Frame(self._freeze(rgb), stamp_sec, stamp_nanosec, frame_id,
                          self.clock() if received_at is None else received_at)
            self._latest = frame

    def capture(self):
        with self._lock:
            if self._latest is None:
                raise SceneError('NO_FRAME: no valid camera frame received')
            age = self.clock() - self._latest.received_at
            if self.stale_threshold_sec > 0 and age > self.stale_threshold_sec:
                raise SceneError(f'STALE_FRAME: receipt age {age:.3f}s exceeds threshold')
            current = self._latest
            frozen = Frame(self._freeze(current.rgb), current.stamp_sec,
                           current.stamp_nanosec, current.frame_id, current.received_at)
            scene = Scene(uuid.uuid4().hex, frozen)
            self._scenes[scene.scene_id] = scene
            while len(self._scenes) > self.retained_count:
                self._scenes.popitem(last=False)
            return scene

    def resolve(self, scene_id='', refresh_frame=False):
        if refresh_frame or not scene_id:
            return self.capture()
        with self._lock:
            try:
                return self._scenes[scene_id]
            except KeyError:
                raise SceneError('SCENE_NOT_FOUND: unknown or expired scene_id') from None
