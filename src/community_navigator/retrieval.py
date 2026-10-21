"""Deterministic retrieval over the small local service catalog."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from .knowledge import KnowledgeBase
from .models import ServiceRecord


MIN_CONFIDENCE_SCORE = 25.0
AMBIGUOUS_SCORE_GAP = 5.0
MAX_CANDIDATES = 3

_FILLER_PHRASES = (
    "请问",
    "麻烦",
    "我想",
    "我要",
    "能不能",
    "可以",
    "怎么",
    "如何",
    "哪里",
    "在哪儿",
    "在哪里",
    "办理",
    "参加",
    "找谁",
    "家里",
)


def normalize_query(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return "".join(
        character
        for character in normalized
        if character.isalnum() or "\u4e00" <= character <= "\u9fff"
    )


def _content_query(text: str) -> str:
    content = normalize_query(text)
    for phrase in _FILLER_PHRASES:
        content = content.replace(phrase, "")
    return content


@dataclass(frozen=True, slots=True)
class SearchResult:
    service: ServiceRecord
    score: float
    matched_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchDecision:
    status: Literal["matched", "ambiguous", "not_found"]
    results: list[SearchResult]
    question: str | None = None


class ServiceRetriever:
    def __init__(self, knowledge: KnowledgeBase) -> None:
        self.knowledge = knowledge

    def search(self, query: str, limit: int = MAX_CANDIDATES) -> list[SearchResult]:
        normalized = normalize_query(query)
        content = _content_query(query)
        if not normalized or limit <= 0:
            return []

        scored: list[SearchResult] = []
        for service in self.knowledge.data.services:
            result = self._score(service, normalized, content)
            if result.score > 0:
                scored.append(result)

        scored.sort(key=lambda result: (-result.score, result.service.id))
        return scored[: min(limit, MAX_CANDIDATES)]

    def is_confident(self, results: list[SearchResult]) -> bool:
        return bool(results and results[0].score >= MIN_CONFIDENCE_SCORE)

    def decide(self, query: str) -> SearchDecision:
        clauses = self._split_clauses(query)
        if not clauses:
            return SearchDecision(status="not_found", results=[])

        if len(clauses) > 1:
            clause_results = [self.search(clause, limit=1) for clause in clauses]
            confident = [
                results[0]
                for results in clause_results
                if self.is_confident(results)
            ]
            if not confident:
                return SearchDecision(status="not_found", results=[])

            unique = self._unique_results(confident)
            all_matched = len(confident) == len(clauses)
            if not all_matched or len(unique) > 1:
                service_name = unique[0].service.name
                return SearchDecision(
                    status="ambiguous",
                    results=unique[:MAX_CANDIDATES],
                    question=f"您想先了解{service_name}，还是咨询其他事情？",
                )

            return SearchDecision(status="matched", results=unique)

        results = self.search(clauses[0])
        if not self.is_confident(results):
            return SearchDecision(status="not_found", results=[])

        if (
            len(results) > 1
            and results[1].score >= MIN_CONFIDENCE_SCORE
            and results[0].score - results[1].score <= AMBIGUOUS_SCORE_GAP
        ):
            return SearchDecision(
                status="ambiguous",
                results=results,
                question=(
                    f"您想咨询{results[0].service.name}，"
                    f"还是{results[1].service.name}？"
                ),
            )

        return SearchDecision(status="matched", results=results)

    def _score(
        self, service: ServiceRecord, normalized: str, content: str
    ) -> SearchResult:
        score = 0.0
        matched: set[str] = set()
        name = normalize_query(service.name)

        if name and name in normalized:
            score += 100
            matched.add(service.name)
        elif len(content) >= 2 and (content in name or name in content):
            score += 60
            matched.add(service.name)

        for alias in service.aliases:
            alias_key = normalize_query(alias)
            if not alias_key:
                continue
            if alias_key in normalized:
                score += 90
                matched.add(alias)
            elif len(content) >= 2 and (content in alias_key or alias_key in content):
                score += 55
                matched.add(alias)

        for keyword in service.keywords:
            keyword_key = normalize_query(keyword)
            if keyword_key and keyword_key in normalized:
                score += 25
                matched.add(keyword)

        category = normalize_query(service.category)
        if category and category in normalized:
            score += 10
            matched.add(service.category)

        if content:
            similarity = SequenceMatcher(None, content, name).ratio()
            if similarity >= 0.45:
                score += min(20.0, similarity * 20.0)

        return SearchResult(
            service=service,
            score=round(score, 3),
            matched_terms=tuple(sorted(matched)),
        )

    @staticmethod
    def _split_clauses(query: str) -> list[str]:
        expanded = re.sub(r"(还要|也想|另外|以及)", "|", query)
        expanded = re.sub(r"[，,。；;、]|和", "|", expanded)
        return [part.strip() for part in expanded.split("|") if normalize_query(part)]

    @staticmethod
    def _unique_results(results: list[SearchResult]) -> list[SearchResult]:
        unique: dict[str, SearchResult] = {}
        for result in results:
            current = unique.get(result.service.id)
            if current is None or result.score > current.score:
                unique[result.service.id] = result
        return sorted(unique.values(), key=lambda result: -result.score)
