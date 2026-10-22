# Mind+ K10 Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有社区老人办事导航智能体接入 Mind+ V2 K10 积木程序、USB 串口桥和六路地图 LED，并交付可打开的原生 `.mp` 工程。

**Architecture:** K10 使用 Mind+ 积木处理离线命令词、A/B 键、屏幕、语音合成和 LED，只通过 115200 baud UTF-8 短协议与电脑通信。独立 Python 桥接进程保存当前 `session_id`，把 K10 指令转成现有 FastAPI REST 调用，再把 `SessionState.device` 转成 Mind+ 容易解析的逐行指令。现有知识库、规划、模型提供者和浏览器模拟器继续共用同一业务状态。

**Tech Stack:** Python 3.11+、FastAPI、httpx、Pydantic 2、pyserial 3.5、pytest、原生 HTML/CSS/SVG、Mind+ V2 上传模式、行空板 K10、DFR1231。

**Spec:** `docs/superpowers/specs/2026-10-22-mindplus-k10-integration-design.md`

## Global Constraints

- 必须使用 Mind+ V2 上传模式和行空板 K10 主控扩展。
- 串口 0 固定为 115200 baud、UTF-8、每条指令换行结束，单行最大 1024 字节。
- K10 只识别设计稿中 ID 10—17 的八个离线命令词，不宣称为自由语音听写。
- K10 只做交互和设备控制；知识检索、规划、安全校验、会话和模型选择仍在电脑端。
- 不在 Mind+ 工程、串口日志、浏览器资源或 Git 提交中写入 API Key。
- 未知信息固定播报“当前资料中没有这项信息，请向社区工作人员确认”并下发 `LED|0`。
- 电脑每 2 秒发送 `PING`；K10 连续 5 秒未收到时熄灭全部 LED 并显示断线提示。
- 六路 LED 映射固定为 1/P0、2/P1、3/P2、4/P8、5/P9、6/P12，每路使用 220—330 Ω 限流电阻。
- 原生 Mind+ 工程必须由 Mind+ V2 保存为 `mindplus/社区老人办事导航员-K10.mp`，并在 Mind+ 中重新打开验证，不手工伪造。
- 原有知识库仍为演示数据，文档和屏幕不得把它宣称为真实政务信息。

## Review Focus

- USB 数据可能拆成半行或一次到达多行；短协议缓冲器必须只在收到换行后交付完整指令，由 Task 1 的分片/合并测试锁定。
- 包含 `|`、控制字符、无效 UTF-8 或多字节超长的查询不得破坏帧边界，由 Task 1 的字节级验证测试锁定。
- FastAPI 重启后桥接程序可能保留失效 `session_id`；按键收到 404 时必须清空会话并下发人可理解的提示，由 Task 2 的过期会话测试锁定。
- Mind+ 串口监视器与 Python 桥不能同时占用同一 COM 口；打开失败时 CLI 必须显示关闭 Mind+ 连接的操作建议，由 Task 3 的占用错误测试锁定。
- 语音合成期间不能在按键中断里刷屏或做耗时通信；A/B 回调只改标志位，由 Task 5 的积木清单测试和 Task 6 的原生工程验证锁定。

---

## File Structure

```text
src/community_navigator/device_bridge/
  __init__.py       稳定对外导出
  protocol.py       K10 短协议、行缓冲和 DeviceState 帧编码
  controller.py     当前会话状态机与 REST 网关调用
  runtime.py        串口读写、心跳和有界重试
  cli.py            community-navigator-bridge 命令行入口
tests/
  test_device_protocol.py
  test_device_controller.py
  test_device_runtime.py
  test_mindplus_assets.py
  test_mindplus_project.py
mindplus/
  README.md
  01-积木搭建步骤.md
  02-接线与联调.md
  03-故障排查.md
  社区老人办事导航员-K10.mp
  assets/
    积木流程总览.svg
src/community_navigator/web/index.html
src/community_navigator/web/styles.css
pyproject.toml
README.md
```

### Task 1: K10 短协议与逐行缓冲

