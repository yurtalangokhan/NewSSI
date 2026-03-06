"""
Sync Schedule Pydantic Models.

Defines input/output schemas for the schedule CRUD API
and the database row representation.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SchedulePreset(StrEnum):
    """Well-known cron presets for the frontend picker."""

    EVERY_5_MIN = "every_5_min"
    EVERY_15_MIN = "every_15_min"
    EVERY_30_MIN = "every_30_min"
    HOURLY = "hourly"
    EVERY_6_HOURS = "every_6_hours"
    EVERY_12_HOURS = "every_12_hours"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


# Map presets → 6-field Quartz cron expressions (seconds min hour dom month dow)
PRESET_CRON_MAP: dict[SchedulePreset, str] = {
    SchedulePreset.EVERY_5_MIN: "0 */5 * * * ?",
    SchedulePreset.EVERY_15_MIN: "0 */15 * * * ?",
    SchedulePreset.EVERY_30_MIN: "0 */30 * * * ?",
    SchedulePreset.HOURLY: "0 0 * * * ?",
    SchedulePreset.EVERY_6_HOURS: "0 0 */6 * * ?",
    SchedulePreset.EVERY_12_HOURS: "0 0 */12 * * ?",
    SchedulePreset.DAILY: "0 0 0 * * ?",
    SchedulePreset.WEEKLY: "0 0 0 * * 1",
    SchedulePreset.MONTHLY: "0 0 0 1 * ?",
}


# ------------------------------------------------------------------
# Input models
# ------------------------------------------------------------------


class SyncScheduleInput(BaseModel):
    """Body for creating or updating a sync schedule."""

    cron_expression: str = Field(
        ...,
        description=(
            "Quartz 6-field cron expression (seconds minute hour dom month dow). "
            "Ignored when preset != 'custom'."
        ),
        examples=["0 */15 * * * ?", "0 0 0 * * 1"],
    )
    preset: SchedulePreset = Field(
        SchedulePreset.CUSTOM,
        description="Convenience preset; when not 'custom' the server resolves the cron expression.",
    )
    enabled: bool = Field(True, description="Whether the schedule is active.")
    update_graph_rag: bool = Field(
        False,
        description="Rebuild the knowledge graph after every successful sync.",
    )
    timezone: str = Field("UTC", description="IANA timezone for the cron trigger.")

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        v = v.strip()
        _validate_quartz_cron(v)
        return v


class SyncScheduleUpdate(BaseModel):
    """Partial update – every field is optional."""

    cron_expression: Optional[str] = None
    preset: Optional[SchedulePreset] = None
    enabled: Optional[bool] = None
    update_graph_rag: Optional[bool] = None
    timezone: Optional[str] = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        _validate_quartz_cron(v)
        return v


def _quartz_to_unix(cron_expr: str) -> str:
    """Convert 6-field Quartz cron to 5-field unix cron for croniter.

    Quartz:  seconds minute hour dom month dow
    Unix:    minute hour dom month dow
    """
    parts = cron_expr.strip().split()
    if len(parts) == 6:
        # Drop leading seconds, replace '?' with '*'
        return " ".join(p.replace("?", "*") for p in parts[1:])
    return cron_expr


def _validate_quartz_cron(v: str) -> None:
    """Validate a 6-field Quartz cron expression."""
    from croniter import croniter

    parts = v.split()
    if len(parts) != 6:
        raise ValueError(
            f"Expected 6-field Quartz cron (seconds min hour dom month dow), got {len(parts)} fields: {v!r}"
        )
    # Validate by converting to 5-field for croniter
    unix_cron = _quartz_to_unix(v)
    if not croniter.is_valid(unix_cron):
        raise ValueError(f"Invalid cron expression: {v!r}")


# ------------------------------------------------------------------
# Response models
# ------------------------------------------------------------------


class SyncScheduleResponse(BaseModel):
    """Full schedule representation returned by the API."""

    id: str
    datasource_id: str
    cron_expression: str
    preset: str
    enabled: bool
    update_graph_rag: bool
    timezone: str
    next_run_at: Optional[str] = None
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None
    created_at: str
    updated_at: str


class SyncScheduleListItem(BaseModel):
    """Lightweight schedule entry used in list endpoints."""

    id: str
    datasource_id: str
    datasource_name: Optional[str] = None
    cron_expression: str
    preset: str
    enabled: bool
    update_graph_rag: bool
    next_run_at: Optional[str] = None
    last_run_status: Optional[str] = None


class ScheduleRunStatus(BaseModel):
    """Real-time status returned while a scheduled sync is running."""

    datasource_id: str
    sync_status: str
    sync_progress: int = 0
    queue_position: Optional[int] = None
    scheduled: bool = False
    next_run_at: Optional[str] = None
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None
    update_graph_rag: bool = False
    graph_update_status: Optional[str] = None
