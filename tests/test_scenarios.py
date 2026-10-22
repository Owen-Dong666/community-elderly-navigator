"""End-to-end classroom demonstration scenarios."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from community_navigator.api import create_app
from community_navigator.config import Settings
from community_navigator.planning import UNKNOWN_INFORMATION_MESSAGE
from community_navigator.providers import MockProvider


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(demo_knowledge_path) -> TestClient:
    return TestClient(
        create_app(
            settings=Settings(
                model_provider="mock",
                knowledge_path=demo_knowledge_path,
            ),
            provider=MockProvider(),
        )
    )


@pytest.mark.parametrize(
    ("query", "service_id", "location_id", "led"),
    [
        ("我想报名参加书法班", "calligraphy_class", "activity_room", 4),
        ("想学太极", "tai_chi_class", "community_entrance", 1),
        ("老人合唱队什么时候活动", "choir_activity", "activity_room", 4),
        ("教老人用手机的课", "smartphone_class", "community_center", 2),
        ("我想参加健康讲座", "health_lecture", "community_center", 2),
        ("哪里可以免费量血压", "blood_pressure_check", "health_station", 3),
        ("我想问社保", "social_security_consultation", "service_hall", 5),
        ("怎样申请高龄补贴", "senior_allowance", "service_hall", 5),
        ("我要申请居家养老服务", "home_care_application", "service_hall", 5),
        ("助餐点在哪里", "meal_service", "convenience_station", 6),
        ("家里水管坏了找谁", "repair_service", "convenience_station", 6),
        ("请问社区怎么借书", "library_borrowing", "community_center", 2),
    ],
)
def test_known_service_scenarios(
    client: TestClient,
    query: str,
    service_id: str,
    location_id: str,
    led: int,
) -> None:
    response = client.post("/api/v1/query", json={"text": query})

    assert response.status_code == 200
    state = response.json()
    assert state["status"] == "ready"
    assert state["plan"]["service_id"] == service_id
    assert state["plan"]["location_id"] == location_id
    assert state["plan"]["steps"]
    assert state["device"]["active_leds"] == [led]


@pytest.mark.parametrize(
    "query",
    [
        "我想办理护照",
        "明天天气怎么样",
        "公交车什么时候来",
        "我想购买火车票",
        "哪里可以给宠物洗澡",
    ],
)
def test_unknown_service_scenarios_are_safely_declined(
    client: TestClient, query: str
) -> None:
    response = client.post("/api/v1/query", json={"text": query})

    assert response.status_code == 200
    state = response.json()
    assert state["status"] == "not_found"
    assert state["plan"]["confirmation_message"] == UNKNOWN_INFORMATION_MESSAGE
    assert state["device"]["active_leds"] == []


def test_complete_calligraphy_flow_remains_traceable(client: TestClient) -> None:
    state = client.post(
        "/api/v1/query", json={"text": "我想报名参加书法班"}
    ).json()
    session_id = state["session_id"]
    original_sources = state["plan"]["source_record_ids"]
    total_steps = len(state["plan"]["steps"])

    repeated = client.post(
        f"/api/v1/sessions/{session_id}/events",
        json={"type": "BUTTON_A"},
    ).json()
    assert repeated["device"]["current_step_index"] == 0

    for _ in range(total_steps):
        state = client.post(
            f"/api/v1/sessions/{session_id}/events",
            json={"type": "BUTTON_B"},
        ).json()

    assert state["ended"] is True
    assert state["device"]["screen_mode"] == "idle"
    assert state["device"]["active_leds"] == []
    assert state["plan"]["source_record_ids"] == original_sources == [
        "calligraphy_class"
    ]


def test_readme_orders_api_before_releasing_mindplus_and_starting_bridge() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required_markers = (
        "community-navigator.exe",
        "community-navigator-bridge.exe --port COM",
        "Mind+ 串口占用",
        "qwen3:0.6b",
        "mindplus/社区老人办事导航员-K10.mp",
    )

    for marker in required_markers:
        assert marker in readme

    api_start = readme.index("community-navigator.exe")
    release_serial = readme.index("断开 Mind+ 串口")
    bridge_start = readme.index("community-navigator-bridge.exe --port COM")
    assert api_start < release_serial < bridge_start
