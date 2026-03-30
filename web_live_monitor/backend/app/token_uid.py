from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from typing import Any

_UID_KEYS = ("stuid", "ltuid", "account_id", "uid", "aid")
_UID_DIGITS_RE = re.compile(r"^[0-9]{5,20}$")
_UID_KV_RE = re.compile(
    r"(?:^|[;,&\s])(?:stuid|ltuid|account_id|uid|aid)\s*[:=]\s*([0-9]{5,20})(?:$|[;,&\s])",
    re.IGNORECASE,
)


def _normalize_uid(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not _UID_DIGITS_RE.fullmatch(text):
        return None
    return text


def _uid_from_mapping(data: Mapping[str, Any]) -> str | None:
    for key in _UID_KEYS:
        if key not in data:
            continue
        uid = _normalize_uid(data.get(key))
        if uid:
            return uid
    return None


def _uid_from_cookie_like(token: str) -> str | None:
    pairs: dict[str, str] = {}
    for chunk in token.split(";"):
        piece = chunk.strip()
        if not piece or "=" not in piece:
            continue
        key, value = piece.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        pairs[key] = value
    if not pairs:
        return None
    return _uid_from_mapping(pairs)


def _uid_from_json_text(token: str) -> str | None:
    text = token.strip()
    if not text:
        return None
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return _uid_from_mapping(parsed)


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None

    payload = parts[1].strip()
    if not payload:
        return None

    padding = "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload + padding)
        parsed = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def resolve_uid_from_token(token: str) -> str:
    value = token.strip()
    if not value:
        raise ValueError("token cannot be empty")

    uid = _uid_from_cookie_like(value)
    if uid:
        return uid

    uid = _uid_from_json_text(value)
    if uid:
        return uid

    jwt_like = value
    if value.lower().startswith("bearer "):
        jwt_like = value[7:].strip()
    payload = _decode_jwt_payload(jwt_like)
    if payload is not None:
        uid = _uid_from_mapping(payload)
        if uid:
            return uid

    match = _UID_KV_RE.search(value)
    if match:
        return match.group(1)

    raise ValueError(
        "cannot extract uid from token. "
        "For official accounts please provide cookie/token containing stuid/ltuid/account_id."
    )
