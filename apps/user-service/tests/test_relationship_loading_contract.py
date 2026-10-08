"""Application permission rows serialize without SQL identity relationships.

Display identities come from Keycloak repositories after SQL serialization.
The guarded row fails if code accidentally accesses removed relationships.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import InvalidRequestError

from src.repository.resource_permission_repository import ResourcePermissionRepository

RELATIONSHIP_NAMES = ("organization", "user")


def _relationships_in(options) -> set[str]:
    """The relationships a set of loader options eagerly loads."""
    requested: set[str] = set()
    for option in options or ():
        rendered = str(getattr(option, "path", ""))
        for name in RELATIONSHIP_NAMES:
            if f".{name} " in rendered or rendered.endswith(f".{name}"):
                requested.add(name)
    return requested


def _requested_relationships(statement) -> set[str]:
    """The relationships a statement's loader options eagerly load."""
    return _relationships_in(getattr(statement, "_with_options", ()))


class _Related:
    def __init__(self, name: str) -> None:
        self.id = uuid.uuid4()
        self.name = name
        self.code = name
        self.level = 1
        self.email = f"{name}@example.com"
        self.first_name = name
        self.last_name = "User"
        self.username = name
        self.role = "enduser"


class _Row:
    """A mapped row that refuses unloaded relationship access, as lazy='raise' does."""

    def __init__(self, **columns: object) -> None:
        self.__dict__.update(columns)
        self.__dict__["_loaded"] = set()

    def load(self, names: set[str]) -> _Row:
        self.__dict__["_loaded"] |= set(names)
        return self

    def __getattr__(self, item: str):
        if item in RELATIONSHIP_NAMES:
            if item not in self.__dict__["_loaded"]:
                raise InvalidRequestError(
                    f"'{type(self).__name__}.{item}' is not available due to lazy='raise'"
                )
            return _Related(item)
        raise AttributeError(item)


class _Result:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[_Row]:
        return list(self._rows)

    def first(self) -> _Row | None:
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self) -> _Row | None:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> int:
        return len(self._rows)

    @property
    def rowcount(self) -> int:
        return len(self._rows)


class _ContractSession:
    """Loads relationships only when the statement asked for them."""

    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows
        self.added: list[object] = []
        self.refreshed: list[set[str]] = []

    async def execute(self, statement, *args, **kwargs) -> _Result:
        requested = _requested_relationships(statement)
        return _Result([row.load(requested) for row in self._rows])

    async def get(self, _model, _pk, options=None):
        if not self._rows:
            return None
        return self._rows[0].load(_relationships_in(options))

    async def refresh(self, instance, attribute_names=None) -> None:
        self.refreshed.append(set(attribute_names or ()))
        if attribute_names and isinstance(instance, _Row):
            instance.load({name for name in attribute_names if name in RELATIONSHIP_NAMES})

    def add(self, instance) -> None:
        self.added.append(instance)
        self._rows.append(instance) if isinstance(instance, _Row) else None

    async def flush(self) -> None:
        return None


def _bind(repository, session: _ContractSession):
    @asynccontextmanager
    async def _session():
        yield session

    repository._session = _session
    return repository


def _permission_row() -> _Row:
    return _Row(
        id=uuid.uuid4(),
        resource_type="agent",
        resource_id="agent-1",
        resource_name="Agent",
        organization_id=uuid.uuid4(),
        user_id=None,
        permission_level="read",
        is_inherited=False,
        granted_by=None,
        granted_at=datetime.now(UTC),
        expires_at=None,
    )


@pytest.fixture(autouse=True)
def directory_identity(monkeypatch):
    organization = {"id": uuid.uuid4(), "name": "Team", "code": "team"}
    monkeypatch.setattr(
        "src.repository.organization_repository.OrganizationRepository.get_by_id",
        AsyncMock(return_value=organization),
    )


class TestResourcePermissionRepository:
    @pytest.mark.asyncio
    async def test_create_loads_the_relationships_it_serialises(self) -> None:
        """A freshly flushed row has no relationships loaded either."""
        session = _ContractSession([])
        repository = _bind(ResourcePermissionRepository(), session)

        result = await repository.create(
            resource_type="agent",
            resource_id="agent-1",
            resource_name="Agent",
            organization_id=uuid.uuid4(),
            permission_level="read",
        )

        assert result["resource_id"] == "agent-1"
        assert result["organization"]["name"] == "Team"
        assert all(not set(RELATIONSHIP_NAMES).intersection(names) for names in session.refreshed)

    @pytest.mark.asyncio
    async def test_get_by_id_returns_a_serialisable_permission(self) -> None:
        session = _ContractSession([_permission_row()])
        repository = _bind(ResourcePermissionRepository(), session)

        result = await repository.get_by_id(uuid.uuid4())

        assert result is not None
        assert result["resource_id"] == "agent-1"

    @pytest.mark.asyncio
    async def test_lookups_return_serialisable_permissions(self) -> None:
        session = _ContractSession([_permission_row()])
        repository = _bind(ResourcePermissionRepository(), session)

        assert await repository.get_by_org_resource(uuid.uuid4(), "agent", "agent-1")
        assert await repository.get_by_user_resource(uuid.uuid4(), "agent", "agent-1")

    @pytest.mark.asyncio
    async def test_listings_return_serialisable_permissions(self) -> None:
        session = _ContractSession([_permission_row()])
        repository = _bind(ResourcePermissionRepository(), session)

        assert len(await repository.get_resource_permissions("agent", "agent-1")) == 1
        assert len(await repository.get_organization_permissions(uuid.uuid4())) == 1
        assert len(await repository.get_user_permissions(uuid.uuid4())) == 1


class TestTheFakeItself:
    """The fake is only worth anything if it reproduces the real failure."""

    def test_an_unloaded_relationship_raises(self) -> None:
        with pytest.raises(InvalidRequestError, match="lazy='raise'"):
            _ = _permission_row().organization

    def test_a_loaded_relationship_does_not(self) -> None:
        assert _permission_row().load({"organization"}).organization is not None
