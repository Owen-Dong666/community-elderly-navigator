import ipaddress
import json
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings


class ModelFailure(Exception):
    """A model was unavailable or rejected a request."""


class ModelFormatError(Exception):
    """A model returned data that cannot safely drive navigation."""


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["start", "answer", "clarify", "unknown", "chat", "next", "previous", "repeat", "end"]
    service_id: str | None = None
    fact_ids: list[str] = Field(default_factory=list, max_length=8)
    reply: str = Field(default="", max_length=200)


SYSTEM_PROMPT = """你是社区演示导航助手。只使用提供的虚构资料，不补充政策、资格、时间、地点或材料。
根据用户当前问题和上下文输出一个 JSON 对象：
action 为 start（开始某项服务导航）、answer（回答服务资料问题）、clarify（需询问用户）、
unknown（资料不足或服务不支持）、chat（简短问候并引导社区服务）、next、previous、repeat 或 end。
service_id 必须是资料中真实存在的服务 id；需要澄清、未知和控制动作时可为 null。
fact_ids 是相关服务的事实 id 列表；回答时间、地点、物品等必须选对应事实 id。
reply 仅用在澄清或问候，尽量简短，不要自行声称任何服务事实或政策。
用户说“刚才那个”等指向之前的话题；普通追问不要重启当前步骤；多个服务不明确时澄清。
只输出 JSON，字段为 action、service_id、fact_ids、reply。"""


def local_url(base: str) -> str:
    try:
        parsed = urlsplit(base)
        host = parsed.hostname
        if parsed.scheme != "http" or not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError
        if host.lower() == "localhost":
            host = "127.0.0.1"
        elif not ipaddress.ip_address(host).is_loopback:
            raise ValueError
        address = f"[{host}]" if ":" in host else host
        if parsed.port:
            address += f":{parsed.port}"
        return urlunsplit(("http", address, parsed.path.rstrip("/"), "", ""))
    except (ValueError, TypeError):
        raise ModelFailure("本地模式只能连接本机 Ollama 地址。") from None


class ModelProvider:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.transport = transport

    def _configuration(self):
        settings = self.settings
        if settings.provider == "ollama":
            base = local_url(settings.ollama_base_url)
            if not settings.ollama_model:
                raise ModelFailure("请在 .env 中设置已经安装的 OLLAMA_MODEL。")
            return base, settings.ollama_model
        if settings.provider == "openai_compatible":
            try:
                parsed = urlsplit(settings.cloud_base_url)
                invalid = parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                parsed.port  # Validate a supplied port before making any request.
            except ValueError:
                invalid = True
            if invalid:
                raise ModelFailure("请在 .env 中设置有效的云端 API 地址。")
            if parsed.scheme == "http":
                try:
                    local_url(settings.cloud_base_url)
                except ModelFailure:
                    raise ModelFailure("云端 API 地址必须使用 HTTPS。") from None
            if not settings.cloud_model or not settings.cloud_key:
                raise ModelFailure("请在 .env 中设置云端模型名称和 API 密钥。")
            return settings.cloud_base_url.rstrip("/"), settings.cloud_model
        raise ModelFailure("MODEL_PROVIDER 须为 ollama 或 openai_compatible。")

    async def health(self):
        try:
            base, model = self._configuration()
            if self.settings.provider != "ollama":
                return {"status": "configured", "detail": "云端 API 已配置，发送问题时连接。"}
            async with httpx.AsyncClient(timeout=2, trust_env=False, transport=self.transport, follow_redirects=False) as client:
                response = await client.get(base + "/api/tags")
                response.raise_for_status()
                available = [item.get("name") for item in response.json().get("models", [])]
            if model not in available:
                return {"status": "unavailable", "detail": "Ollama 已连接，但未找到配置的模型。"}
            return {"status": "ready", "detail": "本地模型已就绪。"}
        except ModelFailure as exc:
            return {"status": "unavailable", "detail": str(exc)}
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return {"status": "unavailable", "detail": "无法连接本机 Ollama，请检查服务。"}

    async def decide(self, messages, knowledge, navigation):
        base, model = self._configuration()
        context = json.dumps({"knowledge": knowledge, "navigation": navigation}, ensure_ascii=False)
        prompt_messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n演示资料与当前状态：" + context}, *messages]
        headers = {}
        if self.settings.provider == "ollama":
            url = base + "/api/chat"
            body = {"model": model, "messages": prompt_messages, "stream": False, "format": Decision.model_json_schema(), "options": {"temperature": 0.1}}
        else:
            url = base + "/chat/completions"
            headers["Authorization"] = "Bearer " + self.settings.cloud_key
            body = {"model": model, "messages": prompt_messages, "stream": False, "temperature": 0.1, "response_format": {"type": "json_object"}}
        try:
            async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, trust_env=False, transport=self.transport, follow_redirects=False) as client:
                response = await client.post(url, json=body, headers=headers)
                response.raise_for_status()
                payload = response.json()
            content = payload["message"]["content"] if self.settings.provider == "ollama" else payload["choices"][0]["message"]["content"]
            return json.loads(content)
        except httpx.TimeoutException:
            raise ModelFailure("模型响应超时，请检查服务后重试。") from None
        except httpx.HTTPStatusError as exc:
            raise ModelFailure(f"模型服务返回错误（HTTP {exc.response.status_code}）。") from None
        except httpx.HTTPError:
            raise ModelFailure("模型连接失败，请检查服务和配置。") from None
        except (KeyError, IndexError, ValueError, TypeError):
            raise ModelFormatError("模型输出格式无效。") from None
