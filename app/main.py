from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from .config import ROOT, Settings
from .engine import Navigator
from .model import ModelFailure, ModelProvider


class MessageInput(BaseModel):
    text: str = Field(min_length=1, max_length=200)

    @field_validator("text")
    @classmethod
    def nonempty(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("请输入想咨询的问题。")
        return value


class EventInput(BaseModel):
    event: Literal["BUTTON_A", "BUTTON_B", "REPEAT", "END"]


class SessionInput(BaseModel):
    previous_session_id: str | None = None


def create_app(settings=None, model=None):
    settings = settings or Settings.load()
    navigator = Navigator(model or ModelProvider(settings))
    app = FastAPI(title="K10 Community Navigator", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.navigator = navigator

    def session_for(session_id):
        session = navigator.sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="对话已失效，请开始新对话。")
        return session

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "k10-simulator.html", media_type="text/html; charset=utf-8")

    @app.get("/api/v1/health")
    async def health():
        status = await navigator.model.health()
        return {"provider": settings.provider, "model": settings.ollama_model if settings.provider == "ollama" else settings.cloud_model, **status}

    @app.post("/api/v1/sessions")
    async def create_session(body: SessionInput | None = None):
        if body and body.previous_session_id:
            navigator.sessions.pop(body.previous_session_id, None)
        return navigator.response(navigator.create_session(), incoming="HELLO|1")

    @app.get("/api/v1/sessions/{session_id}")
    async def get_session(session_id: str):
        return navigator.response(session_for(session_id))

    @app.post("/api/v1/sessions/{session_id}/messages")
    async def send_message(session_id: str, body: MessageInput):
        session = session_for(session_id)
        if session.lock.locked():
            raise HTTPException(status_code=409, detail="上一条消息仍在处理中。")
        async with session.lock:
            incoming = "QUERY|" + navigator._line(body.text)
            previous_service = session.service_id
            try:
                reply, sources = await navigator.message(session, body.text)
                device = navigator.device(session)
                speech = reply
                if device["mode"] == "showing" and previous_service != device["service_id"] and device["screen"]["body"] != reply:
                    speech += " " + device["screen"]["body"]
                return navigator.response(session, reply, sources, incoming, speech=speech)
            except ModelFailure as exc:
                return JSONResponse(status_code=502, content=navigator.response(session, incoming=incoming, error=str(exc)))

    @app.post("/api/v1/sessions/{session_id}/events")
    async def send_event(session_id: str, body: EventInput):
        session = session_for(session_id)
        if session.lock.locked():
            raise HTTPException(status_code=409, detail="上一条消息仍在处理中。")
        async with session.lock:
            navigator._button(session, body.event)
            return navigator.response(session, incoming=body.event)

    return app


app = create_app()