**Files:**
- Create: `src/community_navigator/device_bridge/__init__.py`
- Create: `src/community_navigator/device_bridge/protocol.py`
- Create: `tests/test_device_protocol.py`

**Interfaces:**
- Consumes: `community_navigator.models.SessionState`、`DeviceState`
- Produces: `DeviceCommand(kind: Literal["HELLO", "QUERY", "BUTTON_A", "BUTTON_B"], payload: str = "")`
- Produces: `LineBuffer.feed(chunk: bytes) -> list[bytes]`
- Produces: `parse_device_line(line: bytes) -> DeviceCommand`
- Produces: `encode_device_state(state: SessionState) -> tuple[bytes, ...]`
- Produces: `encode_ready(message: str = "智能体已连接") -> bytes`
- Produces: `encode_error(message: str) -> bytes`
- Produces: `encode_ping() -> bytes`

- [ ] **Step 1: Write failing command parsing and byte-limit tests**

Add tests named:

```python
def test_parse_hello_query_and_buttons() -> None: ...
def test_query_rejects_pipe_control_character_invalid_utf8_and_blank_text() -> None: ...
def test_byte_limit_counts_utf8_bytes_not_python_characters() -> None: ...
```

Assert `HELLO|1\n`、`QUERY|我想报名参加书法班\n`、`BUTTON_A\n`、`BUTTON_B\n` parse to the exact `DeviceCommand` values. Assert query payloads are limited to the REST contract's 1—200 characters. The 1024/1025-byte framing boundary is tested on `LineBuffer` in Step 4 so semantic query limits and transport limits remain separate.

- [ ] **Step 2: Run the focused tests and verify the import failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_device_protocol.py -v`

Expected: FAIL because `community_navigator.device_bridge.protocol` does not exist.

- [ ] **Step 3: Implement command parsing and sanitization**

In `protocol.py`, define `MAX_LINE_BYTES = 1024`, frozen `DeviceCommand`, `DeviceProtocolError`, `parse_device_line()`, and private field validation. Require exactly protocol version `1`; strip only the trailing CR/LF delimiter, not meaningful payload whitespace; reject query payloads outside 1—200 characters, `|`, remaining Unicode control characters and invalid UTF-8.

- [ ] **Step 4: Add failing fragmentation and coalescing tests**

```python
def test_line_buffer_waits_for_fragment_completion() -> None: ...
def test_line_buffer_returns_multiple_complete_lines_and_keeps_tail() -> None: ...
def test_line_buffer_rejects_an_overlong_unterminated_line() -> None: ...
```

Feed `b"QUE"`, then the remaining UTF-8 bytes and newline; expect no line before the newline and one exact line after it. Feed `BUTTON_A\nBUTTON_B\nQUE`; expect two lines and retain `QUE`. Feed an arbitrary transport record whose total size including newline is 1024 bytes and expect acceptance; 1025 bytes must raise `DeviceProtocolError`.

- [ ] **Step 5: Implement `LineBuffer`**

`LineBuffer.feed()` accumulates raw bytes, extracts newline-terminated records in order, rejects any pending or complete line over 1024 bytes, and never decodes bytes itself.

- [ ] **Step 6: Add failing device-state frame tests**

```python
def test_ready_state_encodes_complete_atomic_frame() -> None: ...
def test_unknown_state_encodes_led_zero_and_confirmation_speech() -> None: ...
def test_output_fields_replace_pipe_cr_and_lf_with_spaces() -> None: ...
```

For a calligraphy state assert exact markers `STATE_BEGIN\n` and `STATE_END\n`, `STEP|1|3\n`, and `LED|4\n`. For a not-found state assert `LED|0\n` and the fixed confirmation message in `SPEAK`. Assert all produced records are at most 1024 bytes and end in one newline.

- [ ] **Step 7: Implement state and control-line encoders**

Encode `MODE`, `SERVICE`, `STEP`, `TITLE`, `BODY`, `HELPER`, `SPEAK`, and one `LED` record between frame markers. Convert zero-based `current_step_index` to one-based `STEP`; use `0|0` when absent. Replace `|`, CR and LF in server-provided fields with spaces before byte-length validation.

- [ ] **Step 8: Run protocol tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_device_protocol.py -v`

