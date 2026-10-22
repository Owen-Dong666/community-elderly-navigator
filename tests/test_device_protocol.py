"""Mind+ K10 line-protocol contract tests."""

from __future__ import annotations

import pytest

from community_navigator.device_bridge.protocol import (
    DeviceCommand,
    DeviceProtocolError,
    LineBuffer,
    encode_device_state,
    encode_error,
    encode_ping,
    encode_ready,
    parse_device_line,
)
from community_navigator.models import DeviceState, PlanResult, PlanStep, SessionState


def test_parse_hello_query_and_buttons() -> None:
    assert parse_device_line(b"HELLO|1\n") == DeviceCommand("HELLO", "1")
    assert parse_device_line("QUERY|我想报名参加书法班\n".encode()) == DeviceCommand(
        "QUERY", "我想报名参加书法班"
    )
    assert parse_device_line(b"BUTTON_A\n") == DeviceCommand("BUTTON_A")
    assert parse_device_line(b"BUTTON_B\n") == DeviceCommand("BUTTON_B")


@pytest.mark.parametrize(
    "line",
    [
        b"QUERY|   \n",
        b"QUERY|calligraphy|change-location\n",
        b"QUERY|calligraphy\x01\n",
        b"QUERY|\xff\n",
        b"HELLO|2\n",
        b"BUTTON_C\n",
    ],
)
def test_query_rejects_pipe_control_character_invalid_utf8_and_blank_text(
    line: bytes,
) -> None:
    with pytest.raises(DeviceProtocolError):
        parse_device_line(line)


def test_byte_limit_counts_utf8_bytes_not_python_characters() -> None:
    accepted = "字" * 200
    assert len(accepted) == 200
    assert len(accepted.encode("utf-8")) == 600
    assert parse_device_line(f"QUERY|{accepted}\n".encode()).payload == accepted

    with pytest.raises(DeviceProtocolError, match="200"):
        parse_device_line(f"QUERY|{accepted}字\n".encode())


def test_line_buffer_waits_for_fragment_completion() -> None:
    buffer = LineBuffer()

    assert buffer.feed(b"QUE") == []
    assert buffer.feed("RY|书法班\n".encode()) == ["QUERY|书法班\n".encode()]


def test_line_buffer_returns_multiple_complete_lines_and_keeps_tail() -> None:
    buffer = LineBuffer()

    assert buffer.feed(b"BUTTON_A\nBUTTON_B\nQUE") == [
        b"BUTTON_A\n",
        b"BUTTON_B\n",
    ]
    assert buffer.feed(b"RY|calligraphy\n") == [b"QUERY|calligraphy\n"]


def test_line_buffer_rejects_an_overlong_unterminated_line() -> None:
    buffer = LineBuffer()

    assert buffer.feed((b"x" * 1023) + b"\n") == [(b"x" * 1023) + b"\n"]

    with pytest.raises(DeviceProtocolError, match="1024"):
        buffer.feed(b"x" * 1025)


def _ready_state(device: DeviceState | None = None) -> SessionState:
    plan = PlanResult(
        status="ready",
        service_id="calligraphy_class",
        service_name="书法班报名",
        location_id="activity_room",
        schedule="每周三上午九点",
        steps=[
            PlanStep(index=1, title="准备资料", instruction="带上居民卡。", speech="请带上居民卡。"),
            PlanStep(index=2, title="前往地点", instruction="前往活动室。", speech="请前往活动室。"),
            PlanStep(index=3, title="登记信息", instruction="登记姓名和电话。", speech="请登记姓名和电话。"),
        ],
    )
    return SessionState(
        session_id="session-1",
        status="ready",
        plan=plan,
        device=device
        or DeviceState(
            screen_mode="display",
            service_name="书法班报名",
            current_step_index=0,
            total_steps=3,
            title="准备资料",
            body="带上居民卡。",
            helper_text="步骤 1 / 3",
            speech_text="请带上居民卡。",
            speech_status="queued",
            active_leds=[4],
        ),
    )


def test_ready_state_encodes_complete_atomic_frame() -> None:
    records = encode_device_state(_ready_state())

    assert records == (
        b"STATE_BEGIN\n",
        "MODE|display\n".encode(),
        "SERVICE|书法班报名\n".encode(),
        b"STEP|1|3\n",
        "TITLE|准备资料\n".encode(),
        "BODY|带上居民卡。\n".encode(),
        "HELPER|步骤 1 / 3\n".encode(),
        "SPEAK|请带上居民卡。\n".encode(),
        b"LED|4\n",
        b"STATE_END\n",
    )
    assert all(record.endswith(b"\n") for record in records)
    assert all(record.count(b"\n") == 1 for record in records)
    assert all(len(record) <= 1024 for record in records)


def test_unknown_state_encodes_led_zero_and_confirmation_speech() -> None:
    message = "当前资料中没有这项信息，请向社区工作人员确认"
    state = SessionState(
        session_id="session-unknown",
        status="not_found",
        plan=PlanResult(
            status="not_found",
            summary=message,
            confirmation_message=message,
        ),
        device=DeviceState(
            screen_mode="error",
            title="需要人工确认",
            body=message,
            helper_text="地图指示灯保持关闭",
            speech_text=message,
            speech_status="queued",
            active_leds=[],
        ),
    )

    records = encode_device_state(state)

    assert b"STEP|0|0\n" in records
    assert b"LED|0\n" in records
    assert f"SPEAK|{message}\n".encode() in records


def test_output_fields_replace_pipe_cr_and_lf_with_spaces() -> None:
    device = DeviceState(
        screen_mode="display",
        service_name="服务|名称\n二",
        current_step_index=0,
        total_steps=3,
        title="标题\r二",
        body="正文|二",
        helper_text="帮助\n二",
        speech_text="播报|二",
        speech_status="queued",
        active_leds=[3],
    )

    records = encode_device_state(_ready_state(device))

    assert "SERVICE|服务 名称 二\n".encode() in records
    assert "TITLE|标题 二\n".encode() in records
    assert "BODY|正文 二\n".encode() in records
    assert "HELPER|帮助 二\n".encode() in records
    assert "SPEAK|播报 二\n".encode() in records


def test_control_lines_are_utf8_newline_records() -> None:
    assert encode_ready() == "READY|智能体已连接\n".encode()
    assert encode_error("错误|请检查\n服务") == "ERROR|错误 请检查 服务\n".encode()
    assert encode_ping() == b"PING\n"
