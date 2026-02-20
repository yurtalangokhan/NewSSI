"""
Sync Schedule API Routes.

CRUD endpoints for managing cron-based sync schedules.
Separated from ``datasources.py`` to follow SRP.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException

from service.schedule_db import ScheduleDBManager
from service.schedule_models import (
    PRESET_CRON_MAP,
    SchedulePreset,
    ScheduleRunStatus,
    SyncScheduleInput,
    SyncScheduleListItem,
    SyncScheduleResponse,
    SyncScheduleUpdate,
)
from service.sync_queue import SyncJob, get_sync_queue
from service.sync_scheduler import get_sync_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasources", tags=["sync-schedules"])


# ------------------------------------------------------------------
# List all schedules
# ------------------------------------------------------------------


@router.get("/schedules", response_model=List[SyncScheduleListItem])
async def list_all_schedules():
    """Return every sync schedule across all datasources."""
    rows = await ScheduleDBManager.list_all()
    return [
        SyncScheduleListItem(
            id=r["id"],
            datasource_id=r["datasource_id"],
            datasource_name=r.get("datasource_name"),
            cron_expression=r["cron_expression"],
            preset=r["preset"],
            enabled=r["enabled"],
            update_graph_rag=r["update_graph_rag"],
            next_run_at=r.get("next_run_at"),
            last_run_status=r.get("last_run_status"),
        )
        for r in rows
    ]


# ------------------------------------------------------------------
# Per-datasource schedule CRUD
# ------------------------------------------------------------------


@router.post("/{datasource_id}/schedule", response_model=SyncScheduleResponse)
async def create_schedule(datasource_id: str, body: SyncScheduleInput):
    """Create a sync schedule for a datasource.

    If *preset* is not ``custom`` the server resolves the cron expression.
    """
    # Check if schedule already exists
    existing = await ScheduleDBManager.get_by_datasource(datasource_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Schedule already exists for this datasource. Use PUT to update.",
        )

    # Resolve preset → cron
    cron_expr = body.cron_expression
    if body.preset != SchedulePreset.CUSTOM:
        cron_expr = PRESET_CRON_MAP.get(body.preset, cron_expr)

    row = await ScheduleDBManager.create(
        datasource_id=datasource_id,
        cron_expression=cron_expr,
        preset=body.preset,
        enabled=body.enabled,
        update_graph_rag=body.update_graph_rag,
        tz=body.timezone,
    )

    # Register with APScheduler at runtime
    if body.enabled:
        get_sync_scheduler().add_job(row)

    return _row_to_response(row)


@router.get("/{datasource_id}/schedule", response_model=SyncScheduleResponse)
async def get_schedule(datasource_id: str):
    """Get the sync schedule for a datasource."""
    row = await ScheduleDBManager.get_by_datasource(datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="No schedule found for this datasource")
    return _row_to_response(row)


@router.put("/{datasource_id}/schedule", response_model=SyncScheduleResponse)
async def update_schedule(datasource_id: str, body: SyncScheduleUpdate):
    """Update an existing sync schedule.

    Only supplied fields are changed. Cron expression is re-validated.
    """
    existing = await ScheduleDBManager.get_by_datasource(datasource_id)
    if not existing:
        raise HTTPException(status_code=404, detail="No schedule found for this datasource")

    # Resolve preset → cron if needed
    cron_expr = body.cron_expression
    if body.preset and body.preset != SchedulePreset.CUSTOM:
        cron_expr = PRESET_CRON_MAP.get(body.preset, cron_expr)

    updates: dict = {}
    if cron_expr is not None:
        updates["cron_expression"] = cron_expr
    if body.preset is not None:
        updates["preset"] = body.preset
    if body.enabled is not None:
        updates["enabled"] = body.enabled
    if body.update_graph_rag is not None:
        updates["update_graph_rag"] = body.update_graph_rag
    if body.timezone is not None:
        updates["timezone"] = body.timezone

    # Recompute next_run_at
    enabled = updates.get("enabled", existing["enabled"])
    final_cron = updates.get("cron_expression", existing["cron_expression"])
    final_tz = updates.get("timezone", existing.get("timezone", "UTC"))
    if enabled:
        updates["next_run_at"] = ScheduleDBManager.compute_next_run(final_cron, final_tz)
    else:
        updates["next_run_at"] = None

    row = await ScheduleDBManager.update(datasource_id, **updates)
    if not row:
        raise HTTPException(status_code=500, detail="Failed to update schedule")

    # Update APScheduler
    get_sync_scheduler().update_job(row)

    return _row_to_response(row)


@router.delete("/{datasource_id}/schedule")
async def delete_schedule(datasource_id: str):
    """Remove the sync schedule for a datasource."""
    deleted = await ScheduleDBManager.delete(datasource_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No schedule found for this datasource")

    # Remove from APScheduler
    get_sync_scheduler().remove_job(datasource_id)

    return {"status": "deleted", "datasource_id": datasource_id}


# ------------------------------------------------------------------
# Enhanced status (extends existing /status with schedule info)
# ------------------------------------------------------------------


@router.get("/{datasource_id}/schedule/status", response_model=ScheduleRunStatus)
async def get_schedule_run_status(datasource_id: str):
    """Get combined sync + schedule status for real-time UI updates."""
    from service.store import get_store
    from psycopg.rows import dict_row
    import json

    store = get_store()
    if not store or not store.pool:
        raise HTTPException(status_code=503, detail="Database not initialized")

    # Fetch current sync status from cmetadata
    async with store.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT cmetadata FROM langchain_pg_collection WHERE uuid = %s",
                (datasource_id,),
            )
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="DataSource not found")
            meta = row.get("cmetadata", {})

    # Fetch schedule info
    schedule = await ScheduleDBManager.get_by_datasource(datasource_id)

    # Queue position
    queue = get_sync_queue()
    queue_pos = queue.get_queue_position(datasource_id)

    return ScheduleRunStatus(
        datasource_id=datasource_id,
        sync_status=meta.get("sync_status", "idle"),
        sync_progress=meta.get("sync_progress", 0),
        queue_position=queue_pos,
        scheduled=schedule is not None and schedule.get("enabled", False),
        next_run_at=schedule.get("next_run_at") if schedule else None,
        last_run_at=schedule.get("last_run_at") if schedule else None,
        last_run_status=schedule.get("last_run_status") if schedule else None,
        update_graph_rag=schedule.get("update_graph_rag", False) if schedule else False,
        graph_update_status=meta.get("graph_update_status"),
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _row_to_response(row: dict) -> SyncScheduleResponse:
    return SyncScheduleResponse(
        id=row["id"],
        datasource_id=row["datasource_id"],
        cron_expression=row["cron_expression"],
        preset=row["preset"],
        enabled=row["enabled"],
        update_graph_rag=row["update_graph_rag"],
        timezone=row.get("timezone", "UTC"),
        next_run_at=row.get("next_run_at"),
        last_run_at=row.get("last_run_at"),
        last_run_status=row.get("last_run_status"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