Expected: all protocol tests PASS.

- [ ] **Step 9: Commit**

```powershell
git add src/community_navigator/device_bridge tests/test_device_protocol.py
git commit -m "feat: add Mind+ K10 serial protocol"
```

### Task 2: REST 网关与桥接会话控制器

**Files:**
- Create: `src/community_navigator/device_bridge/controller.py`
- Create: `tests/test_device_controller.py`
- Modify: `src/community_navigator/device_bridge/__init__.py`

**Interfaces:**
- Consumes: `DeviceCommand`, `encode_device_state()`, `encode_ready()`, `encode_error()` from Task 1
- Produces: `NavigatorGateway` protocol with `health() -> dict[str, object]`, `query(text: str) -> SessionState`, and `event(session_id: str, event_type: Literal["BUTTON_A", "BUTTON_B"]) -> SessionState`
- Produces: `HttpNavigatorGateway(base_url: str, timeout_seconds: float = 10.0, client: httpx.Client | None = None)`
- Produces: `BridgeController(gateway: NavigatorGateway)` with `current_session_id: str | None` and `handle(command: DeviceCommand) -> tuple[bytes, ...]`
- Produces: `BridgeGatewayError(message: str, *, stale_session: bool = False)`

- [ ] **Step 1: Write failing HTTP gateway contract tests**

Using `httpx.MockTransport`, add:

```python
def test_http_gateway_calls_health_query_and_event_routes() -> None: ...
def test_http_gateway_rejects_non_200_and_invalid_session_payloads() -> None: ...
def test_http_gateway_marks_404_event_as_stale_session() -> None: ...
```

