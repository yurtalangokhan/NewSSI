from unittest.mock import AsyncMock, Mock

from error_contract import ConflictError, DependencyTimeoutError, DependencyUnavailableError
import httpx
import pytest

from schemas.schedules import SyncScheduleInput
from service.auth.permission_service import PermissionService
from service.datasources import datasource_application_service
from service.runtime import schedule_application_service
from service.runtime.schedule_service import ScheduleService


@pytest.mark.asyncio
async def test_permission_outage_is_not_an_authorization_denial(monkeypatch):
    monkeypatch.setattr(
        "service.auth.permission_service.outbound.request",
        AsyncMock(side_effect=httpx.ReadTimeout("private upstream")),
    )
    with pytest.raises(DependencyTimeoutError):
        await PermissionService().check_agent_access("user", "agent")


@pytest.mark.asyncio
async def test_duplicate_schedule_is_not_swallowed(monkeypatch):
    connection_repo = Mock()
    connection_repo.get = AsyncMock(return_value={"datasource_id": "datasource", "update_graph_rag": False})
    schedule_repo = Mock()
    schedule_repo.get_by_datasource = AsyncMock(return_value={"datasource_id": "datasource", "enabled": True})
    monkeypatch.setattr(
        "service.runtime.schedule_service.datasource_connection_repository", lambda: connection_repo
    )
    monkeypatch.setattr("service.runtime.schedule_service.schedule_repository", lambda: schedule_repo)
    with pytest.raises(ConflictError):
        await ScheduleService().create_schedule("datasource", SyncScheduleInput(cron_expression="* * * * *"))


@pytest.mark.asyncio
async def test_source_outage_is_normalized_by_datasource_application_service(monkeypatch):
    service = AsyncMock()
    service.get_sync_history.side_effect = ConnectionError("private upstream")
    monkeypatch.setattr(datasource_application_service, "_get_service", lambda: service)
    with pytest.raises(DependencyUnavailableError) as exc_info:
        await datasource_application_service.get_sync_history("datasource")
    assert "private upstream" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_timeout_is_normalized_by_schedule_application_service(monkeypatch):
    service = AsyncMock()
    service.list_all_schedules.side_effect = TimeoutError("private upstream")
    monkeypatch.setattr(schedule_application_service, "_get_service", lambda: service)
    with pytest.raises(DependencyTimeoutError) as exc_info:
        await schedule_application_service.list_all_schedules()
    assert "private upstream" not in str(exc_info.value)
