from __future__ import annotations

import asyncio
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

import cv2
from fastapi import WebSocket

from .qr_parser import parse_qr_payload
from .scan_login import execute_scan_login
from .schemas import StartMonitorRequest
from .wechat_qr_scanner import WeChatQRScanner


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LiveMonitorService:
    def __init__(self, streamlink_command: str = "streamlink") -> None:
        self._state_lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._ws_clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

        self._worker_thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None

        self._streamlink_command = streamlink_command
        self._qr_scanner = WeChatQRScanner()
        self._qr_warning_emitted = False
        self._device_id = str(uuid.uuid4())
        self._latest_frame_jpeg: bytes | None = None

        self._state: dict[str, Any] = {
            "running": False,
            "session_id": None,
            "platform": None,
            "room_id": None,
            "room_url": None,
            "stream_url": None,
            "quality": None,
            "qr_backend": self._qr_scanner.backend_name,
            "qr_model_dir": self._qr_scanner.model_dir,
            "qr_ready": self._qr_scanner.is_ready,
            "qr_error": self._qr_scanner.error_message,
            "scan_interval_ms": None,
            "auto_stop_on_ticket": True,
            "enable_scan_login": False,
            "server_type": None,
            "started_at": None,
            "stopped_at": None,
            "last_frame_at": None,
            "last_preview_at": None,
            "last_detection_at": None,
            "detections_count": 0,
            "last_qr_text": None,
            "last_game_name": None,
            "last_ticket": None,
            "last_scan_login_at": None,
            "last_scan_login_ok": None,
            "last_scan_login_stage": None,
            "last_scan_login_message": None,
            "last_error": None,
        }

    def bind_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def add_client(self, websocket: WebSocket) -> None:
        self._ws_clients.add(websocket)

    def remove_client(self, websocket: WebSocket) -> None:
        self._ws_clients.discard(websocket)

    def get_status(self) -> dict[str, Any]:
        with self._state_lock:
            return dict(self._state)

    def get_latest_frame_jpeg(self) -> bytes | None:
        with self._frame_lock:
            if self._latest_frame_jpeg is None:
                return None
            return bytes(self._latest_frame_jpeg)

    def start_monitor(self, request: StartMonitorRequest) -> dict[str, Any]:
        with self._state_lock:
            if self._state["running"]:
                raise RuntimeError("monitor is already running")

            room_url = self._build_room_url(request)
            stop_event = threading.Event()
            session_id = uuid.uuid4().hex[:12]

            self._state.update(
                {
                    "running": True,
                    "session_id": session_id,
                    "platform": request.platform,
                    "room_id": request.room_id,
                    "room_url": room_url,
                    "stream_url": None,
                    "quality": request.quality,
                    "qr_backend": self._qr_scanner.backend_name,
                    "qr_model_dir": self._qr_scanner.model_dir,
                    "qr_ready": self._qr_scanner.is_ready,
                    "qr_error": self._qr_scanner.error_message,
                    "scan_interval_ms": request.scan_interval_ms,
                    "auto_stop_on_ticket": request.auto_stop_on_ticket,
                    "enable_scan_login": request.enable_scan_login,
                    "server_type": request.server_type,
                    "started_at": _utc_now_iso(),
                    "stopped_at": None,
                    "last_frame_at": None,
                    "last_preview_at": None,
                    "last_detection_at": None,
                    "detections_count": 0,
                    "last_qr_text": None,
                    "last_game_name": None,
                    "last_ticket": None,
                    "last_scan_login_at": None,
                    "last_scan_login_ok": None,
                    "last_scan_login_stage": None,
                    "last_scan_login_message": None,
                    "last_error": None,
                }
            )

            self._stop_event = stop_event
            self._qr_warning_emitted = False
            with self._frame_lock:
                self._latest_frame_jpeg = None
            self._worker_thread = threading.Thread(
                target=self._monitor_worker,
                args=(request, room_url, session_id, stop_event),
                daemon=True,
                name=f"live-monitor-{session_id}",
            )
            self._worker_thread.start()

        self._emit_event(
            "monitor_started",
            {
                "session_id": session_id,
                "platform": request.platform,
                "room_id": request.room_id,
                "room_url": room_url,
                "quality": request.quality,
                "scan_interval_ms": request.scan_interval_ms,
                "enable_scan_login": request.enable_scan_login,
                "server_type": request.server_type,
            },
        )
        return self.get_status()

    def stop_monitor(self) -> dict[str, Any]:
        with self._state_lock:
            stop_event = self._stop_event
            was_running = bool(self._state["running"])

        if stop_event is not None:
            stop_event.set()

        if was_running:
            self._emit_event("monitor_stopping", {"reason": "manual_stop"})

        return self.get_status()

    def _build_room_url(self, request: StartMonitorRequest) -> str:
        if request.platform == "bilibili":
            return f"https://live.bilibili.com/{request.room_id}"
        if request.platform == "douyin":
            return f"https://live.douyin.com/{request.room_id}"
        if not request.custom_url:
            raise ValueError("custom_url is required when platform is custom")
        return request.custom_url

    def _resolve_stream_url(self, room_url: str, quality: str) -> str:
        base_args = ["--stream-url", "--loglevel", "warning", room_url, quality]

        commands: list[list[str]] = []
        commands.append([*shlex.split(self._streamlink_command), *base_args])

        if shutil.which("streamlink") is None:
            commands.append([sys.executable, "-m", "streamlink", *base_args])

        last_error = "streamlink failed"
        for command in commands:
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=40,
                    check=False,
                )
            except FileNotFoundError:
                last_error = f"command not found: {' '.join(command)}"
                continue
            except subprocess.TimeoutExpired:
                last_error = f"streamlink timeout: {' '.join(command)}"
                continue

            if completed.returncode != 0:
                stderr = completed.stderr.strip()
                stdout = completed.stdout.strip()
                tail = stderr or stdout or f"exit code {completed.returncode}"
                last_error = f"streamlink error: {tail}"
                continue

            lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
            if not lines:
                last_error = "streamlink returned empty stream url"
                continue

            stream_url = lines[-1]
            if stream_url.startswith("http://") or stream_url.startswith("https://"):
                return stream_url

            last_error = f"unexpected stream url: {stream_url}"

        raise RuntimeError(last_error)

    def _decode_payloads(self, frame: Any) -> Iterable[str]:
        if not self._qr_scanner.is_ready:
            return []
        try:
            return self._qr_scanner.decode(frame)
        except Exception:
            return []

    def _monitor_worker(
        self,
        request: StartMonitorRequest,
        room_url: str,
        session_id: str,
        stop_event: threading.Event,
    ) -> None:
        capture: cv2.VideoCapture | None = None
        seen_payload_at: dict[str, float] = {}

        try:
            stream_url = self._resolve_stream_url(room_url, request.quality)
            with self._state_lock:
                self._state["stream_url"] = stream_url

            self._emit_event("stream_resolved", {"stream_url": stream_url})

            capture = cv2.VideoCapture(stream_url)
            if not capture.isOpened():
                raise RuntimeError("cannot open stream with OpenCV VideoCapture")

            self._emit_event("stream_opened", {"session_id": session_id})
            if not self._qr_scanner.is_ready and not self._qr_warning_emitted:
                self._qr_warning_emitted = True
                self._emit_event(
                    "monitor_warning",
                    {
                        "message": self._qr_scanner.error_message
                        or "qr scanner is not ready; preview works but decode is disabled",
                    },
                )

            scan_interval_sec = request.scan_interval_ms / 1000.0
            last_scan_at = 0.0
            last_preview_encode_at = 0.0
            read_fail_count = 0

            while not stop_event.is_set():
                ok, frame = capture.read()
                now = time.monotonic()

                if not ok or frame is None:
                    read_fail_count += 1
                    if read_fail_count > 80:
                        raise RuntimeError("stream frame read failed repeatedly")
                    time.sleep(0.05)
                    continue

                read_fail_count = 0
                with self._state_lock:
                    self._state["last_frame_at"] = _utc_now_iso()

                if now - last_preview_encode_at >= 0.25:
                    self._update_latest_frame(frame)
                    last_preview_encode_at = now

                if now - last_scan_at < scan_interval_sec:
                    continue
                last_scan_at = now

                payloads = self._decode_payloads(frame)
                if not payloads:
                    continue

                for payload in payloads:
                    text = payload.strip()
                    if not text:
                        continue

                    last_seen = seen_payload_at.get(text)
                    if last_seen is not None and now - last_seen < 3:
                        continue
                    seen_payload_at[text] = now

                    # prevent map growth in very long sessions
                    if len(seen_payload_at) > 256:
                        expire_before = now - 120
                        seen_payload_at = {
                            key: value
                            for key, value in seen_payload_at.items()
                            if value >= expire_before
                        }

                    parsed = parse_qr_payload(text)
                    detection_time = _utc_now_iso()

                    with self._state_lock:
                        self._state["detections_count"] += 1
                        self._state["last_qr_text"] = parsed["raw_text"]
                        self._state["last_game_name"] = parsed["game_name"]
                        self._state["last_ticket"] = parsed["ticket"]
                        self._state["last_detection_at"] = detection_time

                    self._emit_event(
                        "qr_detected",
                        {
                            "detected_at": detection_time,
                            **parsed,
                        },
                    )

                    if parsed["ticket"] and request.enable_scan_login:
                        login_result = self._perform_scan_login(request=request, parsed=parsed)
                        login_time = _utc_now_iso()
                        with self._state_lock:
                            self._state["last_scan_login_at"] = login_time
                            self._state["last_scan_login_ok"] = login_result.get("ok")
                            self._state["last_scan_login_stage"] = login_result.get("stage")
                            self._state["last_scan_login_message"] = login_result.get("message")

                        self._emit_event(
                            "scan_login_result",
                            {
                                "login_at": login_time,
                                "ticket": parsed["ticket"],
                                "game_code": parsed["game_code"],
                                "game_name": parsed["game_name"],
                                **login_result,
                            },
                        )

                    if parsed["ticket"] and request.auto_stop_on_ticket:
                        self._emit_event(
                            "ticket_detected",
                            {
                                "detected_at": detection_time,
                                "ticket": parsed["ticket"],
                                "game_name": parsed["game_name"],
                                "auto_stop": True,
                            },
                        )
                        stop_event.set()
                        break

        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            with self._state_lock:
                self._state["last_error"] = message
            self._emit_event("monitor_error", {"message": message})

        finally:
            if capture is not None:
                capture.release()

            with self._state_lock:
                self._state["running"] = False
                self._state["stopped_at"] = _utc_now_iso()
                self._stop_event = None
                self._worker_thread = None

            self._emit_event(
                "monitor_stopped",
                {
                    "session_id": session_id,
                    "last_error": self.get_status().get("last_error"),
                },
            )

    def _perform_scan_login(
        self,
        *,
        request: StartMonitorRequest,
        parsed: dict[str, str | None],
    ) -> dict[str, Any]:
        game_code = parsed.get("game_code")
        ticket = parsed.get("ticket")
        if not game_code or not ticket:
            return {
                "ok": False,
                "stage": "scan",
                "message": "missing game_code or ticket for scan login",
                "retcode": None,
            }

        try:
            return execute_scan_login(
                server_type=request.server_type or "",
                game_code=game_code,
                ticket=ticket,
                uid=request.uid or "",
                token=request.token or "",
                username=request.username,
                device_id=self._device_id,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "stage": "error",
                "message": f"scan login exception: {exc}",
                "retcode": None,
            }

    def _update_latest_frame(self, frame: Any) -> None:
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if not ok:
            return
        preview_at = _utc_now_iso()
        with self._frame_lock:
            self._latest_frame_jpeg = buf.tobytes()
        with self._state_lock:
            self._state["last_preview_at"] = preview_at

    def _emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._loop is None:
            return

        event = {
            "type": event_type,
            "time": _utc_now_iso(),
            "payload": payload,
        }
        asyncio.run_coroutine_threadsafe(self._broadcast(event), self._loop)

    async def _broadcast(self, event: dict[str, Any]) -> None:
        if not self._ws_clients:
            return

        dead: list[WebSocket] = []
        for client in list(self._ws_clients):
            try:
                await client.send_json(event)
            except Exception:  # noqa: BLE001
                dead.append(client)

        for client in dead:
            self._ws_clients.discard(client)
