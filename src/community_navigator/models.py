"""Validated data contracts for knowledge, planning and devices."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocationRecord(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    led_index: int = Field(ge=1, le=6)
    description: str = Field(min_length=1)


class ServiceRecord(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    category: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    schedule: str = Field(min_length=1)
    location_id: str = Field(min_length=1)
    materials: list[str] = Field(default_factory=list)
    steps: list[str] = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)
    contact_note: str | None = None
    requires_confirmation: bool = False

    @field_validator(
        "id",
        "name",
        "category",
        "audience",
        "summary",
        "schedule",
        "location_id",
    )
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text field cannot be blank")
        return value


class CommunityData(StrictModel):
    community_name: str = Field(min_length=1)
    is_demo: bool
    locations: list[LocationRecord]
    services: list[ServiceRecord]


class PlanStep(StrictModel):
    index: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=30)
    instruction: str = Field(min_length=1, max_length=180)
    speech: str = Field(min_length=1, max_length=220)


PlanStatus = Literal["ready", "needs_clarification", "not_found", "error"]


class PlanResult(StrictModel):
    status: PlanStatus
    service_id: str | None = None
    service_name: str = ""
    summary: str = ""
    location_id: str | None = None
    schedule: str = ""
    materials: list[str] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list, max_length=6)
    confirmation_message: str | None = None
    source_record_ids: list[str] = Field(default_factory=list)


ScreenMode = Literal["idle", "listening", "searching", "planning", "display", "error"]
SpeechStatus = Literal["idle", "queued", "speaking", "done", "unavailable"]


class DeviceState(StrictModel):
    screen_mode: ScreenMode = "idle"
    service_name: str = ""
    current_step_index: int | None = None
    total_steps: int = 0
    title: str = "请说出您要办理的事情"
    body: str = ""
    helper_text: str = "演示数据"
    speech_text: str = ""
    speech_status: SpeechStatus = "idle"
    active_leds: list[int] = Field(default_factory=list)


class SessionState(StrictModel):
    session_id: str
    status: PlanStatus
    plan: PlanResult
    device: DeviceState
    ended: bool = False


class DeviceEvent(StrictModel):
    type: Literal["BUTTON_A", "BUTTON_B"]


class SerialMessage(StrictModel):
    version: Literal[1] = 1
    type: Literal["QUERY", "BUTTON_A", "BUTTON_B", "DEVICE_STATE"]
    request_id: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)

