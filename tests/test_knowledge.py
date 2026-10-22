import json
from pathlib import Path

import pytest

try:
    from community_navigator.knowledge import KnowledgeBase
except ModuleNotFoundError:
    KnowledgeBase = None  # type: ignore[assignment,misc]


def load_demo(path: Path):
    assert KnowledgeBase is not None, "KnowledgeBase has not been implemented"
    return KnowledgeBase.load(path)


def test_demo_knowledge_has_six_unique_led_locations(demo_knowledge_path: Path):
    knowledge = load_demo(demo_knowledge_path)

    assert len(knowledge.data.locations) == 6
    assert {location.id for location in knowledge.data.locations} == {
        "community_entrance",
        "community_center",
        "health_station",
        "activity_room",
        "service_hall",
        "convenience_station",
    }
    assert {location.led_index for location in knowledge.data.locations} == {
        1,
        2,
        3,
        4,
        5,
        6,
    }


def test_demo_knowledge_has_at_least_fifteen_services(demo_knowledge_path: Path):
    knowledge = load_demo(demo_knowledge_path)

    assert len(knowledge.data.services) >= 15
    calligraphy = knowledge.get_service("calligraphy_class")
    assert calligraphy is not None
    assert calligraphy.name == "书法班报名"
    assert {"书法班", "学书法", "报名写毛笔字"}.issubset(calligraphy.aliases)
    assert calligraphy.location_id == "activity_room"
    assert calligraphy.schedule
    assert calligraphy.materials
    assert len(calligraphy.steps) == 3


def test_every_service_references_a_location(demo_knowledge_path: Path):
    knowledge = load_demo(demo_knowledge_path)

    for service in knowledge.data.services:
        assert knowledge.get_location(service.location_id) is not None


def test_demo_records_are_marked_as_demo_data(demo_knowledge_path: Path):
    knowledge = load_demo(demo_knowledge_path)

    assert knowledge.data.is_demo is True
    assert knowledge.data.community_name == "幸福里社区"


def test_loader_rejects_duplicate_led_index(tmp_path: Path):
    assert KnowledgeBase is not None, "KnowledgeBase has not been implemented"
    invalid_path = tmp_path / "duplicate-led.json"
    invalid_path.write_text(
        json.dumps(
            {
                "community_name": "测试社区",
                "is_demo": True,
                "locations": [
                    {
                        "id": "one",
                        "name": "地点一",
                        "led_index": 1,
                        "description": "左侧",
                    },
                    {
                        "id": "two",
                        "name": "地点二",
                        "led_index": 1,
                        "description": "右侧",
                    },
                ],
                "services": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="LED"):
        KnowledgeBase.load(invalid_path)
