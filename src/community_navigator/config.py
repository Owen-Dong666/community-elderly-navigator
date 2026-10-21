"""Environment-backed application settings."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    """Runtime settings shared by the API and model provider factory."""

    model_config = ConfigDict(extra="forbid")

    model_provider: str = "mock"
    model_base_url: str | None = None
    model_name: str | None = None
    model_api_key: str | None = Field(default=None, repr=False)
    model_timeout_seconds: float = Field(default=20.0, gt=0)
    knowledge_path: Path = Path("data/demo_community.json")
    expose_knowledge_api: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        expose_value = os.getenv("EXPOSE_KNOWLEDGE_API", "true").strip().lower()
        return cls(
            model_provider=os.getenv("MODEL_PROVIDER", "mock").strip().lower(),
            model_base_url=os.getenv("MODEL_BASE_URL") or None,
            model_name=os.getenv("MODEL_NAME") or None,
            model_api_key=os.getenv("MODEL_API_KEY") or None,
            model_timeout_seconds=float(os.getenv("MODEL_TIMEOUT_SECONDS", "20")),
            knowledge_path=Path(
                os.getenv("KNOWLEDGE_PATH", "data/demo_community.json")
            ),
            expose_knowledge_api=expose_value in {"1", "true", "yes", "on"},
        )

