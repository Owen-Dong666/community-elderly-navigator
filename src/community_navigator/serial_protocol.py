"""Small versioned JSON Lines protocol for the future USB serial bridge."""

from __future__ import annotations

import json

from pydantic import ValidationError

from .models import SerialMessage


MAX_MESSAGE_BYTES = 4096


class ProtocolError(ValueError):
    """Malformed or unsupported serial record."""


def encode_message(message: SerialMessage) -> bytes:
    record = json.dumps(
        message.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    if len(record) > MAX_MESSAGE_BYTES:
        raise ProtocolError("串口消息过长")
    return record


def decode_message(line: bytes) -> SerialMessage:
    if len(line) > MAX_MESSAGE_BYTES:
        raise ProtocolError("串口消息过长")
    if not line.endswith(b"\n") or line.count(b"\n") != 1:
        raise ProtocolError("每次必须提供完整的一行消息")
    try:
        raw = json.loads(line[:-1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("串口消息不是有效的 UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ProtocolError("串口消息必须是 JSON 对象")
    if "version" not in raw:
        raise ProtocolError("串口消息缺少协议版本")
    try:
        return SerialMessage.model_validate(raw)
    except ValidationError as exc:
        raise ProtocolError("串口消息结构无效") from exc
