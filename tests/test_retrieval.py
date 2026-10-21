from pathlib import Path

import pytest

from community_navigator.knowledge import KnowledgeBase

try:
    from community_navigator.retrieval import ServiceRetriever
except ModuleNotFoundError:
    ServiceRetriever = None  # type: ignore[assignment,misc]


def make_retriever(path: Path):
    assert ServiceRetriever is not None, "ServiceRetriever has not been implemented"
    return ServiceRetriever(KnowledgeBase.load(path))


@pytest.mark.parametrize(
    ("query", "service_id", "location_id"),
    [
        ("我想报名参加书法班", "calligraphy_class", "activity_room"),
        ("哪里可以测血压", "blood_pressure_check", "health_station"),
        ("老人助餐在哪里", "meal_service", "convenience_station"),
        ("家里水管坏了找谁", "repair_service", "convenience_station"),
    ],
)
def test_known_questions_select_expected_service(
    demo_knowledge_path: Path,
    query: str,
    service_id: str,
    location_id: str,
):
    decision = make_retriever(demo_knowledge_path).decide(query)

    assert decision.status == "matched"
    assert decision.results[0].service.id == service_id
    assert decision.results[0].service.location_id == location_id


@pytest.mark.parametrize(
    ("query", "service_id"),
    [
        ("我想学书法", "calligraphy_class"),
        ("能免费量血压吗", "blood_pressure_check"),
        ("我要去助餐点订饭", "meal_service"),
        ("想登记水电报修", "repair_service"),
        ("请问怎么借书", "library_borrowing"),
    ],
)
def test_common_wording_variants_are_consistent(
    demo_knowledge_path: Path, query: str, service_id: str
):
    decision = make_retriever(demo_knowledge_path).decide(query)

    assert decision.status == "matched"
    assert decision.results[0].service.id == service_id


@pytest.mark.parametrize("query", ["我想办理护照", "？！。，", "   "])
def test_unrelated_or_empty_question_is_not_confident(
    demo_knowledge_path: Path, query: str
):
    retriever = make_retriever(demo_knowledge_path)

    decision = retriever.decide(query)

    assert decision.status == "not_found"
    assert decision.results == []
    assert retriever.is_confident(retriever.search(query)) is False


def test_mixed_known_and_unknown_intent_requests_clarification(
    demo_knowledge_path: Path,
):
    decision = make_retriever(demo_knowledge_path).decide(
        "我想报书法班，也想办理护照"
    )

    assert decision.status == "ambiguous"
    assert decision.results[0].service.id == "calligraphy_class"
    assert decision.question
    assert "书法班" in decision.question
    assert "其他事情" in decision.question


def test_search_returns_no_more_than_requested_limit(demo_knowledge_path: Path):
    results = make_retriever(demo_knowledge_path).search("老人社区服务", limit=2)

    assert len(results) <= 2
