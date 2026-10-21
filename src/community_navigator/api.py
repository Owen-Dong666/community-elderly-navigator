"""FastAPI assembly and stable REST routes for the navigator."""

from __future__ import annotations

import unicodedata
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import Settings
from .knowledge import KnowledgeBase
from .models import DeviceEvent, SessionState
from .planning import PlanningService
from .providers import ModelProvider, build_provider
from .retrieval import ServiceRetriever
from .sessions import SessionError, SessionManager


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("查询内容不能为空")
        if any(unicodedata.category(character).startswith("C") for character in stripped):
            raise ValueError("查询内容不能包含控制字符")
        return stripped


class EventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str


def create_app(
    settings: Settings | None = None,
    provider: ModelProvider | None = None,
) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    knowledge = KnowledgeBase.load(runtime_settings.knowledge_path)
    runtime_provider = provider or build_provider(runtime_settings)
    retriever = ServiceRetriever(knowledge)
    planner = PlanningService(knowledge, runtime_provider)
    sessions = SessionManager(knowledge)

    app = FastAPI(
        title="社区老人的办事导航员",
        version="0.1.0",
        description="电脑端智能体与 K10 模拟器共用服务",
    )
    app.state.settings = runtime_settings
    app.state.knowledge = knowledge
    app.state.provider = runtime_provider
    app.state.retriever = retriever
    app.state.planner = planner
    app.state.sessions = sessions

    web_dir = Path(__file__).with_name("web")
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/", include_in_schema=False)
    def simulator() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    @app.get("/api/v1/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "provider": runtime_settings.model_provider,
            "is_demo": knowledge.data.is_demo,
        }

    @app.post("/api/v1/query", response_model=SessionState)
    def query(request: QueryRequest) -> SessionState:
        decision = retriever.decide(request.text)
        plan = planner.plan(request.text, decision)
        return sessions.create(plan)

    @app.get("/api/v1/sessions/{session_id}", response_model=SessionState)
    def get_session(session_id: str) -> SessionState:
        state = sessions.get(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        return state

    @app.post(
        "/api/v1/sessions/{session_id}/events",
        response_model=SessionState,
    )
    def apply_event(session_id: str, request: EventRequest) -> SessionState:
        try:
            event = DeviceEvent.model_validate(request.model_dump())
            return sessions.apply_event(session_id, event)
        except SessionError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="按键事件无效") from exc

    @app.get("/api/v1/knowledge/services")
    def services() -> dict[str, object]:
        if not runtime_settings.expose_knowledge_api:
            raise HTTPException(status_code=404, detail="接口未启用")
        return knowledge.data.model_dump(mode="json")

    return app

