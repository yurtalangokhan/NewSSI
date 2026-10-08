from __future__ import annotations

from schemas.schedules import (
    ScheduleRunStatus,
    SyncScheduleDeleteResponse,
    SyncScheduleInput,
    SyncScheduleListItem,
    SyncScheduleResponse,
    SyncScheduleUpdate,
)
from service.common.domain_errors import translate_domain_errors
from service.runtime.schedule_service import ScheduleService, get_schedule_service


def _get_service() -> ScheduleService:
    """Get the singleton ScheduleService instance."""
    return get_schedule_service()


@translate_domain_errors
async def list_all_schedules() -> list[SyncScheduleListItem]:
    """Return every sync schedule across all datasources."""
    return await _get_service().list_all_schedules()


@translate_domain_errors
async def create_schedule(datasource_id: str, body: SyncScheduleInput) -> SyncScheduleResponse:
    """Create a cron sync schedule for a datasource."""
    return await _get_service().create_schedule(datasource_id, body)


@translate_domain_errors
async def get_schedule(datasource_id: str) -> SyncScheduleResponse:
    """Get the sync schedule for a datasource."""
    return await _get_service().get_schedule(datasource_id)


@translate_domain_errors
async def update_schedule(datasource_id: str, body: SyncScheduleUpdate) -> SyncScheduleResponse:
    """Update an existing sync schedule."""
    return await _get_service().update_schedule(datasource_id, body)


@translate_domain_errors
async def delete_schedule(datasource_id: str) -> SyncScheduleDeleteResponse:
    """Remove the sync schedule; the datasource then syncs only on demand."""
    return await _get_service().delete_schedule(datasource_id)


@translate_domain_errors
async def get_schedule_run_status(datasource_id: str) -> ScheduleRunStatus:
    """Get combined sync + schedule status for real-time UI updates."""
    return await _get_service().get_schedule_run_status(datasource_id)
