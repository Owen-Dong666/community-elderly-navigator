"""Versioned UTF-8 JSON Lines protocol tests."""

from __future__ import annotations

import json

import pytest

from community_navigator.models import SerialMessage
from community_navigator.serial_protocol import (
    MAX_MESSAGE_BYTES,
    ProtocolError,
    decode_message,
    encode_message,
)


@pytest.mark.parametrize("message_type", ["QUERY", "BUTTON_A", "BUTTON_B", "DEVICE_STATE"])
def test_all_message_types_round_trip_as_one_utf8_line(message_type: str) -> None:
    message = SerialMessage(
        type=message_type,
        request_id="请求-1",
        payload={"text": "我要报名书法班", "step": 2},
    )

    encoded = encode_message(message)

    assert encoded.endswith(b"\n")
    assert not encoded.endswith(b"\n\n")
    assert "我要报名书法班" in encoded.decode("utf-8")
    assert decode_message(encoded) == message


@pytest.mark.parametrize(
    "raw",
    [
        b'{"type":"QUERY","request_id":"1","payload":{}}\n',
        b'{"version":1,"type":"BUTTON_X","request_id":"1","payload":{}}\n',
        b"not-json\n",
        b"\xff\n",
    ],
)
def test_decode_rejects_missing_version_unknown_type_and_invalid_data(raw: bytes) -> None:
    with pytest.raises(ProtocolError):
        decode_message(raw)


def test_decode_rejects_payload_over_maximum_line_size() -> None:
    raw = json.dumps(
        {
            "version": 1,
            "type": "QUERY",
            "request_id": "large",
            "payload": {"text": "字" * MAX_MESSAGE_BYTES},
        },
        ensure_ascii=False,
    ).encode("utf-8") + b"\n"

    with pytest.raises(ProtocolError, match="过长"):
        decode_message(raw)


def test_decode_requires_exactly_one_complete_line() -> None:
    message = SerialMessage(type="BUTTON_A", request_id="one")
    encoded = encode_message(message)

    with pytest.raises(ProtocolError, match="一行"):
        decode_message(encoded + encoded)
