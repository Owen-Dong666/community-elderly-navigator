from __future__ import annotations

import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "mindplus" / "社区老人办事导航员-K10.mp"


def load_stage_blocks() -> dict[str, dict[str, object]]:
    with zipfile.ZipFile(PROJECT) as archive:
        project = json.loads(archive.read("project.json").decode("utf-8"))

    stage = next(target for target in project["targets"] if target["isStage"])
    return stage["blocks"]


def block_tree_ids(
    blocks: dict[str, dict[str, object]], root_id: str | None
) -> set[str]:
    if not root_id:
        return set()

    pending = [root_id]
    found: set[str] = set()
    while pending:
        block_id = pending.pop()
        if block_id in found or block_id not in blocks:
            continue
        found.add(block_id)
        block = blocks[block_id]
        next_id = block.get("next")
        if isinstance(next_id, str):
            pending.append(next_id)
        for raw_input in block.get("inputs", {}).values():
            if not isinstance(raw_input, list):
                continue
            for item in raw_input[1:]:
                if isinstance(item, str) and item in blocks:
                    pending.append(item)
    return found


def subtree_serialized(
    blocks: dict[str, dict[str, object]], root_id: str | None
) -> str:
    ids = block_tree_ids(blocks, root_id)
    return json.dumps([blocks[block_id] for block_id in ids], ensure_ascii=False)


def substack_root(block: dict[str, object]) -> str | None:
    raw = block.get("inputs", {}).get("SUBSTACK")
    if isinstance(raw, list) and len(raw) >= 2 and isinstance(raw[1], str):
        return raw[1]
    return None


def condition_root(block: dict[str, object]) -> str | None:
    raw = block.get("inputs", {}).get("CONDITION")
    if isinstance(raw, list) and len(raw) >= 2 and isinstance(raw[1], str):
        return raw[1]
    return None


def conditionals_containing(
    blocks: dict[str, dict[str, object]], marker: str
) -> list[dict[str, object]]:
    return [
        block
        for block in blocks.values()
        if block["opcode"] == "control_if"
        and marker in subtree_serialized(blocks, condition_root(block))
    ]


def chain_ids(blocks: dict[str, dict[str, object]], first_id: str | None) -> list[str]:
    result: list[str] = []
    current = first_id
    while isinstance(current, str):
        result.append(current)
        current = blocks[current].get("next")
    return result


def procedure_body_serialized(
    blocks: dict[str, dict[str, object]], proccode: str
) -> str:
    prototype = next(
        block
        for block in blocks.values()
        if block["opcode"] == "procedures_prototype"
        and block.get("mutation", {}).get("proccode") == proccode
    )
    definition_id = prototype["parent"]
    return subtree_serialized(blocks, blocks[definition_id].get("next"))


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


def test_all_mindplus_blocks_are_reachable_and_references_resolve() -> None:
    blocks = load_stage_blocks()
    referenced_ids: set[str] = set()
    for block in blocks.values():
        next_id = block.get("next")
        if isinstance(next_id, str):
            referenced_ids.add(next_id)
        for raw_input in block.get("inputs", {}).values():
            if not isinstance(raw_input, list):
                continue
            referenced_ids.update(
                item for item in raw_input[1:] if isinstance(item, str)
            )

    assert referenced_ids <= blocks.keys()

    for block_id, block in blocks.items():
        next_id = block.get("next")
        if isinstance(next_id, str):
            assert blocks[next_id]["parent"] == block_id
        for raw_input in block.get("inputs", {}).values():
            if not isinstance(raw_input, list):
                continue
            for item in raw_input[1:]:
                if isinstance(item, str):
                    assert blocks[item]["parent"] == block_id

    top_level_ids = [
        block_id for block_id, block in blocks.items() if block.get("topLevel")
    ]
    assert len(top_level_ids) == 9
    reachable: set[str] = set()
    for block_id in top_level_ids:
        reachable.update(block_tree_ids(blocks, block_id))
    assert reachable == blocks.keys()


def test_native_project_contains_six_named_custom_blocks() -> None:
    blocks = load_stage_blocks()
    procedure_names = {
        block.get("mutation", {}).get("proccode")
        for block in blocks.values()
        if block["opcode"] == "procedures_prototype"
    }
    assert procedure_names == {
        "全部LED关闭",
        "点亮地图地点 %s",
        "显示初始页",
        "发送查询 %s",
        "处理电脑指令 %s",
        "应用完整状态",
    }


def test_button_event_stacks_only_set_flags() -> None:
    blocks = load_stage_blocks()
    hats = [
        block_id
        for block_id, block in blocks.items()
        if block["opcode"].endswith("_esp32s3bit_whenButtonPressed")
    ]
    assert len(hats) == 2

    for hat_id in hats:
        hat = blocks[hat_id]
        button = hat["fields"]["BTNNUMBER"][0]
        expected_variable = f"button{button}Flag"
        body_ids = chain_ids(blocks, hat.get("next"))
        assert len(body_ids) == 1
        assignment = blocks[body_ids[0]]
        assert assignment["opcode"] == "data_setvariableto"
        assert assignment["fields"]["VARIABLE"][0] == expected_variable
        assert "\"1\"" in json.dumps(assignment, ensure_ascii=False)

        handlers = conditionals_containing(blocks, expected_variable)
        assert any(
            f"BUTTON_{button}" in subtree_serialized(blocks, substack_root(handler))
            for handler in handlers
        )


