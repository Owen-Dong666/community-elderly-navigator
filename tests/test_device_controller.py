"""REST gateway and session-controller tests for the K10 bridge."""

from __future__ import annotations

import json

import httpx
import pytest

from community_navigator.device_bridge.controller import (
    BridgeController,
    BridgeGatewayError,
    HttpNavigatorGateway,
)
from community_navigator.device_bridge.protocol import DeviceCommand
from community_navigator.models import SessionState


def _session_payload(
    *,
    session_id: str = "session-1",
    step_index: int = 0,
    led_index: int = 4,
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "status": "ready",
        "plan": {
            "status": "ready",
            "service_id": "calligraphy_class",
            "service_name": "书法班报名",
            "summary": "书法班演示",
            "location_id": "activity_room",
            "schedule": "每周三上午九点",
            "materials": ["社区居民卡"],
            "steps": [
                {
                    "index": 1,
                    "title": "准备资料",
                    "instruction": "带上社区居民卡。",
                    "speech": "请带上社区居民卡。",
                },
                {
                    "index": 2,
                    "title": "前往活动室",
                    "instruction": "请前往活动室。",
                    "speech": "请前往活动室。",
                },
            ],
            "confirmation_message": None,
            "source_record_ids": ["calligraphy_class", "activity_room"],
        },
        "device": {
            "screen_mode": "display",
            "service_name": "书法班报名",
            "current_step_index": step_index,
            "total_steps": 2,
            "title": "准备资料" if step_index == 0 else "前往活动室",
            "body": "带上社区居民卡。" if step_index == 0 else "请前往活动室。",
            "helper_text": f"步骤 {step_index + 1} / 2",
            "speech_text": "请带上社区居民卡。" if step_index == 0 else "请前往活动室。",
            "speech_status": "queued",
            "active_leds": [led_index],
        },
        "ended": False,
    }


def test_http_gateway_calls_health_query_and_event_routes() -> None:
    seen: list[tuple[str, str, object, dict[str, float]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append(
            (
                request.method,
                request.url.path,
                body,
                request.extensions["timeout"],
            )
        )
        if request.url.path == "/api/v1/health":
            return httpx.Response(
                200,
                json={"status": "ok", "provider": "mock", "is_demo": True},
            )
        if request.url.path == "/api/v1/query":
            return httpx.Response(200, json=_session_payload())
        return httpx.Response(200, json=_session_payload(step_index=1))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = HttpNavigatorGateway("http://navigator.test/", client=client)

    assert gateway.health() == {"status": "ok", "provider": "mock", "is_demo": True}
    assert gateway.query("我想报名参加书法班").session_id == "session-1"
    assert gateway.event("session-1", "BUTTON_B").device.current_step_index == 1
    assert [(method, path, body) for method, path, body, _ in seen] == [
        ("GET", "/api/v1/health", None),
        ("POST", "/api/v1/query", {"text": "我想报名参加书法班"}),
        (
            "POST",
            "/api/v1/sessions/session-1/events",
            {"type": "BUTTON_B"},
        ),
    ]
    assert all(set(timeout.values()) == {10.0} for *_, timeout in seen)


def test_http_gateway_rejects_non_200_and_invalid_session_payloads() -> None:
    responses = iter(
        [
            httpx.Response(500, text="secret-token-from-server"),
            httpx.Response(200, json={"session_id": "incomplete"}),
        ]
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: next(responses))
    )
    gateway = HttpNavigatorGateway("http://navigator.test", client=client)

    with pytest.raises(BridgeGatewayError) as status_error:
        gateway.query("书法班")
    with pytest.raises(BridgeGatewayError) as schema_error:
        gateway.query("书法班")

    assert "secret-token-from-server" not in str(status_error.value)
    assert "incomplete" not in str(schema_error.value)


def test_http_gateway_marks_404_event_as_stale_session() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(404, json={"detail": "会话不存在"})
        )
    )
    gateway = HttpNavigatorGateway("http://navigator.test", client=client)

    with pytest.raises(BridgeGatewayError) as caught:
        gateway.event("stale", "BUTTON_A")

    assert caught.value.stale_session is True
    assert "stale" not in str(caught.value)


class FakeGateway:
    def __init__(self) -> None:
        self.query_count = 0
        self.fail_query: BridgeGatewayError | None = None
        self.fail_event: BridgeGatewayError | None = None

    def health(self) -> dict[str, object]:
        return {"status": "ok", "provider": "mock", "is_demo": True}

    def query(self, text: str) -> SessionState:
        if self.fail_query:
            raise self.fail_query
        self.query_count += 1
        return SessionState.model_validate(
            _session_payload(session_id=f"session-{self.query_count}")
        )

    def event(self, session_id: str, event_type: str) -> SessionState:
        if self.fail_event:
            raise self.fail_event
        return SessionState.model_validate(
            _session_payload(
                session_id=session_id,
                step_index=0 if event_type == "BUTTON_A" else 1,
                led_index=4 if event_type == "BUTTON_A" else 2,
            )
        )


def test_hello_returns_ready_without_creating_session() -> None:
    controller = BridgeController(FakeGateway())

    records = controller.handle(DeviceCommand("HELLO", "1"))

    assert records == ("READY|智能体已连接\n".encode(),)
    assert controller.current_session_id is None


def test_query_saves_session_and_returns_device_frame() -> None:
    controller = BridgeController(FakeGateway())

    first = controller.handle(DeviceCommand("QUERY", "书法班"))
    second = controller.handle(DeviceCommand("QUERY", "量血压"))

    assert b"LED|4\n" in first
    assert b"STATE_END\n" == first[-1]
    assert b"LED|4\n" in second
    assert controller.current_session_id == "session-2"


def test_buttons_use_current_session_and_return_latest_frame() -> None:
    controller = BridgeController(FakeGateway())
    controller.handle(DeviceCommand("QUERY", "书法班"))

    repeated = controller.handle(DeviceCommand("BUTTON_A"))
    advanced = controller.handle(DeviceCommand("BUTTON_B"))

    assert b"STEP|1|2\n" in repeated
    assert b"LED|4\n" in repeated
    assert b"STEP|2|2\n" in advanced
    assert b"LED|2\n" in advanced


def test_button_without_session_returns_start_query_notice() -> None:
    controller = BridgeController(FakeGateway())

    records = controller.handle(DeviceCommand("BUTTON_A"))

    assert records[0] == b"STATE_BEGIN\n"
    assert records[-1] == b"STATE_END\n"
    assert "BODY|请先说出您要办理的事情\n".encode() in records
    assert "SPEAK|请先说出您要办理的事情\n".encode() in records
    assert b"LED|0\n" in records


def test_stale_session_is_cleared_and_returns_recoverable_notice() -> None:
    gateway = FakeGateway()
    controller = BridgeController(gateway)
    controller.handle(DeviceCommand("QUERY", "书法班"))
    gateway.fail_event = BridgeGatewayError("会话不存在", stale_session=True)

    records = controller.handle(DeviceCommand("BUTTON_B"))

    assert controller.current_session_id is None
    assert "BODY|当前导航已失效，请重新查询\n".encode() in records
    assert b"LED|0\n" in records


def test_gateway_failure_returns_safe_error_without_secret() -> None:
    gateway = FakeGateway()
    gateway.fail_query = BridgeGatewayError("请求失败 secret-api-key")
    controller = BridgeController(gateway)

    records = controller.handle(DeviceCommand("QUERY", "书法班"))

    assert len(records) == 1
    assert records[0].startswith("ERROR|电脑端服务".encode())
    assert b"secret-api-key" not in records[0]
