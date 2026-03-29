# Web Live Monitor

一个独立于原 C++ 客户端的前后端项目，只实现“监视直播间二维码”能力。

## 功能

- 支持平台：`B站`、`抖音`、`自定义直播页URL`
- 后端通过 `streamlink` 解析直播流地址
- 后端使用 OpenCV 实时识别二维码并提取：
  - `game_code`（兼容原项目规则：`8F3` / `9E&` / `8F%` / `%BA`）
  - `ticket`（末尾 24 位）
- 可选“自动扫码登录”闭环：
  - `official`：自动调用 `scan + confirm`
  - `bh3_bilibili`：自动调用 `scan + v2_login + confirm`
- WebSocket 实时推送事件（启动、解析流成功、识别成功、错误、停止）
- 前端控制台支持开始/停止监视、查看状态和日志

## 目录

- `backend/app/main.py`：FastAPI 入口
- `backend/app/monitor_service.py`：监视核心逻辑
- `backend/app/qr_parser.py`：二维码文本解析
- `frontend/`：静态前端页面

## 本地运行

1. 安装 Python 依赖：

```bash
cd web_live_monitor/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 启动服务：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

或直接一键运行：

```bash
cd web_live_monitor/backend
./run.sh
```

3. 浏览器访问：

```text
http://127.0.0.1:8000
```

## Docker 运行

```bash
cd web_live_monitor
docker compose up --build
```

## API

- `GET /api/health` 健康检查
- `GET /api/monitor/status` 当前监视状态
- `POST /api/monitor/start` 开始监视
- `POST /api/monitor/stop` 停止监视
- `WS /ws/events` 事件推送

`POST /api/monitor/start` 示例：

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

`bh3_bilibili` 额外需要：

```json
{
  "enable_scan_login": true,
  "server_type": "bh3_bilibili",
  "uid": "123456789",
  "token": "your_access_key",
  "username": "your_bh3_name"
}
```

## 依赖说明

- `streamlink`：解析直播页到真实流地址
- `opencv-python`：读取流并做二维码识别

如果系统没有 `streamlink` 命令，可通过 Python 包安装后使用：

```bash
pip install streamlink
```

或设置环境变量：

```bash
export STREAMLINK_COMMAND="python3 -m streamlink"
```
