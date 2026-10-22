"""REST gateway and session state for the physical K10 bridge."""

from __future__ import annotations

from typing import Literal, Protocol

import httpx
from pydantic import ValidationError

from ..models import DeviceState, PlanResult, SessionState
from .protocol import (
    DeviceCommand,
    encode_device_state,
    encode_error,
    encode_ready,
)


ButtonEvent = Literal["BUTTON_A", "BUTTON_B"]


class BridgeGatewayError(RuntimeError):
    """A safe failure raised by the local navigator gateway."""

    def __init__(self, message: str, *, stale_session: bool = False) -> None:
        super().__init__(message)
        self.stale_session = stale_session


class NavigatorGateway(Protocol):
    def health(self) -> dict[str, object]: ...

    def query(self, text: str) -> SessionState: ...

    def event(self, session_id: str, event_type: ButtonEvent) -> SessionState: ...


class HttpNavigatorGateway:
    """Small synchronous client for the navigator's stable REST contract."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.Client()

    def health(self) -> dict[str, object]:
        response = self._request("GET", "/api/v1/health")
        try:
            payload = response.json()
        except ValueError as exc:
            raise BridgeGatewayError("电脑端服务返回了无效状态") from exc
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise BridgeGatewayError("电脑端服务尚未就绪")
        return payload

    def query(self, text: str) -> SessionState:
        response = self._request("POST", "/api/v1/query", json={"text": text})
        return self._session_from(response)

    def event(self, session_id: str, event_type: ButtonEvent) -> SessionState:
        response = self._request(
            "POST",
            f"/api/v1/sessions/{session_id}/events",
            json={"type": event_type},
            stale_on_404=True,
        )
        return self._session_from(response)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
        stale_on_404: bool = False,
    ) -> httpx.Response:
        try:
            response = self._client.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise BridgeGatewayError("电脑端服务响应超时") from exc
        except httpx.HTTPError as exc:
            raise BridgeGatewayError("无法连接电脑端服务") from exc
        if stale_on_404 and response.status_code == 404:
            raise BridgeGatewayError("当前导航已失效，请重新查询", stale_session=True)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BridgeGatewayError("电脑端服务请求失败") from exc
        return response

    @staticmethod
    def _session_from(response: httpx.Response) -> SessionState:
        try:
            return SessionState.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise BridgeGatewayError("电脑端服务返回了无效导航状态") from exc


class BridgeController:
    """Map parsed device commands to the current navigator session."""

    def __init__(self, gateway: NavigatorGateway) -> None:
        self.gateway = gateway
        self.current_session_id: str | None = None

    def handle(self, command: DeviceCommand) -> tuple[bytes, ...]:
        if command.kind == "HELLO":
            return (encode_ready(),)
        if command.kind == "QUERY":
            return self._query(command.payload)
        if command.kind in {"BUTTON_A", "BUTTON_B"}:
            return self._button(command.kind)
        return (encode_error("不支持的设备指令"),)

    def _query(self, text: str) -> tuple[bytes, ...]:
        try:
            state = self.gateway.query(text)
        except BridgeGatewayError:
            return self._gateway_error()
        self.current_session_id = state.session_id
        return encode_device_state(state)

    def _button(self, event_type: ButtonEvent) -> tuple[bytes, ...]:
        if self.current_session_id is None:
            return _notice_frame("请先说出您要办理的事情")
        try:
            state = self.gateway.event(self.current_session_id, event_type)
        except BridgeGatewayError as exc:
            if exc.stale_session:
                self.current_session_id = None
                return _notice_frame("当前导航已失效，请重新查询")
            return self._gateway_error()
        return encode_device_state(state)

    @staticmethod
    def _gateway_error() -> tuple[bytes, ...]:
        return (encode_error("电脑端服务暂时不可用，请联系工作人员。"),)


def _notice_frame(message: str) -> tuple[bytes, ...]:
    state = SessionState(
        session_id="bridge-notice",
        status="error",
        plan=PlanResult(
            status="error",
            summary=message,
            confirmation_message=message,
        ),
        device=DeviceState(
            screen_mode="error",
            title="请重新查询",
            body=message,
            helper_text="地图指示灯保持关闭",
            speech_text=message,
            speech_status="queued",
            active_leds=[],
        ),
    )
    return encode_device_state(state)
