from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class StartMonitorRequest(BaseModel):
    platform: Literal["bilibili", "douyin", "custom"] = "bilibili"
    room_id: str | None = Field(default=None, max_length=128)
    quality: str = Field(default="best", min_length=1, max_length=32)
    custom_url: str | None = Field(default=None, max_length=1024)
    auto_stop_on_ticket: bool = True
    enable_scan_login: bool = False
    server_type: Literal["official", "bh3_bilibili"] | None = None
    uid: str | None = Field(default=None, max_length=64)
    token: str | None = Field(default=None, max_length=2048)
    username: str | None = Field(default=None, max_length=128)

    @field_validator("room_id")
    @classmethod
    def strip_room_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None

    @field_validator("quality")
    @classmethod
    def strip_quality(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("quality cannot be empty")
        return value

    @field_validator("custom_url")
    @classmethod
    def strip_custom_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None

    @field_validator("uid")
    @classmethod
    def strip_uid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None

    @field_validator("token")
    @classmethod
    def strip_token(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None

    @field_validator("username")
    @classmethod
    def strip_username(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_login_fields(self) -> "StartMonitorRequest":
        if self.platform in {"bilibili", "douyin"} and not self.room_id:
            raise ValueError("room_id is required for bilibili/douyin")
        if self.platform == "custom" and not self.custom_url:
            raise ValueError("custom_url is required when platform is custom")

        if not self.enable_scan_login:
            return self

        if not self.server_type:
            raise ValueError("server_type is required when enable_scan_login is true")
        if not self.uid:
            raise ValueError("uid is required when enable_scan_login is true")
        if not self.token:
            raise ValueError("token is required when enable_scan_login is true")

        if self.server_type == "bh3_bilibili" and not self.username:
            raise ValueError("username is required for bh3_bilibili scan login")

        return self


class AccountUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    server_type: Literal["official", "bh3_bilibili"]
    token: str = Field(..., min_length=1, max_length=2048)
    username: str | None = Field(default=None, max_length=128)

    @field_validator("name", "token")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field cannot be empty")
        return value

    @field_validator("username")
    @classmethod
    def strip_username(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_server_specific_fields(self) -> "AccountUpsertRequest":
        if self.server_type == "bh3_bilibili" and not self.username:
            raise ValueError("username is required for bh3_bilibili account")
        return self


class OfficialQrStartRequest(BaseModel):
    name: str | None = Field(default=None, max_length=64)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None
