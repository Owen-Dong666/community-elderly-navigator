"""Switchable model-provider adapters with one small synchronous contract."""

from __future__ import annotations

from typing import Protocol

import httpx

from .config import Settings
from .models import PlanResult, PlanStep


class ProviderError(RuntimeError):
    """A safe, user-displayable provider failure."""


class ModelProvider(Protocol):
    def generate_plan(self, prompt: str, schema: dict[str, object]) -> str:
        """Return a JSON document as text."""


class MockProvider:
    """Deterministic provider used for classroom demos and automated tests."""

    def generate_plan(self, prompt: str, schema: dict[str, object]) -> str:
        del prompt, schema
        return PlanResult(
            status="ready",
            summary="已根据社区资料整理好办理步骤。",
            steps=[
                PlanStep(
                    index=1,
                    title="查看办理信息",
                    instruction="请按屏幕提示准备材料并前往对应地点。",
                    speech="请按屏幕提示准备材料并前往对应地点。",
                )
            ],
        ).model_dump_json()


class _HttpProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url.strip():
            raise ProviderError("模型服务地址不能为空")
        if not model.strip():
            raise ProviderError("模型名称不能为空")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.Client()

    def _post(self, path: str, *, payload: dict[str, object], headers=None) -> dict:
        try:
            response = self._client.post(
                f"{self.base_url}{path}",
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            envelope = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderError("模型服务响应超时") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("模型服务请求失败") from exc
        if not isinstance(envelope, dict):
            raise ProviderError("模型服务没有返回有效内容")
        return envelope


class OpenAICompatibleProvider(_HttpProvider):
    """Adapter for cloud or local OpenAI-compatible chat-completion APIs."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            client=client,
        )
        self._api_key = api_key

    def generate_plan(self, prompt: str, schema: dict[str, object]) -> str:
        del schema
        headers = None
        if self._api_key:
            headers = {"Authorization": f"Bearer {self._api_key}"}
        envelope = self._post(
            "/v1/chat/completions",
            headers=headers,
            payload={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "只根据提供的社区资料输出一个 JSON 对象。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
        )
        try:
            content = envelope["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("模型服务没有返回有效内容") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("模型服务没有返回有效内容")
        return content


class OllamaProvider(_HttpProvider):
    """Adapter for Ollama's native structured chat API."""

    def generate_plan(self, prompt: str, schema: dict[str, object]) -> str:
        envelope = self._post(
            "/api/chat",
            payload={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "只根据提供的社区资料输出一个 JSON 对象。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "format": schema,
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        try:
            content = envelope["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ProviderError("模型服务没有返回有效内容") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("模型服务没有返回有效内容")
        return content


def build_provider(settings: Settings) -> ModelProvider:
    """Build the configured provider without exposing secret settings."""

    provider_name = settings.model_provider.strip().lower()
    if provider_name == "mock":
        return MockProvider()
    if provider_name == "openai_compatible":
        if not settings.model_base_url or not settings.model_name:
            raise ProviderError("云端模型需要配置服务地址和模型名称")
        return OpenAICompatibleProvider(
            base_url=settings.model_base_url,
            model=settings.model_name,
            api_key=settings.model_api_key,
            timeout_seconds=settings.model_timeout_seconds,
        )
    if provider_name == "ollama":
        if not settings.model_name:
            raise ProviderError("Ollama 需要配置模型名称")
        return OllamaProvider(
            base_url=settings.model_base_url or "http://127.0.0.1:11434",
            model=settings.model_name,
            timeout_seconds=settings.model_timeout_seconds,
        )
    raise ProviderError(f"不支持的模型提供者：{provider_name}")
