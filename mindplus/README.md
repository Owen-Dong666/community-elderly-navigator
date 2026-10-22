# Mind+ K10 积木搭建包

这是“小学组·社区老人的办事导航员”的 K10 实体端搭建入口。学生主要在 Mind+ V2 中理解和修改积木；电脑负责查知识库、规划步骤与连接 Mock、云端 API 或 Ollama 模型。

> 本包使用“幸福里社区”虚构演示数据，时间、地点和联系方式不能当作真实社区信息。

## 准备物品

- Windows 10/11 电脑，已安装 Python 3.11、Mind+ V2.0.4 或更新版本。
- 行空板 K10、DFR1231 K10 IO 扩展板、Type-C 数据线。
- 6 个 LED、6 个 220—330 Ω 限流电阻、纸板地图和连接线。
- 已按项目根目录 `README.md` 建好 `.venv` 并安装本项目。

## 按这个顺序操作

1. **接线**：按 [02-接线与联调.md](02-接线与联调.md) 连接六路地图 LED。
2. **启动服务**：先在项目目录启动电脑端智能体。
3. **上传积木**：在 Mind+ 打开 [社区老人办事导航员-K10.mp](社区老人办事导航员-K10.mp)，连接 K10 并上传。
4. **断开 Mind+ 串口**：上传完成后断开 Mind+ 的设备连接并关闭串口监视器。
5. **启动桥**：查到 K10 的 COM 号后启动 Python 串口桥。

同一个 COM 口不能同时被 Mind+ 和串口桥占用。顺序错了时，最常见现象就是“COM 端口被占用”。

## 电脑端启动命令

### 课堂保底：Mock 模型

Mock 不需要密钥，适合第一次联调和现场保底：

```powershell
$env:MODEL_PROVIDER="mock"
.\.venv\Scripts\community-navigator.exe
```

### 后期本地模型：Ollama + Qwen3 0.6B

先确保 Ollama 已安装并已执行一次：

```powershell
ollama pull qwen3:0.6b
```

再启动智能体：

```powershell
$env:MODEL_PROVIDER="ollama"
$env:MODEL_BASE_URL="http://127.0.0.1:11434"
$env:MODEL_NAME="qwen3:0.6b"
$env:MODEL_API_KEY=""
.\.venv\Scripts\community-navigator.exe
```

最后启动串口桥，把 `COM5` 改为设备管理器中看到的端口：

```powershell
.\.venv\Scripts\community-navigator-bridge.exe --port COM5
```

## 文件导航

- [01-积木搭建步骤.md](01-积木搭建步骤.md)：变量、自制积木和七组主流程的逐块说明。
- [02-接线与联调.md](02-接线与联调.md)：六路 LED 接线、上传顺序和五项实体演示。
- [03-故障排查.md](03-故障排查.md)：端口、心跳、乱码、语音和 LED 问题。
- [assets/积木流程总览.svg](assets/积木流程总览.svg)：可以放大查看的积木总览图。
- [社区老人办事导航员-K10.mp](社区老人办事导航员-K10.mp)：Mind+ V2 原生项目。

第一次从头搭建时先看总览图，再逐段照着 `01-积木搭建步骤.md` 放置。完成后必须用 `02-接线与联调.md` 的五项场景实测。