Assert the exact routes `/api/v1/health`, `/api/v1/query`, and `/api/v1/sessions/{id}/events`, JSON bodies, 10-second timeout configuration, and `SessionState` validation.

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_device_controller.py -v`

Expected: FAIL because `controller.py` does not exist.

- [ ] **Step 3: Implement `HttpNavigatorGateway`**

Use the existing `httpx` dependency. Normalize `base_url` by removing a trailing slash. Convert timeouts, transport failures, non-success responses and invalid JSON/schema to `BridgeGatewayError`; never include headers or API secrets in the user-facing message.

- [ ] **Step 4: Write failing controller state-transition tests**

```python
def test_hello_returns_ready_without_creating_session() -> None: ...
def test_query_saves_session_and_returns_device_frame() -> None: ...
def test_buttons_use_current_session_and_return_latest_frame() -> None: ...
def test_button_without_session_returns_start_query_notice() -> None: ...
def test_stale_session_is_cleared_and_returns_recoverable_notice() -> None: ...
def test_gateway_failure_returns_led_zero_error_without_secret() -> None: ...
```

Use a fake gateway. Assert query replaces any previous session ID. Assert stale-session handling sets `current_session_id` to `None`. Assert no-session copy is exactly `请先说出您要办理的事情` and its complete notice frame contains `LED|0\n`. Assert gateway failure returns one sanitized `ERROR|...\n` record; the Mind+ error branch owns immediate LED shutdown.

- [ ] **Step 5: Implement `BridgeController`**

Map commands without serial I/O: `HELLO` returns `READY`; `QUERY` calls `gateway.query`; A/B call `gateway.event`. Build notices as complete device frames so K10 follows one rendering path. On stale session clear the ID; on other gateway failures retain no misleading LED or success state.

- [ ] **Step 6: Run controller and existing API tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_device_controller.py tests/test_api.py -v`

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/community_navigator/device_bridge tests/test_device_controller.py
git commit -m "feat: bridge K10 commands to navigator sessions"
```

### Task 3: 串口运行时、心跳和 CLI

**Files:**
- Create: `src/community_navigator/device_bridge/runtime.py`
- Create: `src/community_navigator/device_bridge/cli.py`
- Create: `tests/test_device_runtime.py`
- Modify: `pyproject.toml`
- Modify: `src/community_navigator/device_bridge/__init__.py`

**Interfaces:**
- Consumes: `LineBuffer`, `parse_device_line()`, `encode_ping()` from Task 1 and `BridgeController`, `HttpNavigatorGateway` from Task 2
- Produces: `SerialLike` protocol with `in_waiting: int`, `read(size: int) -> bytes`, `write(data: bytes) -> int`, `flush() -> None`, and `close() -> None`
- Produces: `BridgeRuntime(port: SerialLike, controller: BridgeController, *, heartbeat_seconds: float = 2.0, clock: Callable[[], float] = time.monotonic, interline_delay_seconds: float = 0.03, sleep: Callable[[float], None] = time.sleep)`
- Produces: `BridgeRuntime.poll_once() -> None`
- Produces: `open_serial_port(port: str, baud_rate: int = 115200) -> SerialLike`
- Produces: `serve_with_retries(..., retry_delays: tuple[float, ...] = (1.0, 2.0, 4.0)) -> int`
- Produces: `cli.run(argv: Sequence[str] | None = None) -> int`

- [ ] **Step 1: Add dependency and script-entry declarations**

Modify `pyproject.toml`:

```toml
"pyserial>=3.5,<4.0"
community-navigator-bridge = "community_navigator.device_bridge.cli:run"
```

Reinstall editable dependencies with `.venv\Scripts\python.exe -m pip install -e ".[dev]"`.

- [ ] **Step 2: Write failing runtime buffering and heartbeat tests**

```python
def test_runtime_handles_fragmented_and_coalesced_device_lines() -> None: ...
def test_runtime_sends_ping_at_two_seconds_not_on_every_poll() -> None: ...
def test_runtime_paces_multiline_frames_in_order() -> None: ...
def test_runtime_turns_protocol_error_into_safe_error_frame() -> None: ...
```

Use a fake serial port and fake clock. Assert one `PING\n` at 2.0 seconds, the next at 4.0 seconds, no duplicate between them, and 30 ms injected sleep between state-frame records.

- [ ] **Step 3: Run runtime tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_device_runtime.py -v`

Expected: FAIL because `runtime.py` does not exist.

- [ ] **Step 4: Implement `BridgeRuntime`**

Read available bytes into `LineBuffer`, parse each complete record, call the controller, and write response records in order. Flush after a response frame. Send heartbeat independently of device input. Do not put HTTP, parsing, or CLI argument logic inside the runtime.

- [ ] **Step 5: Write failing CLI and retry tests**

```python
def test_cli_checks_health_before_opening_serial_port() -> None: ...
def test_cli_uses_115200_and_explicit_port() -> None: ...
def test_port_in_use_message_tells_user_to_disconnect_mindplus() -> None: ...
def test_retry_delays_are_exactly_one_two_four_seconds() -> None: ...
def test_cli_never_prints_api_key_environment_value() -> None: ...
```

Inject gateway, opener, sleep and output functions into the retry boundary rather than touching a real COM port in tests.

- [ ] **Step 6: Implement serial open, bounded retry and CLI**

Arguments are `--port` (required), `--api-base` (default `http://127.0.0.1:8000`), and `--baud-rate` (default and allowed value `115200`). Check health before serial open. On access denied/port busy, print `COM端口被占用，请先在 Mind+ 中断开设备并关闭串口监视。`; retry after 1, 2 and 4 seconds, then return exit code 1.

