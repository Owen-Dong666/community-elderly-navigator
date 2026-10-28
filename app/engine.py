import asyncio
from dataclasses import dataclass, field
import json
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from .config import ROOT
from .model import Decision, ModelFailure, ModelFormatError


FACT_LABELS = {"location": "地点", "schedule": "时间", "materials": "准备事项", "details": "服务说明"}


def load_knowledge(path: Path = ROOT / "data" / "demo_community.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = set()
    for service in data["services"]:
        if service["id"] in ids or not 1 <= service["led"] <= 6 or not service["steps"]:
            raise ValueError("Invalid demonstration knowledge")
        ids.add(service["id"])
        if service["facts"]["location"] != service["location"]:
            raise ValueError("Service location differs from its facts")
    return data


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid4().hex)
    history: list = field(default_factory=list)
    mode: str = "idle"
    service_id: str | None = None
    step_index: int = 0
    display_text: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Navigator:
    def __init__(self, model, knowledge=None):
        self.model = model
        self.knowledge = knowledge or load_knowledge()
        self.services = {service["id"]: service for service in self.knowledge["services"]}
        self.sessions = {}

    def create_session(self):
        session = Session()
        self.sessions[session.id] = session
        return session

    def model_knowledge(self):
        data = {"notice": self.knowledge["notice"], "services": []}
        for item in self.services.values():
            data["services"].append({
                "id": item["id"], "name": item["name"],
                "facts": [{"id": f"{item['id']}.{key}", "label": FACT_LABELS.get(key, key), "value": value} for key, value in item["facts"].items()],
                "steps": item["steps"],
            })
        return data

    def device(self, session):
        service = self.services.get(session.service_id)
        if service and session.mode == "showing":
            step = service["steps"][session.step_index]
            screen = {
                "mode": "服务指引", "service": service["name"],
                "step": f"第 {session.step_index + 1} / {len(service['steps'])} 步",
                "title": "服务信息" if session.display_text else step["title"],
                "body": session.display_text or step["body"],
                "helper": "演示数据 · 按 B 返回待机" if session.step_index == len(service["steps"]) - 1 else "演示数据 · A 上一步 / B 下一步",
            }
            return {"mode": "showing", "service_id": service["id"], "location": service["location"], "led": service["led"], "step_index": session.step_index, "step_count": len(service["steps"]), "screen": screen}
        if session.mode == "clarify":
            screen = {"mode": "需确认", "service": "等待确认", "step": "请继续对话", "title": "需要确认", "body": session.display_text, "helper": "演示资料 · 请继续输入或咨询工作人员"}
        else:
            screen = {"mode": "待机", "service": "等待咨询", "step": "准备就绪", "title": "您好，请开始", "body": "输入问题，或选择上方的示例语句。", "helper": "演示数据 · A 上一步 / B 下一步"}
        return {"mode": session.mode, "service_id": None, "location": "", "led": 0, "step_index": 0, "step_count": 0, "screen": screen}

    def _clear(self, session, mode="idle", display_text=""):
        session.mode, session.service_id, session.step_index, session.display_text = mode, None, 0, display_text

    def _button(self, session, event):
        if session.mode != "showing":
            if event in ("BUTTON_A", "BUTTON_B", "END") and session.mode == "clarify":
                self._clear(session)
            return
        if event == "BUTTON_A":
            session.step_index = max(0, session.step_index - 1)
            session.display_text = ""
        elif event == "BUTTON_B":
            if session.step_index >= len(self.services[session.service_id]["steps"]) - 1:
                self._clear(session)
            else:
                session.step_index += 1
                session.display_text = ""
        elif event == "END":
            self._clear(session)

    def _validate(self, raw, session):
        try:
            result = Decision.model_validate(raw)
        except ValidationError as exc:
            raise ModelFormatError("模型输出格式无效。") from exc
        if result.action in ("start", "answer"):
            service_id = result.service_id or (session.service_id if result.action == "answer" else None)
            service = self.services.get(service_id)
            if not service:
                raise ModelFormatError("模型选择了未知服务。")
            for fact in result.fact_ids:
                prefix, separator, key = fact.partition(".")
                if not separator or prefix != service_id or key not in service["facts"]:
                    raise ModelFormatError("模型引用的演示资料无效。")
            result.service_id = service_id
        elif result.fact_ids:
            raise ModelFormatError("模型引用的演示资料无效。")
        return result

    async def message(self, session, text):
        messages = [*session.history[-20:], {"role": "user", "content": text}]
        state = {"service_id": session.service_id, "step_index": session.step_index, "mode": session.mode}
        for attempt in range(2):
            try:
                current = messages if attempt == 0 else [*messages, {"role": "user", "content": "上次输出不符合格式或引用无效，请只使用资料中的服务和事实 id，重新输出 JSON。"}]
                raw = await self.model.decide(current, self.model_knowledge(), state)
                decision = self._validate(raw, session)
                break
            except ModelFormatError:
                if attempt:
                    raise ModelFailure("模型输出不符合演示资料，请重新提问。") from None
        sources = []
        if decision.action in ("start", "answer"):
            service = self.services[decision.service_id]
            for fact_id in dict.fromkeys(decision.fact_ids):
                key = fact_id.split(".", 1)[1]
                sources.append({"id": fact_id, "label": FACT_LABELS.get(key, key), "value": service["facts"][key]})
            facts_text = "；".join(f"{item['label']}：{item['value']}" for item in sources)
            if decision.action == "answer" and not sources:
                reply = "演示资料没有这项信息，请向工作人员确认。"
                self._clear(session, "clarify", reply)
            else:
                if decision.action == "start" or session.service_id != service["id"] or session.mode != "showing":
                    session.mode, session.service_id, session.step_index, session.display_text = "showing", service["id"], 0, ""
                if decision.action == "answer":
                    reply = facts_text
                    session.display_text = reply
                else:
                    reply = f"好的，开始{service['name']}指引。" + (" " + facts_text if facts_text else "")
        elif decision.action == "clarify":
            reply = decision.reply.strip() or "您想先咨询哪项社区服务？"
            self._clear(session, "clarify", reply)
        elif decision.action == "unknown":
            reply = "演示资料中没有可确认的信息，请向工作人员咨询。"
            self._clear(session, "clarify", reply)
        elif decision.action == "chat":
            reply = decision.reply.strip() or "您好，您可以询问社区服务或活动。"
        else:
            mapped = {"next": "BUTTON_B", "previous": "BUTTON_A", "repeat": "REPEAT", "end": "END"}[decision.action]
            self._button(session, mapped)
            device = self.device(session)
            reply = device["screen"]["body"] if device["mode"] == "showing" else "当前没有进行中的导航。"
        session.history = [*messages, {"role": "assistant", "content": reply}][-20:]
        return reply, sources

    @staticmethod
    def _line(value):
        return str(value).replace("|", "／").replace("\r", " ").replace("\n", " ")

    def response(self, session, reply="", sources=None, incoming=None, error="", speech=None):
        device = self.device(session)
        screen = device["screen"]
        if speech is None:
            speech = screen["body"] if device["mode"] == "showing" and not error else ""
        speech = self._line(speech)
        protocol = []
        if incoming:
            protocol.append({"direction": "TX", "line": incoming})
        protocol.append({"direction": "RX", "line": "STATE_BEGIN"})
        if error:
            protocol.append({"direction": "RX", "line": "ERROR|" + self._line(error)})
        elif device["mode"] == "showing":
            for key, value in [("SERVICE", screen["service"]), ("STEP", f"{device['step_index'] + 1}/{device['step_count']}"), ("TITLE", screen["title"]), ("BODY", screen["body"]), ("HELPER", screen["helper"])]:
                protocol.append({"direction": "RX", "line": key + "|" + self._line(value)})
        elif device["mode"] == "clarify":
            protocol.append({"direction": "RX", "line": "ERROR|" + self._line(screen["body"])})
        else:
            protocol.append({"direction": "RX", "line": "READY|等待咨询"})
        if speech:
            protocol.append({"direction": "RX", "line": "SPEAK|" + speech})
        protocol.extend([{"direction": "RX", "line": f"LED|{device['led']}"}, {"direction": "RX", "line": "STATE_END"}])
        return {"session_id": session.id, "reply": reply, "sources": sources or [], "device": device, "protocol": protocol, "speech": speech, "error": error}
