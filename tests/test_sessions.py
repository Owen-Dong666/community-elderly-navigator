"""Deterministic K10-style button and device-state tests."""

from __future__ import annotations

import pytest

from community_navigator.knowledge import KnowledgeBase
from community_navigator.models import DeviceEvent, PlanResult, PlanStep
from community_navigator.sessions import SessionError, SessionManager


@pytest.fixture
def knowledge(demo_knowledge_path) -> KnowledgeBase:
    return KnowledgeBase.load(demo_knowledge_path)


@pytest.fixture
def ready_plan() -> PlanResult:
    return PlanResult(
        status="ready",
        service_id="calligraphy_class",
        service_name="书法班报名",
        summary="办理书法班报名。",
        location_id="activity_room",
        schedule="每周三上午九点",
        materials=["社区居民卡"],
        steps=[
            PlanStep(index=1, title="准备材料", instruction="带好居民卡。", speech="请带好居民卡。"),
            PlanStep(index=2, title="前往活动室", instruction="前往社区活动室。", speech="请前往社区活动室。"),
            PlanStep(index=3, title="登记报名", instruction="登记姓名和电话。", speech="请登记姓名和电话。"),
        ],
        source_record_ids=["calligraphy_class"],
    )


def test_ready_session_starts_at_first_step_with_one_location_led(
    knowledge: KnowledgeBase, ready_plan: PlanResult
) -> None:
    state = SessionManager(knowledge).create(ready_plan)

    assert state.device.screen_mode == "display"
    assert state.device.current_step_index == 0
    assert state.device.total_steps == 3
    assert state.device.title == "准备材料"
    assert state.device.speech_text == "请带好居民卡。"
    assert state.device.speech_status == "queued"
    assert state.device.active_leds == [4]
    assert state.ended is False


def test_button_a_repeats_current_step_without_advancing(
    knowledge: KnowledgeBase, ready_plan: PlanResult
) -> None:
    manager = SessionManager(knowledge)
    created = manager.create(ready_plan)

    first = manager.apply_event(created.session_id, DeviceEvent(type="BUTTON_A"))
    second = manager.apply_event(created.session_id, DeviceEvent(type="BUTTON_A"))

    assert first.device.current_step_index == 0
    assert second.device.current_step_index == 0
    assert second.device.speech_text == "请带好居民卡。"
    assert second.device.speech_status == "queued"
    assert second.device.active_leds == [4]


def test_button_b_advances_then_ends_and_stays_idle(
    knowledge: KnowledgeBase, ready_plan: PlanResult
) -> None:
    manager = SessionManager(knowledge)
    state = manager.create(ready_plan)

    state = manager.apply_event(state.session_id, DeviceEvent(type="BUTTON_B"))
    assert state.device.current_step_index == 1
    assert state.device.title == "前往活动室"
    assert state.device.active_leds == [4]

    state = manager.apply_event(state.session_id, DeviceEvent(type="BUTTON_B"))
    assert state.device.current_step_index == 2

    ended = manager.apply_event(state.session_id, DeviceEvent(type="BUTTON_B"))
    assert ended.ended is True
    assert ended.device.screen_mode == "idle"
    assert ended.device.active_leds == []
    assert ended.device.current_step_index is None
    assert ended.device.total_steps == 0

    repeated = manager.apply_event(state.session_id, DeviceEvent(type="BUTTON_B"))
    assert repeated == ended


def test_get_and_invalid_session_handling(
    knowledge: KnowledgeBase, ready_plan: PlanResult
) -> None:
    manager = SessionManager(knowledge)
    created = manager.create(ready_plan)

    assert manager.get(created.session_id) == created
    assert manager.get("missing") is None
    with pytest.raises(SessionError, match="不存在"):
        manager.apply_event("missing", DeviceEvent(type="BUTTON_A"))


def test_unknown_event_is_rejected(
    knowledge: KnowledgeBase, ready_plan: PlanResult
) -> None:
    manager = SessionManager(knowledge)
    created = manager.create(ready_plan)
    invalid = DeviceEvent.model_construct(type="BUTTON_X")

    with pytest.raises(SessionError, match="按键"):
        manager.apply_event(created.session_id, invalid)


def test_not_found_plan_has_no_led_and_speaks_confirmation(
    knowledge: KnowledgeBase,
) -> None:
    plan = PlanResult(
        status="not_found",
        summary="当前资料中没有这项信息，请向社区工作人员确认",
        confirmation_message="当前资料中没有这项信息，请向社区工作人员确认",
    )

    state = SessionManager(knowledge).create(plan)

    assert state.device.screen_mode == "error"
    assert state.device.current_step_index is None
    assert state.device.active_leds == []
    assert "工作人员" in state.device.body
    assert "工作人员" in state.device.speech_text

