"""Local Uvicorn entry point."""

from __future__ import annotations

import argparse

import uvicorn

from .api import create_app


app = create_app()


def run() -> None:
    parser = argparse.ArgumentParser(description="启动社区办事导航员")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--reload", action="store_true")
    options = parser.parse_args()
    uvicorn.run(
        "community_navigator.main:app",
        host=options.host,
        port=options.port,
        reload=options.reload,
    )


if __name__ == "__main__":
    run()
