from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .account_store import AccountStore
from .monitor_service import LiveMonitorService
from .schemas import AccountUpsertRequest, StartMonitorRequest

APP_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = APP_ROOT.parent.parent / "frontend"
ACCOUNT_FILE = APP_ROOT.parent / "data" / "accounts.json"

service = LiveMonitorService(streamlink_command=os.getenv("STREAMLINK_COMMAND", "streamlink"))
account_store = AccountStore(ACCOUNT_FILE)

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


@app.get("/api/accounts")
def list_accounts() -> dict[str, object]:
    return account_store.list_accounts()


@app.post("/api/accounts")
def add_account(request: AccountUpsertRequest) -> dict[str, object]:
    account = account_store.add_account(request)
    return {
        "account": account,
        **account_store.list_accounts(),
    }


@app.put("/api/accounts/{account_id}")
def update_account(account_id: str, request: AccountUpsertRequest) -> dict[str, object]:
    account = account_store.update_account(account_id, request)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return {
        "account": account,
        **account_store.list_accounts(),
    }


@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: str) -> dict[str, object]:
    ok = account_store.delete_account(account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="account not found")
    return account_store.list_accounts()


@app.post("/api/accounts/{account_id}/default")
def set_default_account(account_id: str) -> dict[str, object]:
    ok = account_store.set_default_account(account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="account not found")
    return account_store.list_accounts()


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
