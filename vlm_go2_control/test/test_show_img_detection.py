"""Tests for the camera viewer's bounding box display timeout."""

from types import SimpleNamespace

from vlm_go2_control import show_img


def test_detection_expires_after_three_seconds(monkeypatch):
    """A new box renews the overlay; an old box is cleared from the viewer."""
    now = [100.0]
    monkeypatch.setattr(show_img.time, 'monotonic', lambda: now[0])
    viewer = SimpleNamespace(
        latest_detection=None, latest_detection_received_at=None)
    first_box = object()
    show_img.ImageAndBoundingBoxViewer.bounding_box_callback(viewer, first_box)

    now[0] = 102.9
    assert show_img.ImageAndBoundingBoxViewer.visible_detection(viewer) is first_box

    now[0] = 103.0
    assert show_img.ImageAndBoundingBoxViewer.visible_detection(viewer) is None
    assert viewer.latest_detection is None

    second_box = object()
    show_img.ImageAndBoundingBoxViewer.bounding_box_callback(viewer, second_box)
    now[0] = 105.9
    assert show_img.ImageAndBoundingBoxViewer.visible_detection(viewer) is second_box
