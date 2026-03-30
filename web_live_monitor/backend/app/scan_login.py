from __future__ import annotations

import hashlib
import hmac
import json
import time
from functools import lru_cache
from typing import Any

import requests

MIHOYO_API_SDK = "https://api-sdk.mihoyo.com"
TAKUMI_API = "https://api-takumi.mihoyo.com"
BH3_V2_LOGIN_URL = f"{MIHOYO_API_SDK}/bh3_cn/combo/granter/login/v2/login"
BH3_QR_SCAN_URL = f"{MIHOYO_API_SDK}/bh3_cn/combo/panda/qrcode/scan"
BH3_QR_CONFIRM_URL = f"{MIHOYO_API_SDK}/bh3_cn/combo/panda/qrcode/confirm"
BH3_OA_URL = "https://mi-m-cpjgtouitx.cn-hangzhou.fcapp.run"
TAKUMI_GAME_TOKEN_URL = f"{TAKUMI_API}/auth/api/getGameToken"

BH3_DEVICE_ID = "0000000000000000"
BH3_SIGN_KEY = "0ebc517adb1b62c6b408df153331f9aa"

OFFICIAL_GAME_CONFIG = {
    "8F3": {
        "app_id": 1,
        "scan_url": f"{MIHOYO_API_SDK}/bh3_cn/combo/panda/qrcode/scan",
        "confirm_url": f"{MIHOYO_API_SDK}/bh3_cn/combo/panda/qrcode/confirm",
    },
    "9E&": {
        "app_id": 4,
        "scan_url": f"{MIHOYO_API_SDK}/hk4e_cn/combo/panda/qrcode/scan",
        "confirm_url": f"{MIHOYO_API_SDK}/hk4e_cn/combo/panda/qrcode/confirm",
    },
    "8F%": {
        "app_id": 8,
        "scan_url": f"{MIHOYO_API_SDK}/hkrpg_cn/combo/panda/qrcode/scan",
        "confirm_url": f"{MIHOYO_API_SDK}/hkrpg_cn/combo/panda/qrcode/confirm",
    },
    "%BA": {
        "app_id": 12,
        "scan_url": f"{MIHOYO_API_SDK}/nap_cn/combo/panda/qrcode/scan",
        "confirm_url": f"{MIHOYO_API_SDK}/nap_cn/combo/panda/qrcode/confirm",
    },
}


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _post_json(session: requests.Session, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = session.post(
        url,
        data=_json_dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _get_json(session: requests.Session, url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = session.get(
        url,
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _make_sign(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in data.items():
        if key == "sign":
            continue
        if isinstance(value, str):
            string_value = value
        else:
            string_value = _json_dumps(value)
        parts.append(f"{key}={string_value}")

    param = "&".join(parts)
    return hmac.new(
        BH3_SIGN_KEY.encode("utf-8"),
        param.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@lru_cache(maxsize=1)
def _get_bh3_oa_string() -> str:
    response = requests.get(BH3_OA_URL, timeout=10)
    response.raise_for_status()
    text = response.text.strip()
    if not text:
        raise RuntimeError("empty OA dispatch string")
    return text


def _official_scan_confirm(
    *,
    session: requests.Session,
    game_code: str,
    ticket: str,
    uid: str,
    game_token: str,
    device_id: str,
) -> dict[str, Any]:
    cfg = OFFICIAL_GAME_CONFIG.get(game_code)
    if cfg is None:
        return {
            "ok": False,
            "stage": "scan",
            "message": f"unsupported game code for official login: {game_code}",
            "retcode": None,
        }

    scan_payload = {
        "app_id": cfg["app_id"],
        "device": device_id,
        "ticket": ticket,
    }
    scan_data = _post_json(session, cfg["scan_url"], scan_payload)
    scan_retcode = scan_data.get("retcode", -1)
    if scan_retcode != 0:
        return {
            "ok": False,
            "stage": "scan",
            "message": "official scan api failed",
            "retcode": scan_retcode,
            "response": scan_data,
        }

    confirm_payload = {
        "app_id": cfg["app_id"],
        "device": device_id,
        "ticket": ticket,
        "payload": {
            "proto": "Account",
            "raw": _json_dumps(
                {
                    "uid": uid,
                    "token": game_token,
                }
            ),
        },
    }
    confirm_data = _post_json(session, cfg["confirm_url"], confirm_payload)
    confirm_retcode = confirm_data.get("retcode", -1)

    return {
        "ok": confirm_retcode == 0,
        "stage": "confirm",
        "message": "official confirm api success" if confirm_retcode == 0 else "official confirm api failed",
        "retcode": confirm_retcode,
        "response": confirm_data,
    }


def _parse_cookie_like_pairs(token: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for chunk in token.split(";"):
        part = chunk.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            result[key] = value
    return result


def _get_game_token_by_stoken(
    *,
    session: requests.Session,
    stoken: str,
    mid: str,
) -> tuple[bool, dict[str, Any]]:
    data = _get_json(session, TAKUMI_GAME_TOKEN_URL, {"stoken": stoken, "mid": mid})
    retcode = data.get("retcode", -1)
    if retcode != 0:
        return False, {"retcode": retcode, "response": data}
    game_token = str(data.get("data", {}).get("game_token", "")).strip()
    if not game_token:
        return False, {"retcode": retcode, "response": data}
    return True, {"game_token": game_token}


def _resolve_official_game_token(
    *,
    session: requests.Session,
    token: str,
) -> tuple[bool, dict[str, Any]]:
    text = token.strip()
    if not text:
        return False, {
            "stage": "prepare",
            "message": "official token is empty",
            "retcode": None,
        }

    pairs = _parse_cookie_like_pairs(text)
    game_token = pairs.get("game_token")
    if game_token:
        return True, {"game_token": game_token}

    stoken = pairs.get("stoken")
    mid = pairs.get("mid")
    if stoken:
        if not mid:
            return False, {
                "stage": "prepare",
                "message": "official stoken token requires mid in cookie",
                "retcode": None,
            }
        ok, info = _get_game_token_by_stoken(session=session, stoken=stoken, mid=mid)
        if not ok:
            return False, {
                "stage": "prepare",
                "message": "exchange game_token by stoken failed",
                **info,
            }
        return True, {"game_token": info["game_token"]}

    # backward-compatible path: plain token is already game_token
    if "=" not in text and ";" not in text:
        return True, {"game_token": text}

    return False, {
        "stage": "prepare",
        "message": "official token must be game_token or cookie containing stoken+mid",
        "retcode": None,
    }


def _bh3_external_login_info(
    *,
    session: requests.Session,
    uid: str,
    access_key: str,
) -> tuple[bool, dict[str, Any]]:
    try:
        uid_value: int | str = int(uid)
    except ValueError:
        uid_value = uid

    body_data = _json_dumps(
        {
            "access_key": access_key,
            "uid": uid_value,
        }
    )

    body: dict[str, Any] = {
        "device": BH3_DEVICE_ID,
        "app_id": 1,
        "channel_id": 14,
        "data": body_data,
    }
    body["sign"] = _make_sign(body)

    response = _post_json(session, BH3_V2_LOGIN_URL, body)
    retcode = response.get("retcode", -1)
    if retcode != 0:
        return False, {
            "retcode": retcode,
            "response": response,
        }

    data = response.get("data", {})
    return True, {
        "open_id": data.get("open_id", ""),
        "combo_token": data.get("combo_token", ""),
        "combo_id": data.get("combo_id", ""),
    }


def _bh3_scan_confirm(
    *,
    session: requests.Session,
    ticket: str,
    uid: str,
    access_key: str,
    username: str,
) -> dict[str, Any]:
    scan_payload = {
        "app_id": "1",
        "device": BH3_DEVICE_ID,
        "ticket": ticket,
        "ts": int(time.time()),
    }
    scan_data = _post_json(session, BH3_QR_SCAN_URL, scan_payload)
    scan_retcode = scan_data.get("retcode", -1)
    if scan_retcode != 0:
        return {
            "ok": False,
            "stage": "scan",
            "message": "bh3 bilibili scan api failed",
            "retcode": scan_retcode,
            "response": scan_data,
        }

    ok, external_data = _bh3_external_login_info(session=session, uid=uid, access_key=access_key)
    if not ok:
        return {
            "ok": False,
            "stage": "external_login",
            "message": "bh3 external login api failed",
            **external_data,
        }

    raw = {
        "heartbeat": False,
        "open_id": external_data["open_id"],
        "device_id": BH3_DEVICE_ID,
        "app_id": "1",
        "channel_id": "14",
        "combo_token": external_data["combo_token"],
        "asterisk_name": username,
        "combo_id": external_data["combo_id"],
        "account_type": "2",
    }

    ext = {
        "data": {
            "accountType": "2",
            "accountID": "",
            "c": external_data["open_id"],
            "accountToken": external_data["combo_token"],
            "dispatch": _get_bh3_oa_string(),
        }
    }

    confirm_payload = {
        "device": BH3_DEVICE_ID,
        "app_id": 1,
        "ts": int(time.time()),
        "ticket": ticket,
        "payload": {
            "proto": "Combo",
            "raw": _json_dumps(raw),
            "ext": _json_dumps(ext),
        },
    }

    confirm_data = _post_json(session, BH3_QR_CONFIRM_URL, confirm_payload)
    confirm_retcode = confirm_data.get("retcode", -1)
    return {
        "ok": confirm_retcode == 0,
        "stage": "confirm",
        "message": "bh3 bilibili confirm api success" if confirm_retcode == 0 else "bh3 bilibili confirm api failed",
        "retcode": confirm_retcode,
        "response": confirm_data,
    }


def execute_scan_login(
    *,
    server_type: str,
    game_code: str,
    ticket: str,
    uid: str,
    token: str,
    username: str | None,
    device_id: str,
) -> dict[str, Any]:
    session = requests.Session()

    if server_type == "official":
        ok, token_info = _resolve_official_game_token(session=session, token=token)
        if not ok:
            return {
                "ok": False,
                **token_info,
            }
        return _official_scan_confirm(
            session=session,
            game_code=game_code,
            ticket=ticket,
            uid=uid,
            game_token=token_info["game_token"],
            device_id=device_id,
        )

    if server_type == "bh3_bilibili":
        if game_code != "8F3":
            return {
                "ok": False,
                "stage": "scan",
                "message": "bh3 bilibili only supports game code 8F3",
                "retcode": None,
            }
        if not username:
            return {
                "ok": False,
                "stage": "scan",
                "message": "username is required for bh3 bilibili scan login",
                "retcode": None,
            }

        return _bh3_scan_confirm(
            session=session,
            ticket=ticket,
            uid=uid,
            access_key=token,
            username=username,
        )

    return {
        "ok": False,
        "stage": "scan",
        "message": f"unsupported server_type: {server_type}",
        "retcode": None,
    }
