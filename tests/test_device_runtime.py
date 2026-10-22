"""Serial runtime and CLI tests for the physical K10 bridge."""

from __future__ import annotations

import serial

from community_navigator.device_bridge.cli import run
from community_navigator.device_bridge.controller import BridgeGatewayError
from community_navigator.device_bridge.protocol import DeviceCommand
from community_navigator.device_bridge.runtime import BridgeRuntime, serve_with_retries


class FakeSerial:
    def __init__(self, incoming: bytes = b"") -> None:
        self.incoming = bytearray(incoming)
        self.writes: list[bytes] = []
        self.flush_count = 0
        self.closed = False

    @property
    def in_waiting(self) -> int:
        return len(self.incoming)

    def read(self, size: int) -> bytes:
        result = bytes(self.incoming[:size])
        del self.incoming[:size]
        return result

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        self.flush_count += 1

    def close(self) -> None:
        self.closed = True


class RecordingController:
    def handle(self, command: DeviceCommand) -> tuple[bytes, ...]:
        if command.kind == "HELLO":
            return (b"READY|ok\n",)
        if command.kind == "QUERY":
            return (b"STATE_BEGIN\n", b"LED|4\n", b"STATE_END\n")
        return (f"EVENT|{command.kind}\n".encode(),)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_runtime_handles_fragmented_and_coalesced_device_lines() -> None:
    port = FakeSerial(b"HEL")
    runtime = BridgeRuntime(port, RecordingController(), sleep=lambda seconds: None)

    runtime.poll_once()
    assert port.writes == []

    port.incoming.extend(b"LO|1\nBUTTON_A\n")
    runtime.poll_once()

    assert port.writes == [b"READY|ok\n", b"EVENT|BUTTON_A\n"]
    assert port.flush_count == 2


def test_runtime_sends_ping_at_two_seconds_not_on_every_poll() -> None:
    port = FakeSerial()
    clock = FakeClock()
    runtime = BridgeRuntime(
        port,
        RecordingController(),
        clock=clock,
        sleep=lambda seconds: None,
    )

    runtime.poll_once()
    clock.now = 1.99
    runtime.poll_once()
    assert port.writes == []

    clock.now = 2.0
    runtime.poll_once()
    clock.now = 2.1
    runtime.poll_once()
    clock.now = 4.0
    runtime.poll_once()

    assert port.writes == [b"PING\n", b"PING\n"]


def test_runtime_paces_multiline_frames_in_order() -> None:
    port = FakeSerial("QUERY|书法班\n".encode())
    sleeps: list[float] = []
    runtime = BridgeRuntime(port, RecordingController(), sleep=sleeps.append)

    runtime.poll_once()

    assert port.writes == [b"STATE_BEGIN\n", b"LED|4\n", b"STATE_END\n"]
    assert sleeps == [0.03, 0.03]
    assert port.flush_count == 1


def test_runtime_turns_protocol_error_into_safe_error_frame() -> None:
    port = FakeSerial(b"QUERY|unsafe|field\n")
    runtime = BridgeRuntime(port, RecordingController(), sleep=lambda seconds: None)

    runtime.poll_once()

    assert len(port.writes) == 1
    assert port.writes[0].startswith("ERROR|设备指令格式无效".encode())
    assert b"unsafe" not in port.writes[0]


class HealthyGateway:
    def __init__(self, events: list[str] | None = None) -> None:
        self.events = events if events is not None else []

    def health(self) -> dict[str, object]:
        self.events.append("health")
        return {"status": "ok", "provider": "mock", "is_demo": True}


class ImmediateStopRuntime:
    def poll_once(self) -> None:
        raise KeyboardInterrupt


def test_cli_checks_health_before_opening_serial_port() -> None:
    events: list[str] = []
    port = FakeSerial()

    def opener(port_name: str, baud_rate: int) -> FakeSerial:
        events.append(f"open:{port_name}:{baud_rate}")
        return port

    result = serve_with_retries(
        "COM7",
        HealthyGateway(events),
        serial_opener=opener,
        runtime_factory=lambda serial_port, controller: ImmediateStopRuntime(),
        sleep=lambda seconds: None,
        output=lambda message: None,
    )

    assert result == 0
    assert events == ["health", "open:COM7:115200"]
    assert port.closed is True


def test_cli_uses_115200_and_explicit_port() -> None:
    seen: dict[str, object] = {}

    def gateway_factory(base_url: str) -> HealthyGateway:
        seen["base_url"] = base_url
        return HealthyGateway()

    def serve(port: str, gateway: HealthyGateway, *, baud_rate: int) -> int:
        seen["port"] = port
        seen["gateway"] = gateway
        seen["baud_rate"] = baud_rate
        return 0

    result = run(
        ["--port", "COM9"],
        gateway_factory=gateway_factory,
        serve=serve,
    )

    assert result == 0
    assert seen["base_url"] == "http://127.0.0.1:8000"
    assert seen["port"] == "COM9"
    assert isinstance(seen["gateway"], HealthyGateway)
    assert seen["baud_rate"] == 115200


def _run_busy_bridge() -> tuple[int, list[float], list[str], int]:
    sleeps: list[float] = []
    output: list[str] = []
    attempts = 0

    def busy_opener(port_name: str, baud_rate: int) -> FakeSerial:
        nonlocal attempts
        attempts += 1
        raise serial.SerialException("Access is denied: secret-device-detail")

    result = serve_with_retries(
        "COM5",
        HealthyGateway(),
        serial_opener=busy_opener,
        sleep=sleeps.append,
        output=output.append,
    )
    return result, sleeps, output, attempts


def test_port_in_use_message_tells_user_to_disconnect_mindplus() -> None:
    result, _, output, attempts = _run_busy_bridge()

    assert result == 1
    assert attempts == 4
    assert output == [
        "COM端口被占用，请先在 Mind+ 中断开设备并关闭串口监视。"
    ] * 4
    assert all("secret-device-detail" not in message for message in output)


def test_retry_delays_are_exactly_one_two_four_seconds() -> None:
    result, sleeps, _, attempts = _run_busy_bridge()

    assert result == 1
    assert attempts == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_cli_never_prints_api_key_environment_value(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_API_KEY", "super-secret-api-key")
    output: list[str] = []

    class FailingHealthGateway(HealthyGateway):
        def health(self) -> dict[str, object]:
            raise BridgeGatewayError("failed with super-secret-api-key")

    result = serve_with_retries(
        "COM5",
        FailingHealthGateway(),
        serial_opener=lambda port, baud: FakeSerial(),
        sleep=lambda seconds: None,
        output=output.append,
    )

    assert result == 1
    assert output == ["无法连接电脑端智能体，请先启动导航服务。"]
    assert "super-secret-api-key" not in "".join(output)
