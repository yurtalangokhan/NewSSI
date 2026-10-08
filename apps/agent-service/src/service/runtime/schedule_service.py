"""Schedule service.

Business logic for datasource sync schedules. A schedule is a row of
``sync_schedules``: a cron expression and a timezone. The connector scheduler
(``service.ingest.connector_runtime``) polls that table and starts a sync when
``next_run_at`` has passed; this service owns the definition and keeps
``next_run_at`` in step with it.

The API keeps accepting Quartz-style six-field expressions (seconds first,
``?`` allowed); they are evaluated in their five-field crontab form.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from error_contract import BadRequestError, ConflictError, NotFoundError

from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import (
    datasource_connection_repository,
    datasource_repository,
    schedule_repository,
)
from schemas.schedules import (
    PRESET_CRON_MAP,
    SchedulePreset,
    ScheduleRunStatus,
    SyncScheduleInput,
    SyncScheduleListItem,
    SyncScheduleResponse,
    SyncScheduleUpdate,
)
from service.common.base import BaseService
from service.ingest.connector_runtime import get_connector_runtime

if TYPE_CHECKING:
    from service.ingest.connector_runtime import ConnectorRuntime

logger = get_logger(__name__)


class ScheduleService(BaseService):
    """Service layer for sync schedule business logic."""

    def __init__(self, runtime: ConnectorRuntime | None = None) -> None:
        self._runtime_override = runtime

    @property
    def _runtime(self) -> ConnectorRuntime:
        return self._runtime_override or get_connector_runtime()

    # ---- helpers ---------------------------------------------------------

    def _compute_next_run(self, cron_expr: str, tz_name: str = "UTC") -> str | None:
        """Next fire-time as a UTC ISO string, or ``None`` for an unparseable expression."""
        return schedule_repository().next_run_iso(cron_expr, tz_name)

    @staticmethod
    def _next_run_or_reject(cron_expr: str, tz_name: str) -> datetime:
        try:
            return schedule_repository().compute_next_run(cron_expr, tz_name)
        except Exception as exc:
            raise BadRequestError(message=f"Invalid cron expression or timezone: {exc}") from exc

    async def _require_connection(self, datasource_id: str) -> dict[str, Any]:
        connection = await datasource_connection_repository().get(datasource_id)
        if not connection:
            self._raise_not_found("datasource.no_connection")
        return connection

    async def get_last_job_info(self, datasource_id: str) -> tuple[str | None, str | None]:
        """The most recent sync job of a datasource: ``(updated_at, status)``."""
        try:
            job = await self._runtime.latest_job(datasource_id)
        except Exception:
            logger.debug("Could not fetch the last job of datasource %s", datasource_id)
            return None, None
        if job is None:
            return None, None
        stamp = job.finished_at or job.heartbeat_at or job.created_at
        return stamp.astimezone(UTC).isoformat().replace("+00:00", "Z"), job.status.value

    async def _build_response(self, schedule: dict[str, Any], connection: dict[str, Any]) -> SyncScheduleResponse:
        last_run_at, last_run_status = await self.get_last_job_info(schedule["datasource_id"])
        return SyncScheduleResponse(
            id=schedule["datasource_id"],
            datasource_id=schedule["datasource_id"],
            cron_expression=schedule["cron_expression"],
            preset=schedule.get("preset") or "custom",
            enabled=bool(schedule.get("enabled")),
            update_graph_rag=bool(connection.get("update_graph_rag")),
            timezone=schedule.get("timezone") or "UTC",
            next_run_at=schedule.get("next_run_at") if schedule.get("enabled") else None,
            last_run_at=last_run_at,
            last_run_status=last_run_status,
            created_at=schedule.get("created_at") or "",
            updated_at=schedule.get("updated_at") or "",
        )

    # ---- operations ------------------------------------------------------

    async def list_all_schedules(self) -> list[SyncScheduleListItem]:
        schedules = [s for s in await schedule_repository().list_all() if s.get("enabled")]
        if not schedules:
            return []
        connections = {c["datasource_id"]: c for c in await datasource_connection_repository().list_all()}

        items: list[SyncScheduleListItem] = []
        for schedule in schedules:
            datasource_id = schedule["datasource_id"]
            _last_run_at, last_run_status = await self.get_last_job_info(datasource_id)
            items.append(
                SyncScheduleListItem(
                    id=datasource_id,
                    datasource_id=datasource_id,
                    cron_expression=schedule["cron_expression"],
                    preset=schedule.get("preset") or "custom",
                    enabled=True,
                    update_graph_rag=bool(connections.get(datasource_id, {}).get("update_graph_rag")),
                    next_run_at=schedule.get("next_run_at"),
                    last_run_status=last_run_status,
                )
            )
        return items

    async def create_schedule(self, datasource_id: str, body: SyncScheduleInput) -> SyncScheduleResponse:
        await self._require_connection(datasource_id)
        repo = schedule_repository()

        existing = await repo.get_by_datasource(datasource_id)
        if existing and existing.get("enabled"):
            # Use PUT to change an existing schedule.
            raise ConflictError()

        cron_expr = body.cron_expression
        if body.preset != SchedulePreset.CUSTOM:
            cron_expr = PRESET_CRON_MAP.get(body.preset, cron_expr)
        if not cron_expr:
            raise BadRequestError(code="schedule.cron_required", message_key="errors.schedule.cron_required")
        next_run = self._next_run_or_reject(cron_expr, body.timezone)

        if existing:
            # A disabled definition is left behind by ``enabled: false``; reuse the row.
            await repo.update(
                datasource_id,
                cron_expression=cron_expr,
                preset=body.preset.value,
                enabled=body.enabled,
                timezone=body.timezone,
            )
        else:
            await repo.create(
                datasource_id,
                cron_expr,
                preset=body.preset.value,
                enabled=body.enabled,
                update_graph_rag=body.update_graph_rag,
                tz=body.timezone,
            )
        await repo.update_run_times(datasource_id, next_run_at=next_run if body.enabled else None)
        connection = await datasource_connection_repository().update(
            datasource_id, update_graph_rag=body.update_graph_rag
        )

        return await self._build_response(await repo.get_by_datasource(datasource_id), connection)

    async def get_schedule(self, datasource_id: str) -> SyncScheduleResponse:
        connection = await self._require_connection(datasource_id)
        schedule = await schedule_repository().get_by_datasource(datasource_id)
        if not schedule or not schedule.get("enabled"):
            raise NotFoundError()
        return await self._build_response(schedule, connection)

    async def update_schedule(self, datasource_id: str, body: SyncScheduleUpdate) -> SyncScheduleResponse:
        connection = await self._require_connection(datasource_id)
        repo = schedule_repository()
        current = await repo.get_by_datasource(datasource_id)

        cron_expr = body.cron_expression
        if body.preset and body.preset != SchedulePreset.CUSTOM:
            cron_expr = PRESET_CRON_MAP.get(body.preset, cron_expr)

        # A body without ``enabled`` leaves the switch as it is: a new cron or graph
        # flag on a disabled schedule must not arm it. A schedule that does not
        # exist yet is created enabled, as before.
        enabled = body.enabled if body.enabled is not None else (current is None or bool(current.get("enabled")))
        final_cron = cron_expr or (current or {}).get("cron_expression") or "0 0 0 * * ?"
        final_tz = body.timezone or (current or {}).get("timezone") or "UTC"
        # The definition is validated even while disabled: it is what ``enabled: true`` arms later.
        next_run = self._next_run_or_reject(final_cron, final_tz)
        preset = body.preset.value if body.preset else None
        if current:
            await repo.update(
                datasource_id,
                cron_expression=final_cron,
                timezone=final_tz,
                preset=preset,
                enabled=enabled,
            )
        else:
            await repo.create(datasource_id, final_cron, preset=preset or "custom", tz=final_tz, enabled=enabled)
        await repo.update_run_times(datasource_id, next_run_at=next_run if enabled else None)

        if body.update_graph_rag is not None:
            connection = await datasource_connection_repository().update(
                datasource_id, update_graph_rag=body.update_graph_rag
            )

        schedule = await repo.get_by_datasource(datasource_id)
        if not schedule:
            raise NotFoundError()
        return await self._build_response(schedule, connection)

    async def delete_schedule(self, datasource_id: str) -> dict[str, Any]:
        await self._require_connection(datasource_id)
        await schedule_repository().delete(datasource_id)
        return {"status": "deleted", "datasource_id": datasource_id}

    async def get_schedule_run_status(self, datasource_id: str) -> ScheduleRunStatus:
        row = await datasource_repository().get_collection(datasource_id)
        if not row:
            self._raise_not_found("datasource.not_found", datasource_id=datasource_id)
        meta = row.get("cmetadata", {}) or {}

        scheduled = False
        next_run = None
        update_graph = False
        last_run_at = last_run_status = None
        try:
            connection = await datasource_connection_repository().get(datasource_id)
            if connection:
                update_graph = bool(connection.get("update_graph_rag"))
                schedule = await schedule_repository().get_by_datasource(datasource_id)
                if schedule:
                    scheduled = bool(schedule.get("enabled"))
                    next_run = schedule.get("next_run_at") if scheduled else None
                last_run_at, last_run_status = await self.get_last_job_info(datasource_id)
        except Exception:
            logger.debug("Could not fetch schedule status for %s", datasource_id, exc_info=True)

        return ScheduleRunStatus(
            datasource_id=datasource_id,
            sync_status=meta.get("sync_status", "idle"),
            sync_progress=meta.get("sync_progress", 0),
            queue_position=await self._runtime.queue_position(datasource_id),
            scheduled=scheduled,
            next_run_at=next_run,
            last_run_at=last_run_at,
            last_run_status=last_run_status,
            update_graph_rag=update_graph,
            graph_update_status=meta.get("graph_update_status"),
        )


# Singleton instance
_schedule_service: ScheduleService | None = None


def get_schedule_service() -> ScheduleService:
    """Get the singleton ScheduleService instance."""
    global _schedule_service
    if _schedule_service is None:
        _schedule_service = ScheduleService()
    return _schedule_service
