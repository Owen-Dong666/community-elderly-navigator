# 社区老人的办事导航员

面向小学组“智能体设计与应用”项目的第一阶段原型：**电脑端智能体 + 浏览器 K10 模拟器**。

老人可以用语音或文字询问社区活动、便民服务；系统查询本地社区资料，给出逐步指引，在模拟纸板地图上点亮地点，并用浏览器扬声器播报。知识库没有答案时，系统固定提示：

> 当前资料中没有这项信息，请向社区工作人员确认

当前所有社区名称、时间、地点和服务内容都是为原型编写的**演示数据**，不能当作真实政务信息使用。

## 已实现功能

- 15 项社区服务、6 个社区地点和 1—6 号地图 LED 映射。
- 文字输入与浏览器语音识别（浏览器支持时可用）。
- 确定性服务检索，不靠大模型猜测服务。
- 检索—规划—执行完整智能体流程。
- 大模型输出的服务、地点、时间、材料和来源校验。
- Mock、云端 OpenAI 兼容 API、Ollama 三种模型通道。
- K10 模拟屏幕、扬声器状态、A/B 大按钮与地图 LED。
- A 键重复播报当前步骤，B 键切换下一步骤；最后一步再按 B 结束。
- 为后期 USB 串口桥预留版本化 UTF-8 JSON Lines 协议。
- 对未知事项、模型超时、非法输出和提示词注入进行安全降级。

## 智能体框架

```text
感知 Perception
  语音识别 / 文字输入
          ↓
  确定性知识库检索
          ↓
规划 Planning
  云端 API / Ollama / Mock 生成步骤草案
          ↓
  来源校验；不一致就使用知识库固定步骤
          ↓
执行 Action
  屏幕显示 + 语音播报 + LED 亮灯 + A/B 按钮
```

大模型只负责把已找到的资料整理成适合老人阅读和播报的步骤，不负责发明服务信息。电脑端保存唯一会话状态，因此浏览器模拟器与未来的 K10 串口桥可以共用相同业务逻辑。

## 环境准备

要求：Windows 10/11、Python 3.11 或更高版本。

在项目目录打开 PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

运行全部测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 最快启动：零密钥 Mock 演示

默认就是 `mock` 模式，不需要 API Key，也不需要安装本地模型：

```powershell
.\.venv\Scripts\community-navigator.exe
```

