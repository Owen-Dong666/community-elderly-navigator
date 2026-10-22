"""Command-line entry point for the physical K10 serial bridge."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from .controller import HttpNavigatorGateway, NavigatorGateway
from .runtime import serve_with_retries


GatewayFactory = Callable[[str], NavigatorGateway]
ServeFunction = Callable[..., int]


def run(
    argv: Sequence[str] | None = None,
    *,
    gateway_factory: GatewayFactory = HttpNavigatorGateway,
    serve: ServeFunction = serve_with_retries,
) -> int:
    parser = argparse.ArgumentParser(
        description="社区老人办事导航员 K10 USB 串口桥",
    )
    parser.add_argument("--port", required=True, help="K10 的 COM 端口，例如 COM5")
    parser.add_argument(
        "--api-base",
        default="http://127.0.0.1:8000",
        help="电脑端智能体服务地址",
    )
    parser.add_argument(
        "--baud-rate",
        type=int,
        choices=(115200,),
        default=115200,
        help="K10 串口波特率（固定为 115200）",
    )
    args = parser.parse_args(argv)
    gateway = gateway_factory(args.api_base)
    return serve(args.port, gateway, baud_rate=args.baud_rate)
