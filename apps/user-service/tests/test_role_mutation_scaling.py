"""Platform role changes avoid per-user directory scans and unbounded logouts."""

import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from error_contract import DependencyUnavailableError

from src.repository.user_role_repository import UserRoleRepository
from src.service.role_service import CompositeRoleService


async def test_role_member_ids_use_one_pooled_filtered_effective_index(monkeypatch):
    identities = [str(uuid.UUID(int=i + 1)) for i in range(100000)]
    index = {identity: {"enduser"} for identity in identities}
    # Bulk index contains direct, secondary, and group-inherited assignments alike.
    for identity in identities[:3]:
        index[identity].add("administrator")
    entered = []

    class Admin:
        @asynccontextmanager
        async def admin_request_scope(self):
            entered.append(True)
            yield

    directory = SimpleNamespace(keycloak=Admin(), _build_role_index=AsyncMock(return_value=index))
    monkeypatch.setattr("src.repository.user_repository.UserRepository", lambda: directory)
    repo = UserRoleRepository()
    repo.client = SimpleNamespace(pages=AsyncMock(side_effect=AssertionError("Per-user scan")))
    assert await repo.list_user_ids_by_role("administrator") == [
        uuid.UUID(value) for value in identities[:3]
    ]
    directory._build_role_index.assert_awaited_once_with(role_name="administrator")
    assert entered == [True]


async def test_role_session_revocation_logs_out_projected_subjects_without_profiles(
    monkeypatch,
):
    monkeypatch.setattr("src.repository.UserRepository", lambda: pytest.fail("Profile hydration"))
    service = CompositeRoleService()
    ids = [uuid.uuid4(), uuid.uuid4()]
    service.user_role_repo = SimpleNamespace(list_user_ids_by_role=AsyncMock(return_value=ids))
    logout = AsyncMock(return_value=True)
    service.keycloak = SimpleNamespace(is_enabled=lambda: True, logout_user_sessions=logout)

    assert await service._invalidate_sessions_for_role_users("administrator") == 2
    assert [c.args for c in logout.await_args_list] == [(str(identity),) for identity in ids]


@pytest.mark.parametrize("failed", [False, True])
async def test_role_session_revocation_uses_bounded_waves_and_reports_failure(failed):
    service = CompositeRoleService()
    ids = [uuid.UUID(int=i + 1) for i in range(21)]
    service.user_role_repo = SimpleNamespace(list_user_ids_by_role=AsyncMock(return_value=ids))
    active = peak = calls = 0

    async def logout(subject):
        nonlocal active, peak, calls
        calls += 1
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return not (failed and subject == str(uuid.UUID(int=3)))

    service.keycloak = SimpleNamespace(is_enabled=lambda: True, logout_user_sessions=logout)
    if failed:
        with pytest.raises(DependencyUnavailableError):
            await service._invalidate_sessions_for_role_users("administrator")
        assert calls == 8
    else:
        assert await service._invalidate_sessions_for_role_users("administrator") == 21
        assert calls == 21
    assert peak == 8 and active == 0
