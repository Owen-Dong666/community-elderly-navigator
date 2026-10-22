"""USB serial bridge for the Mind+ K10 device program."""

from .controller import (
    BridgeController,
    BridgeGatewayError,
    HttpNavigatorGateway,
    NavigatorGateway,
)
from .protocol import (
    DeviceCommand,
    DeviceProtocolError,
    LineBuffer,
    encode_device_state,
    encode_error,
    encode_ping,
    encode_ready,
    parse_device_line,
)
from .runtime import BridgeRuntime, SerialLike, open_serial_port, serve_with_retries

__all__ = [
    "BridgeController",
    "BridgeGatewayError",
    "BridgeRuntime",
    "DeviceCommand",
    "DeviceProtocolError",
    "HttpNavigatorGateway",
    "LineBuffer",
    "NavigatorGateway",
    "SerialLike",
    "encode_device_state",
    "encode_error",
    "encode_ping",
    "encode_ready",
    "open_serial_port",
    "parse_device_line",
    "serve_with_retries",
]
