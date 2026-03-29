from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class StartMonitorRequest(BaseModel):
    platform: Literal["bilibili", "douyin", "custom"] = "bilibili"
    room_id: str = Field(..., min_length=1, max_length=128)
    quality: str = Field(default="best", min_length=1, max_length=32)
    scan_interval_ms: int = Field(default=500, ge=100, le=5000)
    custom_url: str | None = Field(default=None, max_length=1024)
    auto_stop_on_ticket: bool = True

    @field_validator("room_id")
    @classmethod
    def strip_room_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("room_id cannot be empty")
        return value

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
