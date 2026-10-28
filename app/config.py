from dataclasses import dataclass
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    provider: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    cloud_base_url: str = ""
    cloud_model: str = ""
    cloud_key: str = ""
    timeout_seconds: float = 120.0

    @classmethod
    def load(cls, path: Path = ROOT / ".env"):
        values = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip().strip('"').strip("'")

        def get(key, default=""):
            return os.environ.get(key, values.get(key, default)).strip()

        try:
            timeout = float(get("MODEL_TIMEOUT_SECONDS", "120"))
            if not 1 <= timeout <= 600:
                raise ValueError
        except ValueError:
            timeout = 120.0
        return cls(
            provider=get("MODEL_PROVIDER", "ollama").lower(),
            ollama_base_url=get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            ollama_model=get("OLLAMA_MODEL"),
            cloud_base_url=get("CLOUD_BASE_URL"),
            cloud_model=get("CLOUD_MODEL"),
            cloud_key=get("CLOUD_API_KEY"),
            timeout_seconds=timeout,
        )
