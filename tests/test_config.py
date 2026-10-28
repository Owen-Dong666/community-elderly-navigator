import asyncio

from app.config import Settings
from app.model import ModelFailure, ModelProvider
import pytest


def test_local_configuration_file_and_environment_override(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("MODEL_PROVIDER=ollama\nOLLAMA_MODEL=from-file\nCLOUD_API_KEY=private\n", encoding="utf-8")
    monkeypatch.setenv("OLLAMA_MODEL", "from-environment")
    config = Settings.load(path)
    assert config.ollama_model == "from-environment"
    assert config.provider == "ollama" and config.cloud_key == "private"


def test_cloud_credentials_are_not_sent_over_unencrypted_internet():
    provider = ModelProvider(Settings(provider="openai_compatible", cloud_base_url="http://example.test/v1", cloud_model="demo", cloud_key="private"))
    with pytest.raises(ModelFailure, match="HTTPS"):
        provider._configuration()


def test_malformed_cloud_address_shows_configuration_error():
    provider = ModelProvider(Settings(provider="openai_compatible", cloud_base_url="https://[bad", cloud_model="demo", cloud_key="private"))
    status = asyncio.run(provider.health())
    assert status["status"] == "unavailable"
    assert "地址" in status["detail"]
