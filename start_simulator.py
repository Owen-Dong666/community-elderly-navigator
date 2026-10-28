"""Start the loopback service and open the navigator without downloading anything."""
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser


ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8000/"


def probe_service(url=URL):
    opener = build_opener(ProxyHandler({}))
    with opener.open(url, timeout=0.5) as response:
        page = response.read(5000).decode("utf-8", errors="replace")
    return "K10 社区服务导航" in page


def main():
    try:
        import fastapi  # noqa: F401
        import httpx  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        print("运行依赖尚未安装，请先按照 README.md 完成安装。", flush=True)
        return 1

    print("正在启动本地导航服务。关闭此窗口或按 Ctrl+C 可结束服务。", flush=True)
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                print("本地服务启动失败，请检查 8000 端口及上方错误信息。", flush=True)
                return 1
            try:
                if probe_service():
                    break
            except (URLError, OSError):
                pass
            time.sleep(0.25)
        else:
            print("本地服务未能及时启动，请检查上方错误信息。", flush=True)
            return 1

        if process.poll() is not None:
            print("本地服务启动失败，请检查 8000 端口。", flush=True)
            return 1
        print(f"服务已启动：{URL}", flush=True)
        if not webbrowser.open(URL):
            print("请在浏览器中手动打开上面的地址。", flush=True)
        return process.wait()
    except KeyboardInterrupt:
        print("正在关闭本地服务。", flush=True)
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
