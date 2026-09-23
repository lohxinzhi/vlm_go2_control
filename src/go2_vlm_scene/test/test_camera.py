import cv2
import numpy as np
import pytest
from go2_vlm_scene.camera import CameraBuffer, SceneError
from go2_vlm_scene.image_storage import save_scene


def test_latest_and_immutable():
    buffer = CameraBuffer()
    rgb = np.zeros((2, 3, 3), dtype=np.uint8)
    buffer.update(rgb, 20, 1, 'camera')
    rgb[:] = 12
    buffer.update(rgb, 1, 2, 'camera')  # ROS clock may reset
    rgb[:] = 99
    scene = buffer.capture()
    assert np.all(scene.frame.rgb == 12)
    assert (scene.frame.stamp_sec, scene.frame.stamp_nanosec) == (1, 2)
    with pytest.raises(ValueError):
        scene.frame.rgb.setflags(write=True)
    buffer.update(rgb, 2, 0, 'camera')
    assert np.all(scene.frame.rgb == 12)


def test_missing_stale_and_disabled_threshold():
    now = [10.0]
    buffer = CameraBuffer(clock=lambda: now[0])
    with pytest.raises(SceneError, match='NO_FRAME'):
        buffer.capture()
    rgb = np.zeros((2, 3, 3), dtype=np.uint8)
    buffer.update(rgb, 0, 0, '')
    scene = buffer.capture()
    now[0] = 12.0
    buffer.capture()
    now[0] = 12.01
    with pytest.raises(SceneError, match='STALE_FRAME'):
        buffer.capture()
    assert buffer.resolve(scene.scene_id) is scene
    unlimited = CameraBuffer(stale_threshold_sec=0, clock=lambda: now[0])
    unlimited.update(rgb, 0, 0, '', received_at=0)
    unlimited.capture()


def test_ids_refresh_and_expiration():
    buffer = CameraBuffer(retained_count=2)
    buffer.update(np.zeros((2, 3, 3), dtype=np.uint8), 1, 0, '')
    first = buffer.capture()
    second = buffer.resolve()
    assert first.scene_id != second.scene_id
    assert buffer.resolve(first.scene_id) is first
    third = buffer.resolve(first.scene_id, refresh_frame=True)
    assert third.scene_id not in (first.scene_id, second.scene_id)
    with pytest.raises(SceneError, match='SCENE_NOT_FOUND'):
        buffer.resolve(first.scene_id)
    with pytest.raises(SceneError, match='SCENE_NOT_FOUND'):
        buffer.resolve('unknown')
    assert buffer.resolve(second.scene_id) is second


def test_invalid_frame_preserves_latest():
    buffer = CameraBuffer()
    buffer.update(np.zeros((2, 3, 3), dtype=np.uint8), 1, 0, '')
    for bad in (np.zeros((2, 3)), np.zeros((0, 3, 3), dtype=np.uint8)):
        with pytest.raises(SceneError, match='INVALID_FRAME'):
            buffer.update(bad, 2, 0, '')
    assert buffer.capture().frame.stamp_sec == 1


@pytest.mark.parametrize('count,threshold', [(0, 2), (1, -1), (1, float('nan'))])
def test_invalid_configuration(count, threshold):
    with pytest.raises(ValueError):
        CameraBuffer(count, threshold)


@pytest.mark.parametrize('image_format', ['png', 'jpg'])
def test_save_colour_dimensions_no_overwrite(tmp_path, image_format):
    buffer = CameraBuffer()
    rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    rgb[:, :, 0] = 255
    buffer.update(rgb, 1, 0, 'camera')
    scene = buffer.capture()
    path = save_scene(scene, tmp_path, image_format)
    saved = cv2.imread(path)
    assert saved.shape == (480, 640, 3)
    assert saved[100, 100, 2] >= 254 and saved[100, 100, 0] == 0
    with pytest.raises(FileExistsError):
        save_scene(scene, tmp_path, image_format)
