from __future__ import annotations

import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "mindplus" / "社区老人办事导航员-K10.mp"


def test_mindplus_project_is_native_archive_with_contract_markers() -> None:
    assert PROJECT.is_file(), "缺少 Mind+ V2 原生 .mp 工程"

    with zipfile.ZipFile(PROJECT) as archive:
        assert "project.json" in archive.namelist()
        project = json.loads(archive.read("project.json").decode("utf-8"))

    serialized = json.dumps(project, ensure_ascii=False)
    required_markers = (
        "HELLO|1",
        "QUERY|",
        "BUTTON_A",
        "BUTTON_B",
        "STATE_BEGIN",
        "STATE_END",
        "PING",
        "shu fa ban",
        "tai ji quan",
        "liang xue ya",
        "she bao",
        "gao ling jin tie",
        "lao ren zhu can",
        "shui dian bao xiu",
        "ban hu zhao",
        "P0",
        "P1",
        "P2",
        "P8",
        "P9",
        "P12",
    )

    for marker in required_markers:
        assert marker in serialized
