# K10 社区服务导航演示

这个项目用虚拟 K10 屏幕、A/B 按键和六个地图指示灯，演示社区服务的多轮对话导航。网页连接本机 Python 服务：现场可使用本机 Ollama 模型，开发测试时也可切换到云端兼容 API。

**社区地点、时间、材料和流程均为虚构演示数据。** 不连接真实社区系统、串口或实体 K10；模型可能出错，真实服务信息请向当地工作人员确认。

## 第一次准备（需要联网）

在 Windows 安装 Python 3.10 或更新版本，打开 PowerShell 并进入本项目文件夹：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

若需要运行项目测试，安装开发依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### 现场使用 Ollama

1. 提前安装并启动 Ollama，联网下载一个支持中文和结构化 JSON 的模型。
2. 用 `ollama list` 查看模型名称；在 `.env` 中设置 `MODEL_PROVIDER=ollama` 和准确的 `OLLAMA_MODEL`。例如安装了 `qwen3:0.6b` 时可以填写该名称；较小模型的理解与格式遵循能力可能不足，请提前测试。
3. 默认连接 `http://127.0.0.1:11434`。本地模式只允许访问本机回环地址，不会切换到云端。
4. 断网前启动一次并完成演练，确保模型、Python 依赖和浏览器本地中文语音都已可用。模型运行速度取决于电脑性能，必要时调整 `MODEL_TIMEOUT_SECONDS`。

### 测试时使用云端 API

在 `.env` 中设置：

```text
MODEL_PROVIDER=openai_compatible
CLOUD_BASE_URL=https://你的服务商兼容接口地址/v1
CLOUD_MODEL=你的模型名称
CLOUD_API_KEY=你的密钥
```

服务需要支持 OpenAI 兼容的 `/chat/completions` 和 JSON 对象输出。对外地址必须使用 HTTPS；本机回环测试地址可以使用 HTTP。密钥由 Python 服务读取，不进入网页，`.env` 已被 Git 忽略。切回离线演示时把 `MODEL_PROVIDER` 改为 `ollama` 并重启。

使用 DeepSeek 官方接口时，可将 `CLOUD_BASE_URL` 设为 `https://api.deepseek.com`，将 `CLOUD_MODEL` 设为 `deepseek-flash`。具体模型名称和接口以 [DeepSeek 官方文档](https://api-docs.deepseek.com/quick_start/)为准。

云端模式会向服务商发送演示资料和最近十轮对话。请不要在演示中输入身份证号、手机号等个人敏感信息。

## 启动与使用

双击 `start-simulator.bat`。启动成功后会打开 `http://127.0.0.1:8000/`；保持启动窗口开启，按 Ctrl+C 或关闭窗口结束服务。启动过程不会下载任何内容。直接打开 HTML 文件会显示启动说明。

输入问题或点击八个示例开始对话，也可以接着问“刚才那个什么时候上课”“需要带什么”。屏幕显示服务步骤，地图灯指向地点；A 返回上一步，B 前进一步，最后一步按 B 返回待机。文本也可以说“下一步”“重说一遍”或“结束导航”。点击“新对话”可清空当前会话显示并熄灯。

服务提供 `GET /api/v1/health`，以及 `/api/v1/sessions` 下的创建会话、发送消息和按键事件接口。会话只保存在本机内存中；新对话会移除此前会话，服务退出后数据不再保留。

播报只使用浏览器提供的本地中文语音；若不可用，文字仍可阅读。页面没有语音识别，示例按钮模拟原设备的语音指令。展开页面底部可查看模拟串口协议。

模型不可用或返回无效数据时，页面会显示错误；不会替换成预设的模型回答。已确认的导航步骤仍可用 A/B 按键查看。服务、时间和材料由演示知识库提供，模型的澄清和问候内容仍可能不准确。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
node --test tests/test_ui.cjs
```

自动测试使用模拟模型请求，不等同于真实模型或现场断网验收。接入实际模型后应在目标电脑上完成真实对话、断网、语音和键盘演练。
