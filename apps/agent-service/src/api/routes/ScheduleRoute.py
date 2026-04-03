"""
Sync Schedule API Routes.

CRUD endpoints for managing sync schedules via Airbyte native connection
scheduling.  Replaces the old APScheduler + sync_schedules approach.
"""

from __future__ import annotations

import logging
from datetime import datetime

from croniter import croniter
from fastapi import APIRouter, HTTPException

from service.AirbyteApiClientService import get_airbyte_client
from service.AirbyteMappingRepository import AirbyteMappingDB
from service.ScheduleModels import (
    PRESET_CRON_MAP,
    SchedulePreset,
    ScheduleRunStatus,
    SyncScheduleInput,
    SyncScheduleListItem,
    SyncScheduleResponse,
    SyncScheduleUpdate,
)
from service.SyncQueueService import get_sync_queue

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync-schedules"])


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _quartz_to_unix(cron_expr: str) -> str:
    """Convert 6-field Quartz cron to 5-field unix cron for croniter."""
    parts = cron_expr.strip().split()
    if len(parts) == 6:
        return " ".join(p.replace("?", "*") for p in parts[1:])
    return cron_expr


def _compute_next_run(cron_expr: str, tz_name: str = "UTC") -> str | None:
    """Compute next run time from a Quartz cron expression using croniter."""
    try:
        import zoneinfo

        tz = zoneinfo.ZoneInfo(tz_name)
        base = datetime.now(tz)
        # croniter only supports 5-field unix cron
        cron_5 = _quartz_to_unix(cron_expr)
        cron = croniter(cron_5, base)
        return cron.get_next(datetime).isoformat()
    except Exception:
        return None


async def _get_last_job_info(connection_id: str) -> tuple[str | None, str | None]:
    """Fetch the most recent completed/failed sync job for a connection.

    Returns ``(last_run_at_iso, last_run_status)``.
    Airbyte job timestamps are Unix epoch seconds.
    """
    try:
        client = get_airbyte_client()
        jobs = await client.list_jobs(connection_id, limit=1)
        if jobs:
            job = jobs[0].get("job", jobs[0])
            status = job.get("status", "")
            updated_at = job.get("updatedAt") or job.get("createdAt")
            if updated_at is not None:
                ts = datetime.utcfromtimestamp(int(updated_at)).isoformat() + "Z"
                return ts, status
    except Exception:
        logger.debug("Could not fetch last job for connection %s", connection_id)
    return None, None


async def _get_connection_schedule(mapping: dict) -> dict:
    """Fetch schedule info from Airbyte connection.

    Returns the cron expression in its native Quartz 6-field format,
    together with last_run_at / last_run_status from the most recent job.
    """
    client = get_airbyte_client()
    conn_id = mapping["airbyte_connection_id"]
    conn_data = await client.get_connection(conn_id)

    sched = conn_data.get("scheduleData", {})
    cron_data = sched.get("cron", {})
    schedule_type = conn_data.get("scheduleType", "manual")

    cron_expr = cron_data.get("cronExpression", "")
    tz = cron_data.get("cronTimeZone", "UTC")
    # enabled = connection has a cron schedule (status=active means the connection
    # itself is active, not that scheduling is on; scheduleType is the real indicator)
    enabled = schedule_type == "cron"

    last_run_at, last_run_status = await _get_last_job_info(conn_id)

    return {
        "cron_expression": cron_expr,
        "timezone": tz,
        "enabled": enabled,
        "update_graph_rag": mapping.get("update_graph_rag", False),
        "schedule_type": schedule_type,
        "last_run_at": last_run_at,
        "last_run_status": last_run_status,
    }