- [ ] **Step 7: Run runtime, CLI and full bridge tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_device_protocol.py tests/test_device_controller.py tests/test_device_runtime.py -v`

Expected: all tests PASS.

- [ ] **Step 8: Verify both console entry points show help**

Run: `.venv\Scripts\community-navigator.exe --help`

Run: `.venv\Scripts\community-navigator-bridge.exe --help`

Expected: both exit successfully; bridge help lists `--port`, `--api-base`, and `--baud-rate`.

- [ ] **Step 9: Commit**

```powershell
git add pyproject.toml src/community_navigator/device_bridge tests/test_device_runtime.py
git commit -m "feat: add K10 USB serial bridge runtime"
```

### Task 4: 浏览器小喇叭 SVG 图标

**Files:**
- Modify: `src/community_navigator/web/index.html`
- Modify: `src/community_navigator/web/styles.css`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: existing `.speaker-strip` and `.speaker-icon` DOM structure
- Produces: one inline decorative `<svg class="speaker-icon" aria-hidden="true" viewBox="0 0 24 24">` with speaker body and two sound-wave paths

- [ ] **Step 1: Add a failing static HTML assertion**

Extend `test_simulator_page_has_accessible_controls_and_six_map_leds` or add `test_simulator_uses_inline_speaker_svg()` asserting:

```python
assert "◖))" not in html
assert '<svg class="speaker-icon"' in html
assert 'viewBox="0 0 24 24"' in html
assert html.count('class="speaker-wave"') == 2
```

- [ ] **Step 2: Run the test and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api.py::test_simulator_uses_inline_speaker_svg -v`

Expected: FAIL because the old text glyph is still present.

- [ ] **Step 3: Replace the glyph with inline SVG and focused CSS**

Use `fill="currentColor"` for the speaker body and `fill="none"`, `stroke="currentColor"`, `stroke-linecap="round"` for two waves. Set the icon to 25×25 px, `flex: 0 0 auto`, and retain `#ffca5a`; remove the obsolete font-weight rule.

- [ ] **Step 4: Run API tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api.py -v`

Expected: all API and static-page tests PASS.

- [ ] **Step 5: Start the mock server and visually inspect the strip**

Run: `.venv\Scripts\community-navigator.exe --port 8010`

Open `http://127.0.0.1:8010/` and verify the icon reads visually as a small speaker, aligns with the status text at desktop and narrow widths, and does not change the accessible text `扬声器：等待播报`.

- [ ] **Step 6: Commit**

```powershell
git add src/community_navigator/web/index.html src/community_navigator/web/styles.css tests/test_api.py
git commit -m "fix: replace speaker glyph with accessible icon"
```

### Task 5: Mind+ 积木搭建包与接线指南

**Files:**
- Create: `mindplus/README.md`
- Create: `mindplus/01-积木搭建步骤.md`
- Create: `mindplus/02-接线与联调.md`
- Create: `mindplus/03-故障排查.md`
- Create: `mindplus/assets/积木流程总览.svg`
- Create: `tests/test_mindplus_assets.py`

**Interfaces:**
- Consumes: exact protocol records and pin/voice mappings from the approved spec and Tasks 1—3
- Produces: a block-by-block guide that a pupil can follow without reading Python
- Produces: an SVG overview with seven visually separated groups: initialization, voice commands, serial receive, state application, LED custom block, A flag, B flag

- [ ] **Step 1: Write failing asset-completeness tests**

```python
def test_mindplus_guides_and_svg_exist_without_placeholders() -> None: ...
def test_build_guide_contains_all_variables_custom_blocks_and_voice_ids() -> None: ...
def test_wiring_guide_contains_six_led_pin_mappings_and_resistors() -> None: ...
def test_button_handlers_only_set_flags() -> None: ...
def test_overview_svg_is_valid_xml_with_seven_named_groups() -> None: ...
```

Assert no guide contains `TODO`, `TBD`, `待定` or `略`. Assert IDs 10—17 and pinyin commands match the spec exactly. Assert P0/P1/P2/P8/P9/P12 and `220—330 Ω` occur. Assert the A/B sections contain flag assignment but no screen, TTS, delay or serial-read instruction.

