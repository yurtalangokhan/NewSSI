from enum import StrEnum

from pydantic import BaseModel


class SchedulePreset(StrEnum):
    CUSTOM = "custom"
    EVERY_5_MIN = "every_5_min"
    EVERY_15_MIN = "every_15_min"
    EVERY_30_MIN = "every_30_min"
    HOURLY = "hourly"
    EVERY_6_HOURS = "every_6_hours"
    EVERY_12_HOURS = "every_12_hours"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


PRESET_CRON_MAP = {
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


class SyncScheduleInput(BaseModel):
    cron_expression: str
    preset: SchedulePreset = SchedulePreset.CUSTOM
    enabled: bool = True
    update_graph_rag: bool = False
    timezone: str = "UTC"


class SyncScheduleUpdate(BaseModel):
    cron_expression: str | None = None
    preset: SchedulePreset | None = None
    enabled: bool | None = None
    update_graph_rag: bool | None = None
    timezone: str | None = None


class SyncScheduleResponse(BaseModel):
    id: str
    datasource_id: str
    cron_expression: str
    preset: str
    enabled: bool
    update_graph_rag: bool
    timezone: str
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_run_status: str | None = None
    created_at: str
    updated_at: str


class SyncScheduleListItem(BaseModel):
    id: str
    datasource_id: str
    datasource_name: str | None = None
    cron_expression: str
    preset: str
    enabled: bool
    update_graph_rag: bool
    next_run_at: str | None = None
    last_run_status: str | None = None


class ScheduleRunStatus(BaseModel):
    datasource_id: str
    sync_status: str
    sync_progress: int = 0
    queue_position: int | None = None
    scheduled: bool = False
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_run_status: str | None = None
    update_graph_rag: bool = False
    graph_update_status: str | None = None
