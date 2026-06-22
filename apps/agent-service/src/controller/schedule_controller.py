"""Schedule controller - handles sync schedule CRUD operations."""

from typing import Any

from controller.base import BaseController
from service.ScheduleModels import (
    ScheduleRunStatus,
    SyncScheduleInput,
    SyncScheduleListItem,
    SyncScheduleResponse,
    SyncScheduleUpdate,
)
from service.ScheduleService import ScheduleService


class ScheduleController(BaseController):
    """Controller for sync schedule management."""

    def __init__(self):
        self._service = ScheduleService()

    async def list_all_schedules(self) -> list[SyncScheduleListItem]:
        try:
            return await self._service.list_all_schedules()
        except Exception as exc:
            self._raise_internal_error(str(exc))

    async def create_schedule(self, datasource_id: str, body: SyncScheduleInput) -> SyncScheduleResponse:
        if not datasource_id:
            self._raise_bad_request("datasource_id is required")
        try:
            return await self._service.create_schedule(datasource_id, body)
        except LookupError as exc:
            self._raise_not_found(str(exc))
        except ValueError as exc:
            self._raise_bad_request(str(exc))
        except Exception as exc:
            self._raise_internal_error(str(exc))

    async def get_schedule(self, datasource_id: str) -> SyncScheduleResponse:
        if not datasource_id:
            self._raise_bad_request("datasource_id is required")
        try:
            return await self._service.get_schedule(datasource_id)
        except LookupError as exc:
            self._raise_not_found(str(exc))
        except Exception as exc:
            self._raise_internal_error(str(exc))

    async def update_schedule(self, datasource_id: str, body: SyncScheduleUpdate) -> SyncScheduleResponse:
        if not datasource_id:
            self._raise_bad_request("datasource_id is required")
        try:
            return await self._service.update_schedule(datasource_id, body)
        except LookupError as exc:
            self._raise_not_found(str(exc))
        except ValueError as exc:
            self._raise_bad_request(str(exc))
        except Exception as exc:
            self._raise_internal_error(str(exc))

    async def delete_schedule(self, datasource_id: str) -> dict[str, Any]:
        if not datasource_id:
            self._raise_bad_request("datasource_id is required")
        try:
            return await self._service.delete_schedule(datasource_id)
        except LookupError as exc:
            self._raise_not_found(str(exc))
        except Exception as exc:
            self._raise_internal_error(str(exc))

    async def get_schedule_run_status(self, datasource_id: str) -> ScheduleRunStatus:
        if not datasource_id:
            self._raise_bad_request("datasource_id is required")
        try:
            return await self._service.get_schedule_run_status(datasource_id)
        except LookupError as exc:
            self._raise_not_found(str(exc))
        except Exception as exc:
            self._raise_internal_error(str(exc))


# Singleton instance
_schedule_controller: ScheduleController | None = None


def get_schedule_controller() -> ScheduleController:
    """Get the singleton ScheduleController instance."""
    global _schedule_controller
    if _schedule_controller is None:
        _schedule_controller = ScheduleController()
    return _schedule_controller
