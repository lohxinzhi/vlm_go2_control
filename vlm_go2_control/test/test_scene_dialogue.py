"""Tests for routing visual dialogue commands to the scene service."""

from types import SimpleNamespace

from vlm_go2_control import vlm_dialogue_manager


def test_visual_question_is_forwarded_to_service(monkeypatch):
    """The dialogue manager sends the VQA mode and original question."""
    requests = []
    client = SimpleNamespace(
        wait_for_service=lambda timeout_sec: True,
        call_async=lambda request: requests.append(request))
    dialogue = SimpleNamespace(describe_client=client)
    response = SimpleNamespace(
        success=True, description='A red cube.', message='')
    monkeypatch.setattr(
        vlm_dialogue_manager, 'wait_for_future', lambda _: response)

    reply, success = vlm_dialogue_manager.VLMDialogueManager.execute_command(
        dialogue, {'action': 'describe', 'mode': 'vqa',
                   'question': 'What colour is the cube?'})

    assert success
    assert reply == 'A red cube.'
    assert requests[0].mode == 'vqa'
    assert requests[0].question == 'What colour is the cube?'

    reply, success = vlm_dialogue_manager.VLMDialogueManager.execute_command(
        dialogue, {'action': 'describe', 'mode': 'describe'})
    assert success
    assert reply == 'A red cube.'
    assert requests[1].mode == 'describe'
    assert requests[1].question == ''