def test_state_fields_are_cached_and_only_state_end_applies_outputs() -> None:
    blocks = load_stage_blocks()
    effect_suffixes = (
        "_esp32s3bit_canvasDisplayClearAll",
        "_esp32s3bit_canvasDisplayTextInLine",
        "_esp32s3bit_canvasDisplayUpdate",
        "_esp32s3bit_speechSynthesis",
        "_esp32s3bit_digitalWrite",
    )

    cache_fields = {
        "MODE|": "mode",
        "SERVICE|": "serviceName",
        "STEP|": "stepNow",
        "TITLE|": "titleText",
        "BODY|": "bodyText",
        "HELPER|": "helperText",
        "SPEAK|": "speechText",
        "LED|": "ledIndex",
    }
    for marker, variable in cache_fields.items():
        handlers = conditionals_containing(blocks, marker)
        assert handlers, f"缺少 {marker} 缓存分支"
        for handler in handlers:
            body_ids = block_tree_ids(blocks, substack_root(handler))
            body = [blocks[block_id] for block_id in body_ids]
            assert not any(
                item["opcode"].endswith(effect_suffixes) for item in body
            ), f"{marker} 在 STATE_END 前产生了输出"
            body_text = json.dumps(body, ensure_ascii=False)
            assert variable in body_text
            assert "operator_letter_of" in body_text

    begin_handlers = conditionals_containing(blocks, "STATE_BEGIN")
    assert begin_handlers
    for handler in begin_handlers:
        body = [
            blocks[block_id]
            for block_id in block_tree_ids(blocks, substack_root(handler))
        ]
        assert not any(item["opcode"].endswith(effect_suffixes) for item in body)

    end_handlers = conditionals_containing(blocks, "STATE_END")
    assert end_handlers
    end_body = "".join(
        subtree_serialized(blocks, substack_root(handler))
        for handler in end_handlers
    )
    assert "应用完整状态" in end_body
    apply_calls = [
        block_id
        for block_id, block in blocks.items()
        if block["opcode"] == "procedures_call"
        and block.get("mutation", {}).get("proccode") == "应用完整状态"
    ]
    assert len(apply_calls) == 1
    assert any(
        apply_calls[0] in block_tree_ids(blocks, substack_root(handler))
        for handler in end_handlers
    )

    apply_body = procedure_body_serialized(blocks, "应用完整状态")
    for expected in (
        "serviceName",
        "stepNow",
        "stepTotal",
        "titleText",
        "bodyText",
        "helperText",
        "speechText",
        "ledIndex",
        "esp32s3bit_canvasDisplayUpdate",
        "esp32s3bit_speechSynthesis",
        "点亮地图地点 %s",
    ):
        assert expected in apply_body

    light_body = procedure_body_serialized(blocks, "点亮地图地点 %s")
    assert light_body.count("esp32s3bit_digitalWrite") >= 6


def test_protocol_prefixes_never_reach_display_or_speech_directly() -> None:
    blocks = load_stage_blocks()
    for block in blocks.values():
        if not block["opcode"].endswith(
            ("_esp32s3bit_canvasDisplayTextInLine", "_esp32s3bit_speechSynthesis")
        ):
            continue
        rendered = json.dumps(block, ensure_ascii=False)
        for raw_input in block.get("inputs", {}).values():
            if not isinstance(raw_input, list):
                continue
            for item in raw_input[1:]:
                if isinstance(item, str) and item in blocks:
                    rendered += subtree_serialized(blocks, item)
        assert "rxLine" not in rendered


def test_heartbeat_timeout_turns_off_leds_and_displays_disconnect() -> None:
    blocks = load_stage_blocks()
    timeout_handlers = [
        handler
        for handler in conditionals_containing(blocks, "lastPingTime")
        if "5000" in subtree_serialized(blocks, condition_root(handler))
    ]
    assert timeout_handlers

    timeout_condition = "".join(
        subtree_serialized(blocks, condition_root(handler))
        for handler in timeout_handlers
    )
    assert "computerReady" in timeout_condition
    assert "esp32s3bit_timer" in timeout_condition

    timeout_body = "".join(
        subtree_serialized(blocks, substack_root(handler))
        for handler in timeout_handlers
    )
    assert "电脑连接已中断" in timeout_body
    assert "全部LED关闭" in timeout_body
    all_off_body = procedure_body_serialized(blocks, "全部LED关闭")
    assert all_off_body.count("esp32s3bit_digitalWrite") >= 6

    ping_handlers = conditionals_containing(blocks, "PING")
    assert ping_handlers
    assert any(
        "lastPingTime" in subtree_serialized(blocks, substack_root(handler))
        and "esp32s3bit_timer" in subtree_serialized(
            blocks, substack_root(handler)
        )
        for handler in ping_handlers
    )
