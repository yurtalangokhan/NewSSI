"""Schedule service.

Holds business logic for Airbyte sync schedule management.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from croniter import croniter

from core.db import DatasourceRepository
from core.logger import get_logger
from models.schedules import (
    PRESET_CRON_MAP,
    SchedulePreset,
    ScheduleRunStatus,
    SyncScheduleInput,
    SyncScheduleListItem,
    SyncScheduleResponse,
    SyncScheduleUpdate,
)
from repository.airbyte_mapping_repository import AirbyteMappingDB
from service.AirbyteApiClientService import get_airbyte_client
from service.SyncQueueService import get_sync_queue

logger = get_logger(__name__)


class ScheduleService:
    """Service layer for sync schedule business logic."""

    def _quartz_to_unix(self, cron_expr: str) -> str:
        parts = cron_expr.strip().split()
        if len(parts) == 6:
            return " ".join(p.replace("?", "*") for p in parts[1:])
        return cron_expr

    def _compute_next_run(self, cron_expr: str, tz_name: str = "UTC") -> str | None:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(tz_name)
            base = datetime.now(tz)
            cron_5 = self._quartz_to_unix(cron_expr)
            cron = croniter(cron_5, base)
            return cron.get_next(datetime).isoformat()
        except Exception:
            return None

    async def _get_last_job_info(self, connection_id: str) -> tuple[str | None, str | None]:
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

    async def _get_connection_schedule(self, mapping: dict[str, Any]) -> dict[str, Any]:
        client = get_airbyte_client()
        conn_id = mapping["airbyte_connection_id"]
        conn_data = await client.get_connection(conn_id)

        sched = conn_data.get("scheduleData", {})
        cron_data = sched.get("cron", {})
        schedule_type = conn_data.get("scheduleType", "manual")

        cron_expr = cron_data.get("cronExpression", "")
        tz = cron_data.get("cronTimeZone", "UTC")
        enabled = schedule_type == "cron"

        last_run_at, last_run_status = await self._get_last_job_info(conn_id)

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
        self,
        mapping: dict[str, Any],
        sched_info: dict[str, Any],
    ) -> SyncScheduleResponse:
        cron_expr = sched_info.get("cron_expression", "")
        tz = sched_info.get("timezone", "UTC")

        return SyncScheduleResponse(
            id=mapping["datasource_id"],
            datasource_id=mapping["datasource_id"],
            cron_expression=cron_expr,
            preset="custom",
            enabled=sched_info.get("enabled", False),
            update_graph_rag=sched_info.get("update_graph_rag", False),
            timezone=tz,
            next_run_at=self._compute_next_run(cron_expr, tz) if cron_expr else None,
            last_run_at=sched_info.get("last_run_at"),
            last_run_status=sched_info.get("last_run_status"),
            created_at=mapping.get("created_at", ""),
            updated_at=mapping.get("updated_at", ""),
        )

    async def list_all_schedules(self) -> list[SyncScheduleListItem]:
        mappings = await AirbyteMappingDB.list_all()
        if not mappings:
            return []

        items: list[SyncScheduleListItem] = []
        for mapping in mappings:
            try:
                sched_info = await self._get_connection_schedule(mapping)
                if sched_info.get("schedule_type") != "cron":
                    continue

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
                        next_run_at=self._compute_next_run(cron_expr, tz),
                        last_run_status=sched_info.get("last_run_status"),
                    )
                )
            except Exception:
                logger.warning("Could not fetch schedule for %s", mapping["datasource_id"])

        return items

    async def create_schedule(
        self, datasource_id: str, body: SyncScheduleInput
    ) -> SyncScheduleResponse:
        mapping = await AirbyteMappingDB.get(datasource_id)
        if not mapping:
            raise LookupError("No Airbyte mapping found for this datasource")

        try:
            sched_info = await self._get_connection_schedule(mapping)
            if sched_info.get("schedule_type") == "cron":
                raise ValueError("Schedule already exists for this datasource. Use PUT to update.")
        except LookupError:
            raise
        except Exception:
            pass

        cron_expr = body.cron_expression
        if body.preset != SchedulePreset.CUSTOM:
            cron_expr = PRESET_CRON_MAP.get(body.preset, cron_expr)

        if not cron_expr:
            raise ValueError("cron_expression is required")

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

        await AirbyteMappingDB.update(datasource_id, update_graph_rag=body.update_graph_rag)
        mapping = await AirbyteMappingDB.get(datasource_id)
        sched_info = await self._get_connection_schedule(mapping)

        return self._build_response(mapping, sched_info)

    async def get_schedule(self, datasource_id: str) -> SyncScheduleResponse:
        mapping = await AirbyteMappingDB.get(datasource_id)
        if not mapping:
            raise LookupError("No Airbyte mapping found")

        sched_info = await self._get_connection_schedule(mapping)
        if sched_info.get("schedule_type") != "cron":
            raise LookupError("No schedule found for this datasource")

        return self._build_response(mapping, sched_info)

    async def update_schedule(
        self, datasource_id: str, body: SyncScheduleUpdate
    ) -> SyncScheduleResponse:
        mapping = await AirbyteMappingDB.get(datasource_id)
        if not mapping:
            raise LookupError("No Airbyte mapping found")

        cron_expr = body.cron_expression
        if body.preset and body.preset != SchedulePreset.CUSTOM:
            cron_expr = PRESET_CRON_MAP.get(body.preset, cron_expr)

        client = get_airbyte_client()

        if body.enabled is False:
            await client.update_connection_schedule(mapping["airbyte_connection_id"], None)
        else:
            current = await self._get_connection_schedule(mapping)
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

        if body.update_graph_rag is not None:
            await AirbyteMappingDB.update(datasource_id, update_graph_rag=body.update_graph_rag)

        mapping = await AirbyteMappingDB.get(datasource_id)
        sched_info = await self._get_connection_schedule(mapping)

        return self._build_response(mapping, sched_info)

    async def delete_schedule(self, datasource_id: str) -> dict[str, Any]:
        mapping = await AirbyteMappingDB.get(datasource_id)
        if not mapping:
            raise LookupError("No Airbyte mapping found")

        client = get_airbyte_client()
        await client.update_connection_schedule(mapping["airbyte_connection_id"], None)
        return {"status": "deleted", "datasource_id": datasource_id}

    async def get_schedule_run_status(self, datasource_id: str) -> ScheduleRunStatus:
        ds_repo = DatasourceRepository()
        row = await ds_repo.get_collection(datasource_id)
        if not row:
            raise LookupError("DataSource not found")

        meta = row.get("cmetadata", {}) or {}
        mapping = await AirbyteMappingDB.get(datasource_id)

        scheduled = False
        next_run = None
        last_run_at = None
        last_run_status = None
        update_graph = False

        if mapping:
            try:
                sched_info = await self._get_connection_schedule(mapping)
                scheduled = sched_info.get("enabled", False)
                next_run = self._compute_next_run(
                    sched_info.get("cron_expression", ""), sched_info.get("timezone", "UTC")
                )
                update_graph = sched_info.get("update_graph_rag", False)
                last_run_at = sched_info.get("last_run_at")
                last_run_status = sched_info.get("last_run_status")
            except Exception:
                pass

        queue = get_sync_queue()
        queue_pos = queue.get_queue_position(datasource_id) if queue else 0

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
