from pathlib import Path

import pytest


@pytest.fixture
def demo_knowledge_path() -> Path:
    return Path(__file__).parents[1] / "data" / "demo_community.json"

