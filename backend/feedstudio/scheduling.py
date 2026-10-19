"""Refresh schedules: when the next automatic run of a source is due.

Modes:
- ``manual``: never runs automatically.
- ``interval``: every N hours (N in ALLOWED_HOURS), counted from the last run.
- ``daily``: at fixed local times ("08:00", "20:00") in an IANA time zone.
  Daylight-saving transitions are handled by ``zoneinfo``: a time that does not
  exist on a given day (spring forward, e.g. 02:30 in Madrid on the last Sunday
  of March) is shifted forward by the DST offset (runs at 03:30 local time).

All datetimes stored and returned are timezone-aware UTC.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_HOURS = (1, 2, 3, 4, 6, 8, 12, 24)
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class ScheduleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["manual", "interval", "daily"] = "manual"
    every_hours: int | None = Field(default=None, description="interval mode")
    times: list[str] = Field(default_factory=list, max_length=24, description="daily mode, HH:MM")
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        if v != "UTC" and v not in available_timezones():
            raise ValueError(f"Zona horaria desconocida: {v}")
        return v

    @field_validator("times")
    @classmethod
    def _times(cls, v: list[str]) -> list[str]:
        for t in v:
            if not _TIME_RE.match(t):
                raise ValueError(f"Hora inválida '{t}' (formato HH:MM)")
        return sorted(set(v))

    @model_validator(mode="after")
    def _mode(self) -> "ScheduleConfig":
        if self.mode == "interval" and self.every_hours not in ALLOWED_HOURS:
            raise ValueError(f"every_hours debe ser uno de {ALLOWED_HOURS}")
        if self.mode == "daily" and not self.times:
            raise ValueError("Indica al menos una hora de actualización")
        return self


def _zone(name: str) -> ZoneInfo | timezone:
    if name == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:  # pragma: no cover - validated earlier
        raise ValueError(f"Zona horaria desconocida: {name}") from exc


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def next_run(config: ScheduleConfig, after: datetime) -> datetime | None:
    """First due instant strictly after ``after`` (UTC), or None for manual."""
    after = _utc(after)
    if config.mode == "manual":
        return None
    if config.mode == "interval":
        assert config.every_hours is not None
        return after + timedelta(hours=config.every_hours)

    tz = _zone(config.timezone)
    local_after = after.astimezone(tz)
    candidates: list[datetime] = []
    for day_offset in range(0, 3):
        day = (local_after + timedelta(days=day_offset)).date()
        for value in config.times:
            hh, mm = (int(x) for x in value.split(":"))
            local = datetime.combine(day, time(hh, mm), tzinfo=tz)
            # Normalize non-existent local times (DST gap) through a UTC round trip.
            instant = local.astimezone(timezone.utc)
            if instant > after:
                candidates.append(instant)
        if candidates:
            break
    return min(candidates) if candidates else None


def describe(config: ScheduleConfig) -> str:
    if config.mode == "manual":
        return "Manual"
    if config.mode == "interval":
        return "Cada hora" if config.every_hours == 1 else f"Cada {config.every_hours} horas"
    return f"Diario a las {', '.join(config.times)} ({config.timezone})"