也可以直接运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn community_navigator.main:app --host 127.0.0.1 --port 8000
```

浏览器打开：<http://127.0.0.1:8000/>

如果 8000 端口已被占用：

```powershell
.\.venv\Scripts\community-navigator.exe --port 8010
```

## 切换云端 OpenAI 兼容 API

不要在代码或提交记录中写真实密钥。下面的地址、模型名和密钥都要替换成所用平台提供的值：

```powershell
$env:MODEL_PROVIDER="openai_compatible"
$env:MODEL_BASE_URL="https://api.example.com"
$env:MODEL_NAME="replace-with-model-name"
$env:MODEL_API_KEY="replace-with-api-key"
$env:MODEL_TIMEOUT_SECONDS="20"
.\.venv\Scripts\community-navigator.exe
```

程序调用兼容接口的 `/v1/chat/completions` 路径。关闭当前 PowerShell 窗口后，上述临时环境变量不会继续保留。

## 后期切换本地 Ollama + Qwen3 0.6B

Ollama 和模型需要单独安装、下载；本项目不会自动安装它们。安装好 Ollama 后先在 PowerShell 执行：

```powershell
ollama pull qwen3:0.6b
```

再启动本项目：

```powershell
$env:MODEL_PROVIDER="ollama"
$env:MODEL_BASE_URL="http://127.0.0.1:11434"
$env:MODEL_NAME="qwen3:0.6b"
$env:MODEL_API_KEY=""
.\.venv\Scripts\community-navigator.exe
```

如果本机实际模型标签不同，只需修改 `MODEL_NAME`。业务代码、知识库、API 和模拟器都不需要改变。

`.env.example` 是配置项目清单；本程序直接读取系统环境变量，不会自动载入 `.env` 文件。

## 修改演示知识库

数据文件位于 `data/demo_community.json`，编码必须保持 UTF-8。

安全修改规则：

1. `location.id` 和 `service.id` 不能重复。
2. 六个地点的 `led_index` 使用 1—6，且不能重复。
3. 每项服务的 `location_id` 必须引用一个已存在地点。
4. `schedule`、`steps` 和地点不能留空；不确定的真实信息不要猜。
5. `aliases` 写老人常用说法，`keywords` 写能区分该服务的关键词。
6. 可能变化的信息设置 `requires_confirmation: true`，并写清 `contact_note`。
7. 修改后运行完整测试，再进行现场演示。

开发演示时可以访问 `GET /api/v1/knowledge/services` 查看资料。若不希望开放该接口，把 `EXPOSE_KNOWLEDGE_API` 设为 `false`。

## 五分钟现场演示脚本

**第 0:00—0:40 分钟：介绍问题**

“社区老人经常不知道活动在哪里、什么时候去、需要准备什么。我们的智能体把查询、步骤、语音和纸板地图结合起来。”

**第 0:40—2:20 分钟：已知服务**

1. 对麦克风说或输入“我想报名参加书法班”。
2. 指出地图上 4 号“活动室”LED 点亮。
3. 展示 K10 屏幕上的第 1 步和扬声器播报。
4. 按 A 键，说明它会重复当前步骤，方便老人再听一次。
5. 按 B 键逐步前进，直到最后一步；再按 B，屏幕回到结束状态，LED 熄灭。

**第 2:20—3:10 分钟：换一种问法**

输入“哪里可以免费量血压”，展示系统找到卫生站并点亮 3 号 LED，说明检索支持老人日常说法。

**第 3:10—3:50 分钟：未知服务安全边界**

输入“我想办理护照”。屏幕必须显示“当前资料中没有这项信息，请向社区工作人员确认”，所有 LED 保持关闭。强调系统不会编造答案。

**第 3:50—5:00 分钟：智能体与后续硬件**

说明“感知—规划—执行”三层；展示模型可从云端 API 切到本地 Ollama；说明下一阶段会让 K10 通过 USB 串口收发同一套会话状态，驱动真实屏幕、扬声器和纸板地图 LED。

## 建议现场问题

- 我想报名参加书法班。
- 哪里可以免费量血压？
- 家里水管坏了找谁？
- 助餐点在哪里？
- 请问社区怎么借书？
- 我想办理护照。（用于展示未知信息保护）

## 当前限制与下一阶段接口

- 使用虚构的“幸福里社区”演示数据，正式展示时应明确标注。
- 语音识别和播报依赖浏览器能力；录音不会发送给本项目的 Python 服务器，但浏览器是否使用在线语音服务以其自身隐私说明为准。不支持语音时文字输入仍可完整演示。
- 当前未连接实体 K10、DFR1231 扩展板和真实 LED。
- 当前会话保存在内存，程序重启后清空，适合单机现场演示。
- `serial_protocol.py` 已定义 `QUERY`、`BUTTON_A`、`BUTTON_B`、`DEVICE_STATE` 四类版本 1 消息，后续 Mind+ 串口桥可直接对接。

## 比赛材料披露提醒

项目说明和答辩中建议主动写明：

- 社区服务资料为原型演示数据，不对应真实社区。
- 项目使用了生成式人工智能辅助设计、编程或整理资料时，应按比赛文件要求如实披露使用范围。
- 展示结论由团队测试和审核；遇到知识库外信息必须交由社区工作人员确认。

## 主要目录

```text
data/demo_community.json              演示知识库
src/community_navigator/retrieval.py  确定性服务检索
src/community_navigator/planning.py   安全规划与来源校验
src/community_navigator/providers.py  Mock / 云端 / Ollama 适配
src/community_navigator/sessions.py   A/B 按钮和设备状态机
src/community_navigator/web/          浏览器 K10 模拟器
tests/                                单元、接口与场景回归测试
```