def _build_response(
    mapping: dict,
    sched_info: dict,
) -> SyncScheduleResponse:
    """Build SyncScheduleResponse from mapping + schedule info."""
    cron_expr = sched_info.get("cron_expression", "")
    tz = sched_info.get("timezone", "UTC")

    return SyncScheduleResponse(
        id=mapping["datasource_id"],  # use datasource_id as schedule id
        datasource_id=mapping["datasource_id"],
        cron_expression=cron_expr,
        preset="custom",
        enabled=sched_info.get("enabled", False),
        update_graph_rag=sched_info.get("update_graph_rag", False),
        timezone=tz,
        next_run_at=_compute_next_run(cron_expr, tz) if cron_expr else None,
        last_run_at=sched_info.get("last_run_at"),
        last_run_status=sched_info.get("last_run_status"),
        created_at=mapping.get("created_at", ""),
        updated_at=mapping.get("updated_at", ""),
    )


# ------------------------------------------------------------------
# List all schedules
# ------------------------------------------------------------------


@router.get("/datasources/schedules", response_model=list[SyncScheduleListItem])
async def list_all_schedules():
    """Return every sync schedule across all datasources."""
    mappings = await AirbyteMappingDB.list_all()
    if not mappings:
        return []

    items: list[SyncScheduleListItem] = []
    for mapping in mappings:
        try:
            sched_info = await _get_connection_schedule(mapping)
            if sched_info.get("schedule_type") != "cron":
                continue  # skip non-scheduled connections

            cron_expr = sched_info.get("cron_expression", "")
            tz = sched_info.get("timezone", "UTC")

            items.append(
                SyncScheduleListItem(
                    id=mapping["datasource_id"],
                    datasource_id=mapping["datasource_id"],
                    cron_expression=cron_expr,
                    preset="custom",
                    enabled=sched_info.get("enabled", False),
                    update_graph_rag=sched_info.get("update_graph_rag", False),
                    next_run_at=_compute_next_run(cron_expr, tz),
                    last_run_status=sched_info.get("last_run_status"),
                )
            )
        except Exception:
            logger.warning("Could not fetch schedule for %s", mapping["datasource_id"])

    return items


# ------------------------------------------------------------------
# Per-datasource schedule CRUD
# ------------------------------------------------------------------


@router.post("/{datasource_id}/schedule", response_model=SyncScheduleResponse)
async def create_schedule(datasource_id: str, body: SyncScheduleInput):
    """Create a sync schedule by setting cron on the Airbyte connection."""
    mapping = await AirbyteMappingDB.get(datasource_id)
    if not mapping:
        raise HTTPException(
            status_code=404,
            detail="No Airbyte mapping found for this datasource",
        )

    # Check if already scheduled
    try:
        sched_info = await _get_connection_schedule(mapping)
        if sched_info.get("schedule_type") == "cron":
            raise HTTPException(
                status_code=409,
                detail="Schedule already exists for this datasource. Use PUT to update.",
            )
    except HTTPException:
        raise
    except Exception:
        pass

    # Resolve preset → cron
    cron_expr = body.cron_expression
    if body.preset != SchedulePreset.CUSTOM:
        cron_expr = PRESET_CRON_MAP.get(body.preset, cron_expr)

    # Update Airbyte connection schedule
    client = get_airbyte_client()
    schedule = {
        "scheduleType": "cron",
        "scheduleData": {
            "cron": {
                "cronExpression": cron_expr,
                "cronTimeZone": body.timezone,
            }
        },
    }
    await client.update_connection_schedule(mapping["airbyte_connection_id"], schedule)

    # Store update_graph_rag preference
    await AirbyteMappingDB.update(datasource_id, update_graph_rag=body.update_graph_rag)

    # Refresh mapping
    mapping = await AirbyteMappingDB.get(datasource_id)
    sched_info = await _get_connection_schedule(mapping)

    return _build_response(mapping, sched_info)


@router.get("/{datasource_id}/schedule", response_model=SyncScheduleResponse)
async def get_schedule(datasource_id: str):
    """Get the sync schedule for a datasource."""
    mapping = await AirbyteMappingDB.get(datasource_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="No Airbyte mapping found")

    sched_info = await _get_connection_schedule(mapping)
    if sched_info.get("schedule_type") != "cron":
        raise HTTPException(status_code=404, detail="No schedule found for this datasource")

    return _build_response(mapping, sched_info)


