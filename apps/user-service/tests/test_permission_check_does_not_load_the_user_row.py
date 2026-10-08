"""A permission check asks whether the user exists, not for the whole row.

Every permission-gated request ran ``UserRepository.get_by_id`` -- a full
``SELECT *`` of the users table -- purely to decide whether to raise 401,
and then threw the row away: the only field it used, ``user.id``, is the
UUID it had already parsed out of the token. An existence check carries no
PII into the process and answers exactly the question being asked.
"""

from __future__ import annotations

import uuid

from error_contract import UnauthorizedError
import pytest

from src.api import dependencies


class _Repo:
    """Fails the test if anything asks it for a full user row."""

    instances: list[_Repo] = []

    def __init__(self) -> None:
        self.existence_checks: list[uuid.UUID] = []
        _Repo.instances.append(self)

    async def get_by_id(self, user_id: uuid.UUID):
        raise AssertionError("a permission check loaded the whole user row")

    async def exists_by_id(self, user_id: uuid.UUID) -> bool:
        self.existence_checks.append(user_id)
        return True


class _MissingRepo(_Repo):
    async def exists_by_id(self, user_id: uuid.UUID) -> bool:
        self.existence_checks.append(user_id)
        return False


class _Resolver:
    def __init__(self, permissions: set[str]) -> None:
        self._permissions = permissions

    async def resolve_effective_permissions(self, user_id: uuid.UUID) -> set[str]:
        return self._permissions


USER_ID = str(uuid.uuid4())


def _request():
    from types import SimpleNamespace

    return SimpleNamespace(client=None, headers={}, state=SimpleNamespace())


@pytest.fixture(autouse=True)
def _reset() -> None:
    _Repo.instances.clear()
    yield
    _Repo.instances.clear()


@pytest.fixture
def allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.repository.UserRepository", _Repo)
    monkeypatch.setattr(
        dependencies,
        "get_permission_resolver_service",
        lambda: _Resolver({"user:list"}),
    )


@pytest.mark.asyncio
async def test_require_permission_only_checks_existence(allowed):
    check = dependencies.require_permission("user:list")

    assert await check(_request(), USER_ID) == USER_ID
    assert _Repo.instances[0].existence_checks == [uuid.UUID(USER_ID)]


@pytest.mark.asyncio
async def test_an_unknown_user_is_still_rejected(monkeypatch):
    monkeypatch.setattr("src.repository.UserRepository", _MissingRepo)
    monkeypatch.setattr(dependencies, "get_permission_resolver_service", lambda: _Resolver({"*"}))

    check = dependencies.require_permission("user:list")
    with pytest.raises(UnauthorizedError) as exc:
        await check(_request(), USER_ID)

    assert exc.value.status_code == 401
