from __future__ import annotations

import base64
import io
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

import requests

from .account_store import AccountStore, AccountStoreError, DuplicateAccountError
from .schemas import AccountUpsertRequest

HK4E_SDK_BASE = "https://hk4e-sdk.mihoyo.com/hk4e_cn"
QRCODE_FETCH_URL = f"{HK4E_SDK_BASE}/combo/panda/qrcode/fetch"
QRCODE_QUERY_URL = f"{HK4E_SDK_BASE}/combo/panda/qrcode/query"
TAKUMI_GAME_TOKEN_STOKEN_URL = "https://api-takumi.mihoyo.com/account/ma-cn-session/app/getTokenByGameToken"
MYS_USERINFO_URL = "https://bbs-api.miyoushe.com/user/api/getUserFullInfo"

LOGIN_APP_ID = 2

FINAL_STATES = {"confirmed", "expired", "duplicate", "error", "cancelled"}
STATE_TEXT = {
    "init": "等待扫码",
    "scanned": "已扫码，等待手机确认",
    "confirmed": "扫码登录成功，账号已写入",
    "expired": "二维码已失效，请重新获取",
    "duplicate": "该 UID 账号已存在",
    "error": "扫码流程异常",
    "cancelled": "扫码流程已取消",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OfficialQrAccountService:
    def __init__(self, account_store: AccountStore) -> None:
        self._account_store = account_store
        self._lock = threading.Lock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._device_id = str(uuid.uuid4())

    def start_session(self, *, name: str | None) -> dict[str, Any]:
        qrcode_url = self._fetch_qrcode_url()
        ticket = self._extract_ticket(qrcode_url)
        qrcode_image_data_url = self._make_qrcode_data_url(qrcode_url)

        session_id = uuid.uuid4().hex[:12]
        now = _utc_now_iso()
        session = {
            "session_id": session_id,
            "name": (name or "").strip() or None,
            "state": "init",
            "state_text": STATE_TEXT["init"],
            "ticket": ticket,
            "qrcode_url": qrcode_url,
            "qrcode_image_data_url": qrcode_image_data_url,
            "uid": None,
            "account": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        }

        with self._lock:
            self._sessions[session_id] = session

        return dict(session)

    def get_status(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError("session not found")
            if session["state"] in FINAL_STATES:
                return dict(session)

        polled = self._poll_remote_state(session_id)
        return polled

    def cancel_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError("session not found")
            if session["state"] not in FINAL_STATES:
                session["state"] = "cancelled"
                session["state_text"] = STATE_TEXT["cancelled"]
                session["updated_at"] = _utc_now_iso()
            return dict(session)

    def _poll_remote_state(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError("session not found")
            ticket = str(session["ticket"])

        try:
            remote_state, uid, game_token = self._query_qrcode_state(ticket)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                session = self._sessions[session_id]
                session["state"] = "error"
                session["state_text"] = STATE_TEXT["error"]
                session["last_error"] = f"query qrcode state failed: {exc}"
                session["updated_at"] = _utc_now_iso()
                return dict(session)

        if remote_state in {"init", "scanned"}:
            with self._lock:
                session = self._sessions[session_id]
                session["state"] = remote_state
                session["state_text"] = STATE_TEXT[remote_state]
                session["updated_at"] = _utc_now_iso()
                return dict(session)

        if remote_state == "expired":
            with self._lock:
                session = self._sessions[session_id]
                session["state"] = "expired"
                session["state_text"] = STATE_TEXT["expired"]
                session["updated_at"] = _utc_now_iso()
                return dict(session)

        # confirmed
        assert remote_state == "confirmed"
        try:
            mid, stoken = self._get_stoken_by_game_token(uid=uid, game_token=game_token)
            token = f"stuid={uid}; stoken={stoken}; mid={mid}"
            name = self._resolve_account_name(session_id=session_id, uid=uid)
            account = self._account_store.add_account(
                AccountUpsertRequest(
                    name=name,
                    server_type="official",
                    token=token,
                )
            )
            with self._lock:
                session = self._sessions[session_id]
                session["state"] = "confirmed"
                session["state_text"] = STATE_TEXT["confirmed"]
                session["uid"] = uid
                session["account"] = account
                session["updated_at"] = _utc_now_iso()
                return dict(session)
        except DuplicateAccountError as exc:
            with self._lock:
                session = self._sessions[session_id]
                session["state"] = "duplicate"
                session["state_text"] = STATE_TEXT["duplicate"]
                session["uid"] = uid
                session["last_error"] = str(exc)
                session["updated_at"] = _utc_now_iso()
                return dict(session)
        except AccountStoreError as exc:
            with self._lock:
                session = self._sessions[session_id]
                session["state"] = "error"
                session["state_text"] = STATE_TEXT["error"]
                session["uid"] = uid
                session["last_error"] = str(exc)
                session["updated_at"] = _utc_now_iso()
                return dict(session)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                session = self._sessions[session_id]
                session["state"] = "error"
                session["state_text"] = STATE_TEXT["error"]
                session["uid"] = uid
                session["last_error"] = f"save account failed: {exc}"
                session["updated_at"] = _utc_now_iso()
                return dict(session)

    def _resolve_account_name(self, *, session_id: str, uid: str) -> str:
        with self._lock:
            session = self._sessions[session_id]
            preferred = session.get("name")
        if isinstance(preferred, str) and preferred.strip():
            return preferred.strip()

        nickname = self._get_mys_nickname(uid)
        if nickname:
            return nickname
        return f"官服-{uid}"

    def _fetch_qrcode_url(self) -> str:
        response = requests.post(
            QRCODE_FETCH_URL,
            json={"app_id": LOGIN_APP_ID, "device": self._device_id},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        retcode = data.get("retcode", -1)
        if retcode != 0:
            raise RuntimeError(f"qrcode fetch failed: retcode={retcode}")
        url = str(data.get("data", {}).get("url", "")).strip()
        if not url:
            raise RuntimeError("qrcode fetch returned empty url")
        return url

    def _query_qrcode_state(self, ticket: str) -> tuple[str, str, str]:
        response = requests.post(
            QRCODE_QUERY_URL,
            json={"app_id": LOGIN_APP_ID, "device": self._device_id, "ticket": ticket},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        retcode = data.get("retcode", -1)
        if retcode != 0:
            return "expired", "", ""

        stat = str(data.get("data", {}).get("stat", "")).strip()
        stat_map = {
            "Init": "init",
            "Scanned": "scanned",
            "Confirmed": "confirmed",
        }
        state = stat_map.get(stat)
        if state is None:
            return "expired", "", ""
        if state != "confirmed":
            return state, "", ""

        raw = data.get("data", {}).get("payload", {}).get("raw", "")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid confirmed payload: {exc}") from exc

        uid = str(payload.get("uid", "")).strip()
        game_token = str(payload.get("token", "")).strip()
        if not uid or not game_token:
            raise RuntimeError("confirmed payload missing uid or token")
        return "confirmed", uid, game_token

    def _get_stoken_by_game_token(self, *, uid: str, game_token: str) -> tuple[str, str]:
        try:
            account_id: int | str = int(uid)
        except ValueError:
            account_id = uid

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) miHoYoBBS/2.76.1",
            "Accept": "application/json",
            "x-rpc-app_id": "bll8iq97cem8",
            "x-rpc-app_version": "2.76.1",
            "x-rpc-client_type": "2",
            "x-rpc-device_id": self._device_id,
            "x-rpc-device_name": "",
            "x-rpc-game_biz": "bbs_cn",
            "x-rpc-sdk_version": "2.16.0",
            "Content-Type": "application/json",
        }
        response = requests.post(
            TAKUMI_GAME_TOKEN_STOKEN_URL,
            json={"account_id": account_id, "game_token": game_token},
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        retcode = data.get("retcode", -1)
        if retcode != 0:
            raise RuntimeError(f"exchange stoken failed: retcode={retcode}")
        mid = str(data.get("data", {}).get("user_info", {}).get("mid", "")).strip()
        stoken = str(data.get("data", {}).get("token", {}).get("token", "")).strip()
        if not mid or not stoken:
            raise RuntimeError("exchange stoken response missing mid or stoken")
        return mid, stoken

    def _get_mys_nickname(self, uid: str) -> str | None:
        response = requests.get(
            MYS_USERINFO_URL,
            params={"uid": uid},
            timeout=10,
        )
        if response.status_code >= 400:
            return None
        try:
            data = response.json()
            nickname = str(data.get("data", {}).get("user_info", {}).get("nickname", "")).strip()
        except Exception:  # noqa: BLE001
            return None
        return nickname or None

    def _extract_ticket(self, qrcode_url: str) -> str:
        value = qrcode_url.strip()
        if len(value) < 24:
            raise ValueError("invalid qrcode url for ticket extraction")
        return value[-24:]

    def _make_qrcode_data_url(self, content: str) -> str:
        try:
            import qrcode
            import qrcode.image.svg
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("qrcode package is required, please install backend requirements") from exc

        image = qrcode.make(
            content,
            image_factory=qrcode.image.svg.SvgImage,
            box_size=8,
            border=2,
        )
        buf = io.BytesIO()
        image.save(buf)
        svg_bytes = buf.getvalue()
        b64 = base64.b64encode(svg_bytes).decode("ascii")
        return f"data:image/svg+xml;base64,{b64}"
