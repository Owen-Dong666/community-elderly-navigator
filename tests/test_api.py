"""REST contract tests for the computer-side navigator service."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from community_navigator.api import create_app
from community_navigator.config import Settings
from community_navigator.planning import UNKNOWN_INFORMATION_MESSAGE
from community_navigator.providers import MockProvider


class CountingMockProvider(MockProvider):
    def __init__(self) -> None:
        self.calls = 0

    def generate_plan(self, prompt: str, schema: dict[str, object]) -> str:
        self.calls += 1
        return super().generate_plan(prompt, schema)


@pytest.fixture
def settings(demo_knowledge_path) -> Settings:
    return Settings(
        model_provider="mock",
        knowledge_path=demo_knowledge_path,
        expose_knowledge_api=True,
    )


@pytest.fixture
def provider() -> CountingMockProvider:
    return CountingMockProvider()


@pytest.fixture
def client(settings: Settings, provider: CountingMockProvider) -> TestClient:
    return TestClient(create_app(settings=settings, provider=provider))


def test_health_reports_demo_and_provider(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "mock", "is_demo": True}


def test_calligraphy_query_returns_session_first_step_and_activity_led(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/query", json={"text": "我想报名参加书法班"})

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["status"] == "ready"
    assert body["plan"]["service_id"] == "calligraphy_class"
    assert body["plan"]["location_id"] == "activity_room"
    assert body["device"]["current_step_index"] == 0
    assert body["device"]["active_leds"] == [4]


def test_unknown_query_returns_confirmation_and_no_led(client: TestClient) -> None:
    response = client.post("/api/v1/query", json={"text": "我想办理护照"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_found"
    assert body["plan"]["confirmation_message"] == UNKNOWN_INFORMATION_MESSAGE
    assert body["device"]["active_leds"] == []


def test_events_repeat_advance_and_end_session(client: TestClient) -> None:
    created = client.post(
        "/api/v1/query", json={"text": "我想报名参加书法班"}
    ).json()
    session_id = created["session_id"]

    repeated = client.post(
        f"/api/v1/sessions/{session_id}/events", json={"type": "BUTTON_A"}
    ).json()
    assert repeated["device"]["current_step_index"] == 0

    state = repeated
    while not state["ended"]:
        state = client.post(
            f"/api/v1/sessions/{session_id}/events", json={"type": "BUTTON_B"}
        ).json()

    assert state["device"]["screen_mode"] == "idle"
    assert state["device"]["active_leds"] == []
    fetched = client.get(f"/api/v1/sessions/{session_id}")
    assert fetched.status_code == 200
    assert fetched.json() == state


def test_missing_session_returns_stable_404(client: TestClient) -> None:
    get_response = client.get("/api/v1/sessions/missing")
    event_response = client.post(
        "/api/v1/sessions/missing/events", json={"type": "BUTTON_A"}
    )

    assert get_response.status_code == 404
    assert get_response.json() == {"detail": "会话不存在"}
    assert event_response.status_code == 404
    assert event_response.json() == {"detail": "会话不存在"}


@pytest.mark.parametrize(
    "text",
    ["   ", "字" * 201, "书法班\u0001改地点"],
)
def test_invalid_query_returns_422_without_calling_planner(
    client: TestClient,
    provider: CountingMockProvider,
    text: str,
) -> None:
    response = client.post("/api/v1/query", json={"text": text})

    assert response.status_code == 422
    assert provider.calls == 0


def test_knowledge_route_exposes_demo_records_but_no_provider_secret(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/knowledge/services")

    assert response.status_code == 200
    body = response.json()
    assert body["community_name"] == "幸福里社区"
    assert body["is_demo"] is True
    assert len(body["services"]) >= 15
    assert "model_api_key" not in response.text


def test_knowledge_route_can_be_disabled(demo_knowledge_path) -> None:
    app = create_app(
        settings=Settings(
            model_provider="mock",
            knowledge_path=demo_knowledge_path,
            expose_knowledge_api=False,
            model_api_key="never-expose-this",
        ),
        provider=MockProvider(),
    )

    response = TestClient(app).get("/api/v1/knowledge/services")

    assert response.status_code == 404
    assert "never-expose-this" not in response.text


def test_simulator_page_has_accessible_controls_and_six_map_leds(
    client: TestClient,
) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert html.count("data-led-index=") == 6
    assert 'data-action="BUTTON_A"' in html
    assert 'data-action="BUTTON_B"' in html
    assert 'id="voice-button"' in html
    assert 'id="query-input"' in html
    assert "演示数据" in html
    assert 'aria-label="语音输入"' in html
    assert 'aria-live="polite"' in html


def test_static_javascript_uses_api_routes_without_model_secret(
    client: TestClient,
) -> None:
    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert '"/api/v1/query"' in script
    assert "/api/v1/sessions/" in script
    assert "MODEL_API_KEY" not in script
    assert "Bearer " not in script
    assert "speechSynthesis" in script
    assert "webkitSpeechRecognition" in script
