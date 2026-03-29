from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .monitor_service import LiveMonitorService
from .schemas import StartMonitorRequest

APP_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = APP_ROOT.parent.parent / "frontend"

service = LiveMonitorService(streamlink_command=os.getenv("STREAMLINK_COMMAND", "streamlink"))

app = FastAPI(
    title="Live Room QR Monitor",
    version="0.1.0",
    description="Web full-stack live room monitoring service for QR detection.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    service.bind_event_loop(asyncio.get_running_loop())


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "service": "live-room-qr-monitor",
    }


@app.get("/api/monitor/status")
def monitor_status() -> dict[str, object]:
    return service.get_status()


@app.get("/api/monitor/frame")
def monitor_frame() -> Response:
    frame = service.get_latest_frame_jpeg()
    if frame is None:
        raise HTTPException(status_code=404, detail="frame not ready")

    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.post("/api/monitor/start")
def start_monitor(request: StartMonitorRequest) -> dict[str, object]:
    try:
        return service.start_monitor(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/monitor/stop")
def stop_monitor() -> dict[str, object]:
    return service.stop_monitor()


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    await websocket.accept()
    service.add_client(websocket)

    await websocket.send_json(
        {
            "type": "hello",
            "time": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "message": "connected",
                "status": service.get_status(),
            },
        }
    )

    try:
        while True:
            message = await websocket.receive_text()
            if message.strip().lower() == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "time": datetime.now(timezone.utc).isoformat(),
                        "payload": {},
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        service.remove_client(websocket)


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
