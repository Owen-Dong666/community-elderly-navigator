"""Serial polling runtime for the Mind+ K10 USB connection."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

import serial

from .controller import BridgeController, BridgeGatewayError, NavigatorGateway
from .protocol import (
    DeviceProtocolError,
    LineBuffer,
    encode_error,
    encode_ping,
    parse_device_line,
)


class SerialLike(Protocol):
    @property
    def in_waiting(self) -> int: ...

    def read(self, size: int) -> bytes: ...

    def write(self, data: bytes) -> int: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


class BridgeRuntime:
    """Poll a serial port, preserving complete line boundaries."""

    def __init__(
        self,
        port: SerialLike,
        controller: BridgeController,
        *,
        heartbeat_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        interline_delay_seconds: float = 0.03,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.port = port
        self.controller = controller
        self.heartbeat_seconds = heartbeat_seconds
        self.clock = clock
        self.interline_delay_seconds = interline_delay_seconds
        self.sleep = sleep
        self._buffer = LineBuffer()
        self._last_heartbeat = clock()

    def poll_once(self) -> None:
        now = self.clock()
        if now - self._last_heartbeat >= self.heartbeat_seconds:
            self._write_records((encode_ping(),))
            self._last_heartbeat = now

        if self.port.in_waiting <= 0:
            return
        chunk = self.port.read(self.port.in_waiting)
        try:
            records = self._buffer.feed(chunk)
        except DeviceProtocolError:
            self._buffer = LineBuffer()
            self._write_protocol_error()
            return

        for record in records:
            try:
                command = parse_device_line(record)
            except DeviceProtocolError:
                self._write_protocol_error()
                continue
            self._write_records(self.controller.handle(command))

    def _write_protocol_error(self) -> None:
        self._write_records((encode_error("设备指令格式无效，请重试。"),))

    def _write_records(self, records: tuple[bytes, ...]) -> None:
        for index, record in enumerate(records):
            self.port.write(record)
            if index + 1 < len(records):
                self.sleep(self.interline_delay_seconds)
        self.port.flush()


def open_serial_port(port: str, baud_rate: int = 115200) -> SerialLike:
    """Open K10 serial 0 without a blocking read timeout."""

    return serial.Serial(port=port, baudrate=baud_rate, timeout=0)


def serve_with_retries(
    port_name: str,
    gateway: NavigatorGateway,
    *,
    baud_rate: int = 115200,
    serial_opener: Callable[[str, int], SerialLike] = open_serial_port,
    runtime_factory: Callable[[SerialLike, BridgeController], BridgeRuntime] = BridgeRuntime,
    sleep: Callable[[float], None] = time.sleep,
    output: Callable[[str], None] = print,
    retry_delays: tuple[float, ...] = (1.0, 2.0, 4.0),
) -> int:
    """Serve the K10 until interrupted, retrying serial failures finitely."""

    try:
        gateway.health()
    except BridgeGatewayError:
        output("无法连接电脑端智能体，请先启动导航服务。")
        return 1

    for attempt in range(len(retry_delays) + 1):
        port: SerialLike | None = None
        try:
            port = serial_opener(port_name, baud_rate)
        except (serial.SerialException, OSError):
            output("COM端口被占用，请先在 Mind+ 中断开设备并关闭串口监视。")
            if attempt == len(retry_delays):
                return 1
            sleep(retry_delays[attempt])
            continue

        try:
            runtime = runtime_factory(port, BridgeController(gateway))
            while True:
                runtime.poll_once()
                sleep(0.02)
        except KeyboardInterrupt:
            return 0
        except (serial.SerialException, OSError):
            output("串口连接已中断，正在重试。")
            if attempt == len(retry_delays):
                return 1
            sleep(retry_delays[attempt])
        finally:
            port.close()
    return 1