- [ ] **Step 2: Run the asset tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mindplus_assets.py -v`

Expected: FAIL because the `mindplus/` deliverables do not exist.

- [ ] **Step 3: Write `mindplus/README.md` as the pupil-facing entry point**

Include prerequisites, a five-step order (`接线 → 启动服务 → 上传积木 → 断开Mind+串口 → 启动桥`), links to the three guides and `.mp` file, demo-data disclosure, and the exact Mock/Ollama start commands.

- [ ] **Step 4: Write the block-by-block build guide**

Mirror the spec's variables and six custom blocks. For every block group record: Mind+ category, visible block wording, parameters, connection order, expected variable value, and one check after placement. Include the eight command-ID branches and exact Chinese query mapping. State that K10 uses the wake word `你好小行` and TTS speed `1`.

- [ ] **Step 5: Write wiring/integration and troubleshooting guides**

The wiring guide must show LED number, location, pin, resistor and polarity in one table; include direct USB data-cable and common-GND warnings. The integration guide must include COM discovery, upload, Mind+ disconnect, server start, bridge start, and the five physical scenarios. Troubleshooting must cover port busy, no `READY`, garbled text/wrong baud, wrong LED, wake-word failure, K10 reboot, server unavailable and five-second heartbeat timeout.

- [ ] **Step 6: Draw the code-native SVG block overview**

Create a 1600×1200 standalone SVG with large Chinese labels and Scratch-like colored rounded blocks. It is a visual assembly map, not a raster screenshot. Draw arrows for `语音命令 → QUERY → 串口接收 → STATE_END → 屏幕/语音/LED` and show A/B handlers as short flag-only branches.

- [ ] **Step 7: Run guide tests and visually inspect the SVG**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mindplus_assets.py -v`

Expected: all tests PASS.

Open `mindplus/assets/积木流程总览.svg`; verify all labels fit, arrows do not overlap blocks, and text remains legible at 50% zoom.

- [ ] **Step 8: Commit**

```powershell
git add mindplus tests/test_mindplus_assets.py
git commit -m "docs: add Mind+ K10 block-building kit"
```

### Task 6: Mind+ V2 原生 `.mp` 工程

**Files:**
- Create: `mindplus/社区老人办事导航员-K10.mp`
- Create: `tests/test_mindplus_project.py`

**Interfaces:**
- Consumes: the approved block guide and exact protocol from Tasks 1 and 5
- Produces: a Mind+ V2 native project that contains K10 upload-mode blocks and can be reopened by Mind+ V2

- [ ] **Step 1: Write the native-project artifact test**

```python
def test_mindplus_project_is_native_archive_with_contract_markers() -> None: ...
```

Open `mindplus/社区老人办事导航员-K10.mp` with `zipfile.ZipFile`. Assert `project.json` exists, JSON parses, and its serialized block/input content contains `HELLO|1`, `QUERY|`, `BUTTON_A`, `BUTTON_B`, `STATE_BEGIN`, `STATE_END`, `PING`, all pinyin commands, and all six pin identifiers. This test proves structure and contract markers but does not replace reopening it in Mind+.

- [ ] **Step 2: Run the test and verify the missing-file failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mindplus_project.py -v`

Expected: FAIL because the `.mp` project has not been saved yet.

- [ ] **Step 3: Install or open official Mind+ V2 with user authorization**

Use the official Mind+ V2 Windows distribution. If installation requires a download or system write, request the required approval before performing it. Confirm the displayed version is V2.0.4 or newer, select Chinese, create an upload-mode project, and add the `行空板K10` main-controller extension.

- [ ] **Step 4: Build the initialization and custom-block stacks in Mind+**

Follow `01-积木搭建步骤.md` exactly. Create all named variables and six custom blocks. Keep A/B event stacks flag-only. Use serial 0 at 115200, TTS speed 1, the six fixed output pins, and `HELLO|1` after initialization.

- [ ] **Step 5: Build voice-command and serial-state stacks**

Add IDs 10—17 with the exact pinyin phrases and query text. Add `READY`, `PING`, frame field, `STATE_END`, and `ERROR` branches. Ensure only `STATE_END` calls the full state-application block, and the 5000 ms heartbeat branch extinguishes all LEDs before displaying disconnect text.

- [ ] **Step 6: Save the native project and reopen it**

Use Mind+ `项目 → 保存项目` to save the exact path `mindplus/社区老人办事导航员-K10.mp`. Close the project, reopen this file in Mind+ V2, and visually compare every stack with the build guide. Do not edit the archive by hand.

- [ ] **Step 7: Run the archive test**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mindplus_project.py -v`

