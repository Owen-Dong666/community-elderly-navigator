"""In-memory session state machine shared by the simulator and future K10 link."""

from __future__ import annotations

from uuid import uuid4

from .knowledge import KnowledgeBase
from .models import DeviceEvent, DeviceState, PlanResult, SessionState


class SessionError(RuntimeError):
    """Invalid session transition."""


class SessionManager:
    def __init__(
        self,
        knowledge: KnowledgeBase,
        sessions: dict[str, SessionState] | None = None,
    ) -> None:
        self.knowledge = knowledge
        self._sessions = sessions if sessions is not None else {}

    def create(self, plan: PlanResult) -> SessionState:
        session_id = str(uuid4())
        device = self._device_for(plan, 0) if plan.status == "ready" else self._notice(plan)
        state = SessionState(
            session_id=session_id,
            status=plan.status,
            plan=plan,
            device=device,
            ended=False,
        )
        self._sessions[session_id] = state
        return state

    def get(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def apply_event(self, session_id: str, event: DeviceEvent) -> SessionState:
        state = self._sessions.get(session_id)
        if state is None:
            raise SessionError("会话不存在")
        if state.ended:
            return state
        if event.type not in {"BUTTON_A", "BUTTON_B"}:
            raise SessionError("不支持的按键事件")
        if state.plan.status != "ready" or not state.plan.steps:
            return state

        current_index = state.device.current_step_index or 0
        if event.type == "BUTTON_A":
            updated = state.model_copy(
                update={"device": self._device_for(state.plan, current_index)}
            )
        elif current_index + 1 < len(state.plan.steps):
            updated = state.model_copy(
                update={"device": self._device_for(state.plan, current_index + 1)}
            )
        else:
            updated = state.model_copy(update={"device": self._idle_device(), "ended": True})

        self._sessions[session_id] = updated
        return updated

    def _device_for(self, plan: PlanResult, step_index: int) -> DeviceState:
        step = plan.steps[step_index]
        location = (
            self.knowledge.get_location(plan.location_id) if plan.location_id else None
        )
        leds = [location.led_index] if location else []
        helper_parts = [f"步骤 {step_index + 1} / {len(plan.steps)}"]
        if plan.schedule:
            helper_parts.append(plan.schedule)
        return DeviceState(
            screen_mode="display",
            service_name=plan.service_name,
            current_step_index=step_index,
            total_steps=len(plan.steps),
            title=step.title,
            body=step.instruction,
            helper_text=" · ".join(helper_parts),
            speech_text=step.speech,
            speech_status="queued",
            active_leds=leds,
        )

    @staticmethod
    def _notice(plan: PlanResult) -> DeviceState:
        message = plan.confirmation_message or plan.summary
        title = "请确认办理事项" if plan.status == "needs_clarification" else "需要人工确认"
        return DeviceState(
            screen_mode="display" if plan.status == "needs_clarification" else "error",
            service_name=plan.service_name,
            title=title,
            body=plan.summary,
            helper_text="地图指示灯保持关闭",
            speech_text=message,
            speech_status="queued" if message else "idle",
            active_leds=[],
        )

    @staticmethod
    def _idle_device() -> DeviceState:
        return DeviceState(
            screen_mode="idle",
            title="本次导航已结束",
            body="可以开始新的查询",
            helper_text="演示数据",
            active_leds=[],
        )

