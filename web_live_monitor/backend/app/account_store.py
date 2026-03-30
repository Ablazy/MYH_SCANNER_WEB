from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import AccountUpsertRequest
from .token_uid import resolve_uid_from_token


class AccountStoreError(ValueError):
    pass


class DuplicateAccountError(AccountStoreError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AccountStore:
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._lock = threading.Lock()
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        if self._file_path.exists():
            return

        data = {
            "version": 1,
            "default_account_id": None,
            "accounts": [],
        }
        self._write_json(data)

    def _read_json(self) -> dict[str, Any]:
        try:
            with self._file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {
                "version": 1,
                "default_account_id": None,
                "accounts": [],
            }
        except json.JSONDecodeError:
            data = {
                "version": 1,
                "default_account_id": None,
                "accounts": [],
            }

        if not isinstance(data, dict):
            data = {}
        if "accounts" not in data or not isinstance(data["accounts"], list):
            data["accounts"] = []
        data.setdefault("version", 1)
        data.setdefault("default_account_id", None)
        return data

    def _write_json(self, data: dict[str, Any]) -> None:
        tmp_path = self._file_path.with_suffix(self._file_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self._file_path)

    def list_accounts(self) -> dict[str, Any]:
        with self._lock:
            data = self._read_json()
            default_id = data.get("default_account_id")
            accounts = [
                {
                    **account,
                    "is_default": account.get("id") == default_id,
                }
                for account in data["accounts"]
            ]
            accounts.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
            return {
                "default_account_id": default_id,
                "accounts": accounts,
            }

    def add_account(self, request: AccountUpsertRequest) -> dict[str, Any]:
        with self._lock:
            data = self._read_json()
            uid = self._resolve_uid(request)
            if self._has_uid(data, uid):
                raise DuplicateAccountError(f"account with uid {uid} already exists")
            now = _utc_now_iso()
            account = {
                "id": uuid.uuid4().hex,
                "name": request.name,
                "server_type": request.server_type,
                "uid": uid,
                "token": request.token,
                "username": request.username,
                "created_at": now,
                "updated_at": now,
            }
            data["accounts"].append(account)
            if data.get("default_account_id") is None:
                data["default_account_id"] = account["id"]

            self._write_json(data)
            return {
                **account,
                "is_default": account["id"] == data.get("default_account_id"),
            }

    def update_account(self, account_id: str, request: AccountUpsertRequest) -> dict[str, Any] | None:
        with self._lock:
            data = self._read_json()
            uid = self._resolve_uid(request)
            if self._has_uid(data, uid, exclude_account_id=account_id):
                raise DuplicateAccountError(f"account with uid {uid} already exists")
            target: dict[str, Any] | None = None
            for account in data["accounts"]:
                if account.get("id") != account_id:
                    continue
                account["name"] = request.name
                account["server_type"] = request.server_type
                account["uid"] = uid
                account["token"] = request.token
                account["username"] = request.username
                account["updated_at"] = _utc_now_iso()
                target = account
                break

            if target is None:
                return None

            self._write_json(data)
            return {
                **target,
                "is_default": target.get("id") == data.get("default_account_id"),
            }

    def delete_account(self, account_id: str) -> bool:
        with self._lock:
            data = self._read_json()
            old_count = len(data["accounts"])
            data["accounts"] = [
                account for account in data["accounts"]
                if account.get("id") != account_id
            ]
            if len(data["accounts"]) == old_count:
                return False

            if data.get("default_account_id") == account_id:
                if data["accounts"]:
                    data["default_account_id"] = data["accounts"][0].get("id")
                else:
                    data["default_account_id"] = None

            self._write_json(data)
            return True

    def set_default_account(self, account_id: str) -> bool:
        with self._lock:
            data = self._read_json()
            found = any(account.get("id") == account_id for account in data["accounts"])
            if not found:
                return False
            data["default_account_id"] = account_id
            self._write_json(data)
            return True

    def _resolve_uid(self, request: AccountUpsertRequest) -> str:
        try:
            return resolve_uid_from_token(request.token)
        except ValueError as exc:
            raise AccountStoreError(str(exc)) from exc

    def _has_uid(
        self,
        data: dict[str, Any],
        uid: str,
        *,
        exclude_account_id: str | None = None,
    ) -> bool:
        for account in data["accounts"]:
            if exclude_account_id and account.get("id") == exclude_account_id:
                continue
            if str(account.get("uid", "")).strip() == uid:
                return True
        return False
