"""Compatibility sync must never mutate identities or delete application data."""

from unittest.mock import AsyncMock

import pytest

from src.service.user_service import UserService


@pytest.mark.parametrize("users", [[], [object()], [object()] * 10001])
async def test_sync_reports_authoritative_directory_without_orphan_mutations(users):
    service = UserService.__new__(UserService)
    service.user_repo = AsyncMock()
    service.user_repo.get_all.return_value = users

    report = await service.sync_users_from_keycloak()

    assert report["keycloak_users_synced"] == len(users)
    assert report["orphaned_users_deleted"] == 0
    service.user_repo.get_all.assert_awaited_once()
    service.user_repo.update.assert_not_awaited()
    service.user_repo.delete.assert_not_awaited()


async def test_failed_directory_read_propagates_without_mutations():
    service = UserService.__new__(UserService)
    service.user_repo = AsyncMock()
    service.user_repo.get_all.side_effect = ConnectionError("keycloak unreachable")

    with pytest.raises(ConnectionError, match="keycloak unreachable"):
        await service.sync_users_from_keycloak()

    service.user_repo.update.assert_not_awaited()
    service.user_repo.delete.assert_not_awaited()