@router.put("/{datasource_id}/schedule", response_model=SyncScheduleResponse)
async def update_schedule(datasource_id: str, body: SyncScheduleUpdate):
    """Update an existing sync schedule."""
    mapping = await AirbyteMappingDB.get(datasource_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="No Airbyte mapping found")

    # Resolve preset → cron if needed
    cron_expr = body.cron_expression
    if body.preset and body.preset != SchedulePreset.CUSTOM:
        cron_expr = PRESET_CRON_MAP.get(body.preset, cron_expr)

    client = get_airbyte_client()

    if body.enabled is False:
        # Disable schedule → set to manual
        await client.update_connection_schedule(mapping["airbyte_connection_id"], None)
    else:
        # Get current schedule to fill in missing fields
        current = await _get_connection_schedule(mapping)
        final_cron = cron_expr or current.get("cron_expression", "0 0 0 * * ?")
        final_tz = body.timezone or current.get("timezone", "UTC")

        schedule = {
            "scheduleType": "cron",
            "scheduleData": {
                "cron": {
                    "cronExpression": final_cron,
                    "cronTimeZone": final_tz,
                }
            },
        }
        await client.update_connection_schedule(mapping["airbyte_connection_id"], schedule)

    # Update graph RAG preference
    if body.update_graph_rag is not None:
        await AirbyteMappingDB.update(datasource_id, update_graph_rag=body.update_graph_rag)

    mapping = await AirbyteMappingDB.get(datasource_id)
    sched_info = await _get_connection_schedule(mapping)
    return _build_response(mapping, sched_info)


@router.delete("/{datasource_id}/schedule")
async def delete_schedule(datasource_id: str):
    """Remove the sync schedule (set Airbyte connection to manual)."""
    mapping = await AirbyteMappingDB.get(datasource_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="No Airbyte mapping found")

    client = get_airbyte_client()
    await client.update_connection_schedule(mapping["airbyte_connection_id"], None)

    return {"status": "deleted", "datasource_id": datasource_id}


# ------------------------------------------------------------------
# Enhanced status
# ------------------------------------------------------------------


@router.get("/{datasource_id}/schedule/status", response_model=ScheduleRunStatus)
async def get_schedule_run_status(datasource_id: str):
    """Get combined sync + schedule status for real-time UI updates."""
    from core.db import DatasourceRepository

    ds_repo = DatasourceRepository()

    # Fetch current sync status from cmetadata
    row = await ds_repo.get_collection(datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="DataSource not found")
    meta = row.get("cmetadata", {})

    # Fetch schedule info
    mapping = await AirbyteMappingDB.get(datasource_id)
    scheduled = False
    next_run = None
    update_graph = False
    last_run_at = None
    last_run_status = None

    if mapping:
        try:
            sched_info = await _get_connection_schedule(mapping)
            scheduled = sched_info.get("enabled", False)
            cron_expr = sched_info.get("cron_expression", "")
            tz = sched_info.get("timezone", "UTC")
            next_run = _compute_next_run(cron_expr, tz) if cron_expr else None
            update_graph = sched_info.get("update_graph_rag", False)
            last_run_at = sched_info.get("last_run_at")
            last_run_status = sched_info.get("last_run_status")
        except Exception:
            pass

    # Queue position
    queue = get_sync_queue()
    queue_pos = queue.get_queue_position(datasource_id)

    return ScheduleRunStatus(
        datasource_id=datasource_id,
        sync_status=meta.get("sync_status", "idle"),
        sync_progress=meta.get("sync_progress", 0),
        queue_position=queue_pos,
        scheduled=scheduled,
        next_run_at=next_run,
        last_run_at=last_run_at,
        last_run_status=last_run_status,
        update_graph_rag=update_graph,
        graph_update_status=meta.get("graph_update_status"),
    )
