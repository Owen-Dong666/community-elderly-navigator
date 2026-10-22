from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
MINDPLUS = ROOT / "mindplus"
GUIDES = (
    MINDPLUS / "README.md",
    MINDPLUS / "01-积木搭建步骤.md",
    MINDPLUS / "02-接线与联调.md",
    MINDPLUS / "03-故障排查.md",
)


def test_mindplus_guides_and_svg_exist_without_placeholders() -> None:
    files = (*GUIDES, MINDPLUS / "assets" / "积木流程总览.svg")

    for path in files:
        assert path.is_file(), f"缺少交付文件：{path.relative_to(ROOT)}"
        text = path.read_text(encoding="utf-8")
        assert text.strip(), f"交付文件为空：{path.relative_to(ROOT)}"
        assert not re.search(r"\b(?:TODO|TBD)\b|待定|略", text, re.IGNORECASE)


def test_build_guide_contains_all_variables_custom_blocks_and_voice_ids() -> None:
    text = (MINDPLUS / "01-积木搭建步骤.md").read_text(encoding="utf-8")
    variables = {
        "rxLine",
        "computerReady",
        "frameOpen",
        "lastPingTime",
        "buttonAFlag",
        "buttonBFlag",
        "mode",
        "serviceName",
        "stepNow",
        "stepTotal",
        "titleText",
        "bodyText",
        "helperText",
        "speechText",
        "ledIndex",
    }
    custom_blocks = {
        "全部LED关闭",
        "点亮地图地点(编号)",
        "显示初始页",
        "发送查询(文字)",
        "处理电脑指令(一行)",
        "应用完整状态",
    }
    commands = (
        (10, "shu fa ban", "我想报名参加书法班"),
        (11, "tai ji quan", "我想参加太极晨练"),
        (12, "liang xue ya", "哪里可以免费量血压"),
        (13, "she bao", "我想咨询社保"),
        (14, "gao ling jin tie", "我想咨询高龄津贴"),
        (15, "lao ren zhu can", "老人助餐点在哪里"),
        (16, "shui dian bao xiu", "家里水电坏了怎么报修"),
        (17, "ban hu zhao", "我想办理护照"),
    )

    for variable in variables:
        assert f"`{variable}`" in text
    for block in custom_blocks:
        assert f"`{block}`" in text
    for command_id, pinyin, query in commands:
        assert f"| {command_id} | `{pinyin}` | {query} |" in text
    assert "你好小行" in text
    assert "语速设为 `1`" in text


def test_wiring_guide_contains_six_led_pin_mappings_and_resistors() -> None:
    text = (MINDPLUS / "02-接线与联调.md").read_text(encoding="utf-8")
    mappings = (
        (1, "小区入口", "P0"),
        (2, "社区中心", "P1"),
        (3, "卫生站", "P2"),
        (4, "活动室", "P8"),
        (5, "服务大厅", "P9"),
        (6, "便民驿站", "P12"),
    )

    for led, place, pin in mappings:
        assert f"| {led} | {place} | `{pin}` |" in text
    assert "220—330 Ω" in text
    assert "公共 GND" in text
    assert "Type-C 数据线" in text


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"^### {re.escape(heading)}\s*$\n(?P<body>.*?)(?=^### |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"缺少章节：{heading}"
    return match.group("body")


def test_button_handlers_only_set_flags() -> None:
    text = (MINDPLUS / "01-积木搭建步骤.md").read_text(encoding="utf-8")

    for heading, flag in (("A 键事件", "buttonAFlag"), ("B 键事件", "buttonBFlag")):
        section = _section(text, heading)
        assert f"将 `{flag}` 设为 `1`" in section
        for forbidden in ("屏幕", "语音合成", "等待", "读取串口", "串口读取", "延时"):
            assert forbidden not in section


def test_overview_svg_is_valid_xml_with_seven_named_groups() -> None:
    root = ET.parse(MINDPLUS / "assets" / "积木流程总览.svg").getroot()

    assert root.attrib["viewBox"] == "0 0 1600 1200"
    assert root.attrib["width"] == "1600"
    assert root.attrib["height"] == "1200"
    groups = {
        node.attrib["data-group"]
        for node in root.iter()
        if "data-group" in node.attrib
    }
    assert groups == {
        "初始化",
        "语音命令",
        "串口接收",
        "状态应用",
        "LED自制积木",
        "A键标志",
        "B键标志",
    }
