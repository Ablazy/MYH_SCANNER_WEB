# MHY Scanner Web Live Monitor

基于 Web 的直播间二维码监视与扫码登录工具，聚焦“直播流解析 -> 二维码识别 -> 可选自动扫码登录”的完整链路。

## 项目来源

本仓库基于原始项目 [Theresa-0328/MHY_Scanner](https://github.com/Theresa-0328/MHY_Scanner) 的思路与核心规则进行重构。

- 保留：直播二维码识别规则、`ScanModel` 模型方案、扫码登录流程（`official` / `bh3_bilibili`）
- 重构：改为 `FastAPI + 静态前端` 的前后端架构
- 移除：原生 C++/Qt 桌面界面、屏幕监视等与当前 Web 场景无关模块

感谢原项目作者的开源工作。本项目继续遵循仓库根目录的 `GPL-3.0` 许可证。

## 功能特性

- 支持直播来源：`B站`、`抖音`、`自定义直播页 URL`
- 使用 `streamlink` 解析真实流地址
- 使用 `OpenCV WeChatQRCode + ScanModel` 识别二维码
- 解析并提取：
  - `game_code`（`8F3` / `9E&` / `8F%` / `%BA`）
  - `ticket`（二维码文本末尾 24 位）
- 可选自动扫码登录：
  - `official`：`scan + confirm`
  - `bh3_bilibili`：`scan + v2_login + confirm`
- 账号管理：保存、更新、删除、设置默认账号，并可回填到监视配置
- 支持官服“扫码添加账号”（网页展示二维码，手机确认后自动入库）
- WebSocket 实时事件推送 + 页面实时画面预览

## 仓库结构

```text
.
├── ScanModel/                    # WeChatQRCode 所需模型文件
└── web_live_monitor/
    ├── backend/
    │   ├── app/main.py           # FastAPI 入口
    │   ├── app/monitor_service.py
    │   ├── app/scan_login.py
    │   ├── app/account_store.py
    │   ├── requirements.txt
    │   └── run.sh
    ├── frontend/                 # 静态页面（index.html/app.js/styles.css）
    ├── Dockerfile
    └── docker-compose.yml
```

## 环境要求

- Python `3.11+`
- Linux/macOS（Windows 也可运行，但以下命令以 Unix shell 为例）
- 依赖包：`fastapi`、`uvicorn`、`opencv-contrib-python`、`streamlink`、`requests`、`qrcode`
- 根目录存在 `ScanModel` 文件：
  - `detect.prototxt`
  - `detect.caffemodel`
  - `sr.prototxt`
  - `sr.caffemodel`

## 快速开始（本地）

```bash
cd web_live_monitor/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

或手动启动：

```bash
cd web_live_monitor/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

浏览器访问：`http://127.0.0.1:8000`

## Docker 运行

```bash
cd web_live_monitor
docker compose up --build
```

说明：二维码识别依赖 `ScanModel`。如容器环境无法读到模型文件，请把模型目录挂载到容器内 `/ScanModel`。

## 关键配置

- `STREAMLINK_COMMAND`：自定义 `streamlink` 命令（默认 `streamlink`）
  - 示例：`export STREAMLINK_COMMAND="python3 -m streamlink"`
- 账号数据文件：`web_live_monitor/backend/data/accounts.json`

## 接口概览

- `GET /api/health`：健康检查
- `GET /api/monitor/status`：获取监视状态
- `GET /api/monitor/frame`：获取最新画面 JPEG
- `POST /api/monitor/start`：开始监视
- `POST /api/monitor/stop`：停止监视
- `WS /ws/events`：实时事件推送
- `GET /api/accounts`：账号列表
- `POST /api/accounts`：新增账号
- `PUT /api/accounts/{account_id}`：更新账号
- `DELETE /api/accounts/{account_id}`：删除账号
- `POST /api/accounts/{account_id}/default`：设置默认账号
- `POST /api/accounts/official-qr/start`：开始官服扫码添加
- `GET /api/accounts/official-qr/{session_id}/status`：查询扫码状态
- `POST /api/accounts/official-qr/{session_id}/cancel`：取消扫码流程

`POST /api/monitor/start` 示例（官服）：

```json
{
  "platform": "bilibili",
  "room_id": "6",
  "quality": "best",
  "scan_interval_ms": 500,
  "auto_stop_on_ticket": true,
  "enable_scan_login": true,
  "server_type": "official",
  "uid": "123456789",
  "token": "your_game_token"
}
```

`bh3_bilibili` 额外字段示例：

```json
{
  "enable_scan_login": true,
  "server_type": "bh3_bilibili",
  "uid": "123456789",
  "token": "your_access_key",
  "username": "your_bh3_name"
}
```

## 注意事项

- 本项目仅供学习与技术研究，请遵守直播平台和相关服务条款。
- `token/access_key` 属于敏感凭据，建议仅在受信环境中使用。
- 若识别不到二维码，请优先检查：
  - `opencv-contrib-python` 是否安装成功
  - `ScanModel` 四个模型文件是否完整且路径正确
  - 直播流是否可被 `streamlink` 正常解析
