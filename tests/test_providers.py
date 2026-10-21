"""Contract tests for switchable model providers."""

from __future__ import annotations

import json

import httpx
import pytest

from community_navigator.config import Settings
from community_navigator.models import PlanResult
from community_navigator.providers import (
    MockProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    ProviderError,
    build_provider,
)


SCHEMA = PlanResult.model_json_schema()


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_mock_provider_returns_deterministic_json_text() -> None:
    provider = MockProvider()

    first = provider.generate_plan("同一个提示", SCHEMA)
    second = provider.generate_plan("同一个提示", SCHEMA)

    assert first == second
    parsed = PlanResult.model_validate_json(first)
    assert parsed.status == "ready"
    assert parsed.steps


def test_openai_compatible_provider_uses_chat_completions_and_bearer_token() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"status":"ready"}'}}]},
        )

    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test",
        model="demo-model",
        api_key="secret-token",
        client=_client(handler),
    )

    content = provider.generate_plan("只使用给定资料", SCHEMA)

    assert content == '{"status":"ready"}'
    assert seen["path"] == "/v1/chat/completions"
    assert seen["authorization"] == "Bearer secret-token"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "demo-model"
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][-1]["content"] == "只使用给定资料"


def test_ollama_provider_uses_native_structured_chat_endpoint() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "{}"}})

    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:0.6b",
        client=_client(handler),
    )

    assert provider.generate_plan("规划步骤", SCHEMA) == "{}"
    assert seen["path"] == "/api/chat"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "qwen3:0.6b"
    assert body["stream"] is False
    assert body["format"] == SCHEMA
    assert body["messages"][-1]["content"] == "规划步骤"


@pytest.mark.parametrize(
    "response_json",
    [
        {"choices": []},
        {"choices": [{"message": {"content": ""}}]},
        {"unexpected": True},
    ],
)
def test_openai_provider_rejects_missing_content(response_json: dict[str, object]) -> None:
    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test",
        model="demo-model",
        client=_client(lambda _request: httpx.Response(200, json=response_json)),
    )

    with pytest.raises(ProviderError, match="内容"):
        provider.generate_plan("提示", SCHEMA)


def test_provider_wraps_timeout_without_leaking_api_key() -> None:
    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret-token timeout")

    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test",
        model="demo-model",
        api_key="secret-token",
        client=_client(timeout),
    )

    with pytest.raises(ProviderError) as captured:
        provider.generate_plan("提示", SCHEMA)

    assert "secret-token" not in str(captured.value)


def test_provider_wraps_http_failure() -> None:
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:0.6b",
        client=_client(lambda _request: httpx.Response(500, text="boom")),
    )

    with pytest.raises(ProviderError, match="请求失败"):
        provider.generate_plan("提示", SCHEMA)


def test_build_provider_selects_each_implementation() -> None:
    assert isinstance(build_provider(Settings(model_provider="mock")), MockProvider)
    assert isinstance(
        build_provider(
            Settings(
                model_provider="openai_compatible",
                model_base_url="https://models.example.test",
                model_name="demo-model",
            )
        ),
        OpenAICompatibleProvider,
    )
    ollama = build_provider(
        Settings(model_provider="ollama", model_name="qwen3:0.6b")
    )
    assert isinstance(ollama, OllamaProvider)
    assert ollama.base_url == "http://127.0.0.1:11434"


def test_build_provider_rejects_unknown_name_without_exposing_secrets() -> None:
    settings = Settings(model_provider="mystery", model_api_key="top-secret")

    with pytest.raises(ProviderError) as captured:
        build_provider(settings)

    assert "mystery" in str(captured.value)
    assert "top-secret" not in str(captured.value)
