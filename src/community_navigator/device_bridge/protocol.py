"""Small UTF-8 line protocol understood by Mind+ block programs."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Literal

from ..models import SessionState


MAX_LINE_BYTES = 1024
MAX_QUERY_CHARACTERS = 200
CommandKind = Literal["HELLO", "QUERY", "BUTTON_A", "BUTTON_B"]


class DeviceProtocolError(ValueError):
    """A malformed or unsupported K10 serial record."""


@dataclass(frozen=True)
class DeviceCommand:
    kind: CommandKind
    payload: str = ""


class LineBuffer:
    """Reassemble arbitrary serial chunks into complete line records."""

    def __init__(self) -> None:
        self._pending = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        self._pending.extend(chunk)
        records: list[bytes] = []
        while True:
            newline_index = self._pending.find(b"\n")
            if newline_index < 0:
                break
            record_length = newline_index + 1
            if record_length > MAX_LINE_BYTES:
                raise DeviceProtocolError("串口指令超过 1024 字节")
            records.append(bytes(self._pending[:record_length]))
            del self._pending[:record_length]
        if len(self._pending) > MAX_LINE_BYTES:
            raise DeviceProtocolError("串口指令超过 1024 字节")
        return records


def parse_device_line(line: bytes) -> DeviceCommand:
    """Parse one complete newline-terminated record from the K10."""

    if len(line) > MAX_LINE_BYTES:
        raise DeviceProtocolError("串口指令超过 1024 字节")
    if not line.endswith(b"\n") or line.count(b"\n") != 1:
        raise DeviceProtocolError("串口指令必须是完整的一行")

    raw = line[:-1]
    if raw.endswith(b"\r"):
        raw = raw[:-1]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DeviceProtocolError("串口指令必须使用 UTF-8") from exc

    if any(unicodedata.category(character).startswith("C") for character in text):
        raise DeviceProtocolError("串口指令不能包含控制字符")

    parts = text.split("|")
    if parts == ["HELLO", "1"]:
        return DeviceCommand("HELLO", "1")
    if parts == ["BUTTON_A"]:
        return DeviceCommand("BUTTON_A")
    if parts == ["BUTTON_B"]:
        return DeviceCommand("BUTTON_B")
    if len(parts) == 2 and parts[0] == "QUERY":
        payload = parts[1]
        if not payload.strip():
            raise DeviceProtocolError("查询内容不能为空")
        if len(payload) > MAX_QUERY_CHARACTERS:
            raise DeviceProtocolError("查询内容不能超过 200 个字符")
        return DeviceCommand("QUERY", payload)
    raise DeviceProtocolError("不支持的串口指令")


def encode_device_state(state: SessionState) -> tuple[bytes, ...]:
    """Encode one server state as an atomic Mind+ state frame."""

    device = state.device
    step_now = (
        device.current_step_index + 1
        if device.current_step_index is not None
        else 0
    )
    led_index = device.active_leds[0] if device.active_leds else 0
    return (
        b"STATE_BEGIN\n",
        _encode_record("MODE", device.screen_mode),
        _encode_record("SERVICE", device.service_name),
        _encode_record("STEP", str(step_now), str(device.total_steps)),
        _encode_record("TITLE", device.title),
        _encode_record("BODY", device.body),
        _encode_record("HELPER", device.helper_text),
        _encode_record("SPEAK", device.speech_text),
        _encode_record("LED", str(led_index)),
        b"STATE_END\n",
    )


def encode_ready(message: str = "智能体已连接") -> bytes:
    return _encode_record("READY", message)


def encode_error(message: str) -> bytes:
    return _encode_record("ERROR", message)


def encode_ping() -> bytes:
    return b"PING\n"


def _encode_record(command: str, *fields: str) -> bytes:
    text = "|".join([command, *(_sanitize_field(field) for field in fields)]) + "\n"
    record = text.encode("utf-8")
    if len(record) > MAX_LINE_BYTES:
        raise DeviceProtocolError("串口指令超过 1024 字节")
    return record


def _sanitize_field(value: str) -> str:
    return value.replace("|", " ").replace("\r", " ").replace("\n", " ")
