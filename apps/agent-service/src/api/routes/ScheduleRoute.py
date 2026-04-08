"""
Sync Schedule API Routes.

CRUD endpoints for managing sync schedules via Airbyte native connection
scheduling.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from controller import ScheduleController, get_schedule_controller
from service.ScheduleModels import (
    ScheduleRunStatus,
    SyncScheduleInput,
    SyncScheduleListItem,
    SyncScheduleResponse,
    SyncScheduleUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync-schedules"])


def _get_controller() -> ScheduleController:
    """Get the singleton ScheduleController instance."""
    return get_schedule_controller()


@router.get("/datasources/schedules", response_model=list[SyncScheduleListItem])
async def list_all_schedules():
    """Return every sync schedule across all datasources."""
    ctrl = _get_controller()
    return await ctrl.list_all_schedules()


@router.post("/{datasource_id}/schedule", response_model=SyncScheduleResponse)
async def create_schedule(datasource_id: str, body: SyncScheduleInput):
    """Create a sync schedule by setting cron on the Airbyte connection."""
    ctrl = _get_controller()
    return await ctrl.create_schedule(datasource_id, body)


@router.get("/{datasource_id}/schedule", response_model=SyncScheduleResponse)
async def get_schedule(datasource_id: str):
    """Get the sync schedule for a datasource."""
    ctrl = _get_controller()
    return await ctrl.get_schedule(datasource_id)


@router.put("/{datasource_id}/schedule", response_model=SyncScheduleResponse)
async def update_schedule(datasource_id: str, body: SyncScheduleUpdate):
    """Update an existing sync schedule."""
    ctrl = _get_controller()
    return await ctrl.update_schedule(datasource_id, body)


@router.delete("/{datasource_id}/schedule")
async def delete_schedule(datasource_id: str):
    """Remove the sync schedule (set Airbyte connection to manual)."""
    ctrl = _get_controller()
    return await ctrl.delete_schedule(datasource_id)


@router.get("/{datasource_id}/schedule/status", response_model=ScheduleRunStatus)
async def get_schedule_run_status(datasource_id: str):
    """Get combined sync + schedule status for real-time UI updates."""
    ctrl = _get_controller()
    return await ctrl.get_schedule_run_status(datasource_id)
