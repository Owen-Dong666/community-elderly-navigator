import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.model import ModelFailure, ModelFormatError, ModelProvider


def test_ollama_uses_local_chat_schema_and_never_adds_cloud_credentials():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"message": {"content": json.dumps({"action": "unknown"})}})

    settings = Settings(provider="ollama", ollama_model="demo", cloud_key="secret")
    provider = ModelProvider(settings, transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.decide([{"role": "user", "content": "你好"}], {"services": []}, {}))
    assert result["action"] == "unknown"
    assert str(requests[0].url) == "http://127.0.0.1:11434/api/chat"
    body = json.loads(requests[0].content)
    assert body["stream"] is False and body["format"]["type"] == "object"
    assert "authorization" not in requests[0].headers
    assert b"secret" not in requests[0].content


def test_cloud_chat_completions_uses_configured_key_and_model():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"action":"chat","reply":"您好"}'}}]})

    settings = Settings(provider="openai_compatible", cloud_base_url="https://example.test/v1", cloud_model="demo", cloud_key="secret")
    provider = ModelProvider(settings, transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.decide([{"role": "user", "content": "你好"}], {"services": []}, {}))
    assert result["reply"] == "您好"
    assert str(requests[0].url) == "https://example.test/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer secret"
    assert json.loads(requests[0].content)["model"] == "demo"


@pytest.mark.parametrize("url", ["https://example.com", "http://192.168.1.4:11434", "http://127.0.0.1.example.com:11434"])
def test_ollama_rejects_non_loopback_addresses(url):
    provider = ModelProvider(Settings(provider="ollama", ollama_base_url=url, ollama_model="demo"))
    with pytest.raises(ModelFailure, match="本机"):
        asyncio.run(provider.decide([], {"services": []}, {}))


def test_bad_json_and_timeout_are_distinct_errors():
    def invalid(_request):
        return httpx.Response(200, json={"message": {"content": "not json"}})

    def timeout(request):
        raise httpx.ReadTimeout("upstream details", request=request)

    settings = Settings(provider="ollama", ollama_model="demo")
    with pytest.raises(ModelFormatError):
        asyncio.run(ModelProvider(settings, transport=httpx.MockTransport(invalid)).decide([], {}, {}))
    with pytest.raises(ModelFailure, match="超时"):
        asyncio.run(ModelProvider(settings, transport=httpx.MockTransport(timeout)).decide([], {}, {}))
