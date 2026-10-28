import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent


def test_launcher_checks_only_loopback_even_if_proxy_is_configured(monkeypatch):
    from start_simulator import probe_service

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            content = "K10 社区服务导航".encode("utf-8")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(content)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.delenv("no_proxy", raising=False)
        assert probe_service(f"http://127.0.0.1:{server.server_port}/") is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_full_ollama_http_flow_preserves_followup_context():
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app

    received = []

    class OllamaHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_json(self, value):
            content = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            assert self.path == "/api/tags"
            self.send_json({"models": [{"name": "test-model"}]})

        def do_POST(self):
            assert self.path == "/api/chat"
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(payload)
            choice = ({"action": "start", "service_id": "calligraphy", "fact_ids": ["calligraphy.location"]}
                      if len(received) == 1 else
                      {"action": "answer", "service_id": "calligraphy", "fact_ids": ["calligraphy.schedule"]})
            self.send_json({"message": {"content": json.dumps(choice, ensure_ascii=False)}})

    server = ThreadingHTTPServer(("127.0.0.1", 0), OllamaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        settings = Settings(provider="ollama", ollama_base_url=f"http://127.0.0.1:{server.server_port}", ollama_model="test-model")
        with TestClient(create_app(settings=settings)) as client:
            assert client.get("/api/v1/health").json()["status"] == "ready"
            session = client.post("/api/v1/sessions").json()["session_id"]
            first = client.post(f"/api/v1/sessions/{session}/messages", json={"text": "我想学写字"}).json()
            assert first["device"]["led"] == 4
            client.post(f"/api/v1/sessions/{session}/events", json={"event": "BUTTON_B"})
            followup = client.post(f"/api/v1/sessions/{session}/messages", json={"text": "刚才那个班什么时候上课？"}).json()
            assert followup["device"]["step_index"] == 1
            assert followup["sources"][0]["id"] == "calligraphy.schedule"
        assert received[1]["model"] == "test-model"
        assert any(item["content"] == "我想学写字" for item in received[1]["messages"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_local_server_serves_page_and_reports_missing_model_without_fallback():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = os.environ.copy()
    environment.update(MODEL_PROVIDER="ollama", OLLAMA_MODEL="", OLLAMA_BASE_URL="http://127.0.0.1:11434")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                with urlopen(base + "/", timeout=1) as response:
                    assert "离线模拟演示" in response.read().decode("utf-8")
                break
            except URLError:
                assert process.poll() is None and time.monotonic() < deadline
                time.sleep(0.1)
        with urlopen(base + "/api/v1/health", timeout=2) as response:
            assert json.load(response)["status"] == "unavailable"
        request = Request(base + "/api/v1/sessions", data=b"{}", headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=2) as response:
            session = json.load(response)["session_id"]
        request = Request(base + f"/api/v1/sessions/{session}/messages", data=json.dumps({"text": "书法班"}).encode(), headers={"Content-Type": "application/json"})
        try:
            urlopen(request, timeout=2)
            raise AssertionError("unconfigured model should not return a preset response")
        except HTTPError as error:
            result = json.load(error)
            assert error.code == 502 and result["device"]["led"] == 0 and result["reply"] == ""
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