Expected: PASS; project archive and contract markers are present.

- [ ] **Step 8: Upload to a connected K10 and run the hardware smoke check**

Connect K10 directly by a data-capable Type-C cable, upload, and verify the initial page and all LEDs off. After upload, disconnect the Mind+ device/serial monitor before starting the Python bridge. If the board is not physically available, stop here and ask the user to connect it; do not claim hardware verification.

- [ ] **Step 9: Commit**

```powershell
git add 'mindplus/社区老人办事导航员-K10.mp' tests/test_mindplus_project.py
git commit -m "feat: add native Mind+ K10 project"
```

### Task 7: 用户运行手册与全链路验收

**Files:**
- Modify: `README.md`
- Modify: `mindplus/README.md`
- Modify: `tests/test_scenarios.py`

**Interfaces:**
- Consumes: both console entry points, native `.mp` project, guides, browser simulator and existing scenario tests
- Produces: one unambiguous start order and a recorded software/hardware verification result

- [ ] **Step 1: Add failing documentation-contract assertions**

Extend scenario or asset tests to assert the root README contains:

```text
community-navigator.exe
community-navigator-bridge.exe --port COM
Mind+ 串口占用
qwen3:0.6b
mindplus/社区老人办事导航员-K10.mp
```

Assert the listed order starts the API before the bridge and disconnects Mind+ serial before bridge startup.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_scenarios.py tests/test_mindplus_assets.py -v`

Expected: FAIL until README is updated.

- [ ] **Step 3: Update the root README**

Add `Mind+ K10 实体端` and `三分钟启动` sections. Give exact Mock, cloud and Ollama server commands; COM discovery instructions; bridge command; Mind+ upload/disconnect order; `.mp`/guides links; heartbeat behavior; demo-data disclosure; and a note that model switching never changes K10 blocks.

- [ ] **Step 4: Run the complete automated suite**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: all tests PASS; only already-known third-party deprecation warnings may remain.

- [ ] **Step 5: Run the software-only end-to-end check**

Start the mock API on port 8010. Use the fake-serial integration fixture to send `HELLO|1`, the calligraphy query, A, B and the passport query. Verify `READY`, LED 4, repeated step, advanced step, fixed unknown-information speech and LED 0 in that order. Stop all temporary processes afterward.

- [ ] **Step 6: Run and record physical acceptance when K10 is connected**

Execute the seven checks in spec section 12.2. Record date, Mind+ version, COM port, K10 firmware state, model provider, pass/fail and any observed limitation in `mindplus/02-接线与联调.md`. A missing board is an explicit unverified item, never a pass.

- [ ] **Step 7: Inspect the final diff and secret scan**

Run: `git diff --check`

Run: `rg -n "sk-[A-Za-z0-9]|MODEL_API_KEY\s*=\s*[^\"']|Authorization:\s*Bearer" . --glob '!*.mp'`

Expected: no whitespace errors and no committed secret values.

- [ ] **Step 8: Commit**

```powershell
git add README.md mindplus/README.md mindplus/02-接线与联调.md tests/test_scenarios.py tests/test_mindplus_assets.py
git commit -m "docs: add Mind+ K10 operating and acceptance guide"
```

## Final Verification Gate

- [ ] Run `.venv\Scripts\python.exe -m pytest -q` and capture the exact pass count.
- [ ] Run both `--help` entry points and one mock query through the browser simulator.
- [ ] Open `mindplus/assets/积木流程总览.svg` and verify layout.
- [ ] Reopen `mindplus/社区老人办事导航员-K10.mp` in Mind+ V2.
- [ ] If K10 is connected, rerun the complete physical checklist; otherwise report hardware as unverified.
- [ ] Confirm `git status --short` is clean and list the resulting commits.

