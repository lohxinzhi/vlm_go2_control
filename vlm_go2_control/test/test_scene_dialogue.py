"""Tests for routing visual dialogue commands to the scene service."""

from types import SimpleNamespace
from threading import Event, Lock
import json
from concurrent.futures import Future

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


def test_new_motion_plan_cancels_previous_plan(monkeypatch):
    plans = [
        {'actions': [{'action': 'approach', 'object': 'chair'}]},
        {'actions': [{'action': 'goto_room', 'room': 1}]},
    ]
    pending = []
    monkeypatch.setattr(
        vlm_dialogue_manager, 'Thread',
        lambda target, args, daemon: SimpleNamespace(
            start=lambda: pending.append((target, args))))
    dialogue = SimpleNamespace(
        history=[], history_lock=Lock(), plan_lock=Lock(),
        active_plan=None, manual_control=False, rooms={1: {'name': 'Kitchen'}},
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **_: SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(plans.pop(0))))])))),
        text_model='test',
        actions_publisher=SimpleNamespace(publish=lambda _: None),
        validate_command=lambda command: True,
        execute_plan=lambda *_: None,
    )
    dialogue.report_reply = lambda _: None

    vlm_go2_control = vlm_dialogue_manager.VLMDialogueManager
    vlm_go2_control.run_request(dialogue, 'Approach the chair')
    previous = dialogue.active_plan
    assert not previous.is_set()
    vlm_go2_control.run_request(dialogue, 'Go to the kitchen')
    assert previous.is_set()
    assert dialogue.active_plan is not previous
    assert len(pending) == 2


def test_describe_and_invalid_plan_leave_motion_running(monkeypatch):
    plans = [
        {'actions': [{'action': 'describe', 'mode': 'describe'}]},
        {'actions': [{'action': 'unknown'}]},
    ]
    pending = []
    monkeypatch.setattr(
        vlm_dialogue_manager, 'Thread',
        lambda target, args, daemon: SimpleNamespace(
            start=lambda: pending.append((target, args))))
    active_plan = Event()
    replies = []
    dialogue = SimpleNamespace(
        history=[], history_lock=Lock(), plan_lock=Lock(),
        active_plan=active_plan,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **_: SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(plans.pop(0))))])))),
        text_model='test',
        actions_publisher=SimpleNamespace(publish=lambda _: None),
        validate_command=lambda command: command['action'] == 'describe',
        report_reply=replies.append,
        execute_non_motion=lambda *_: None,
    )

    vlm_dialogue_manager.VLMDialogueManager.run_request(dialogue, 'What do you see?')
    assert dialogue.active_plan is active_plan
    assert not active_plan.is_set()
    assert len(pending) == 1

    vlm_dialogue_manager.VLMDialogueManager.run_request(dialogue, 'Nonsense')
    assert dialogue.active_plan is active_plan
    assert not active_plan.is_set()
    assert len(pending) == 1
    assert 'Invalid command' in replies[0]


def test_canceled_plan_sends_cancel_request_to_action_server(monkeypatch):
    result_future = Future()
    cancel_event = Event()
    cancel_event.set()
    cancellations = []

    def cancel_goal():
        cancellations.append(True)
        result_future.set_result(SimpleNamespace(result=SimpleNamespace(
            success=False, message='Canceled.')))

    goal_handle = SimpleNamespace(
        accepted=True, get_result_async=lambda: result_future,
        cancel_goal_async=cancel_goal)
    client = SimpleNamespace(
        wait_for_server=lambda timeout_sec: True,
        send_goal_async=lambda goal: object())
    monkeypatch.setattr(vlm_dialogue_manager, 'wait_for_future',
                        lambda future: goal_handle)
    monkeypatch.setattr(vlm_dialogue_manager.rclpy, 'ok', lambda: True)
    dialogue = SimpleNamespace(plan_lock=Lock(), active_goal=None)

    # Set cancellation after the goal has been accepted.
    monkeypatch.setattr(goal_handle, 'get_result_async',
                        lambda: (cancel_event.set(), result_future)[1])
    cancel_event.clear()
    success, message = vlm_dialogue_manager.VLMDialogueManager.send_action(
        dialogue, client, object(), cancel_event)

    assert not success
    assert message == 'Canceled.'
    assert len(cancellations) == 1


def test_manual_control_cancels_motion_before_acknowledging():
    """Manual commands are allowed only after the old motion plan drains."""
    active_plan = Event()
    dialogue = SimpleNamespace(plan_lock=Lock(), motion_lock=Lock(),
                               active_plan=active_plan, manual_control=False)
    response = SimpleNamespace(success=False, message='')
    vlm_dialogue_manager.VLMDialogueManager.set_manual_control(
        dialogue, SimpleNamespace(data=True), response)
    assert active_plan.is_set()
    assert dialogue.manual_control
    assert response.success


def test_reply_is_published_for_dashboard():
    """The same reply reaches both dialogue history and the browser topic."""
    published = []
    dialogue = SimpleNamespace(history_lock=Lock(), history=[],
                               reply_publisher=SimpleNamespace(publish=published.append))
    vlm_dialogue_manager.VLMDialogueManager.report_reply(dialogue, 'A red cube.')
    assert published[0].data == 'A red cube.'
    assert dialogue.history[-1]['content'] == 'A red cube.'
