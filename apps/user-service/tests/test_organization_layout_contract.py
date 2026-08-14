"""Focused contract tests for organization layout persistence."""

import importlib.util
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import HTTPException

from src.controller.organization_layout_controller import OrganizationLayoutController
from src.core.database.models import OrganizationLayoutModel
from src.core.exceptions import ForbiddenError, NotFoundError
from src.repository.organization_layout_repository import OrganizationLayoutRepository
from src.service.organization_layout_service import OrganizationLayoutService


class ScalarResult:
    """Minimal result object used by the repository's real query methods."""

    def __init__(self, values: list[object]) -> None:
        self.values = values

    def scalars(self) -> "ScalarResult":
        return self

    def all(self) -> list[object]:
        return self.values


class OrderedReadSession:
    """In-memory session that records the repository's read statement."""

    def __init__(self, layouts: list[OrganizationLayoutModel]) -> None:
        self.layouts = layouts
        self.statement: object | None = None

    async def execute(self, statement: object) -> ScalarResult:
        self.statement = statement
        return ScalarResult(self.layouts)


class OrderedReadRepository(OrganizationLayoutRepository):
    """Exercise the real read method against a deterministic in-memory result."""

    def __init__(self, session: OrderedReadSession) -> None:
        self.session = session

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[OrderedReadSession]:
        yield self.session


class StableUpsertSession:
    """In-memory result stream for the real transactional upsert method."""

    def __init__(self, ids: list[uuid.UUID], layouts: list[OrganizationLayoutModel]) -> None:
        self.ids = ids
        self.layouts = layouts
        self.statements: list[object] = []

    async def execute(self, statement: object) -> ScalarResult:
        self.statements.append(statement)
        if len(self.statements) == 1:
            return ScalarResult(self.ids)
        if len(self.statements) == 2:
            return ScalarResult([])
        return ScalarResult(self.layouts)


class StableUpsertRepository(OrganizationLayoutRepository):
    """Exercise the real upsert statement construction with deterministic results."""

    def __init__(self, session: StableUpsertSession) -> None:
        self.session = session

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[StableUpsertSession]:
        yield self.session


class InMemoryLayoutRepository:
    """Stateful layout store for service authorization and atomicity tests."""

    def __init__(self, existing_ids: set[uuid.UUID], writable_ids: set[uuid.UUID]) -> None:
        self.existing_ids = existing_ids
        self.writable_ids = writable_ids
        self.saved: dict[uuid.UUID, dict] = {}
        self.upsert_calls = 0

    async def get_all_positions(self) -> list[dict]:
        return [self.saved[organization_id] for organization_id in sorted(self.saved, key=str)]

    async def get_existing_organization_ids(
        self, organization_ids: set[uuid.UUID]
    ) -> set[uuid.UUID]:
        return organization_ids & self.existing_ids

    async def get_writable_organization_ids(self, _actor_id: uuid.UUID) -> list[uuid.UUID]:
        return sorted(self.writable_ids, key=str)

    async def bulk_upsert_positions(self, positions: list[dict]) -> list[dict]:
        self.upsert_calls += 1
        pending = {position["organization_id"]: position for position in positions}
        self.saved.update(pending)
        return [pending[organization_id] for organization_id in sorted(pending, key=str)]


class IsolatedOrganizationLayoutController(OrganizationLayoutController):
    """Controller test double that receives a per-test service instance."""

    def __init__(self, service: OrganizationLayoutService) -> None:
        self.service = service


class MigrationOperations:
    """Capture migration DDL without requiring a live database."""

    def __init__(self) -> None:
        self.table_arguments: tuple[object, ...] | None = None

    def create_table(self, _name: str, *arguments: object) -> None:
        self.table_arguments = arguments

    def drop_table(self, _name: str) -> None:
        return None


def test_layout_model_has_cascading_organization_key_and_bounded_coordinates() -> None:
    """The model declares the database contract required by the migration."""
    table = OrganizationLayoutModel.__table__
    foreign_key = next(iter(table.foreign_keys))
    constraints = {constraint.name for constraint in table.constraints}

    assert foreign_key.ondelete == "CASCADE"
    assert "ck_organization_layouts_position_x_bounds" in constraints
    assert "ck_organization_layouts_position_y_bounds" in constraints


def test_layout_migration_creates_the_same_cascading_bounded_table_contract() -> None:
    """The Alembic upgrade emits the layout table constraints declared by the model."""
    migration_path = (
        Path(__file__).parents[1]
        / "src"
        / "core"
        / "database"
        / "migrations"
        / "versions"
        / "0019_add_organization_layouts.py"
    )
    spec = importlib.util.spec_from_file_location("organization_layout_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    operations = MigrationOperations()
    migration.op = operations

    migration.upgrade()

    assert operations.table_arguments is not None
    foreign_keys = [
        argument
        for argument in operations.table_arguments
        if getattr(argument, "ondelete", None) == "CASCADE"
    ]
    constraints = {
        getattr(argument, "name", None)
        for argument in operations.table_arguments
        if getattr(argument, "name", None)
    }
    assert foreign_keys
    assert "ck_organization_layouts_position_x_bounds" in constraints
    assert "ck_organization_layouts_position_y_bounds" in constraints


@pytest.mark.asyncio
async def test_repository_read_maps_positions_and_orders_by_organization_id() -> None:
    """The repository returns persisted positions through an ID-ordered query."""
    first_id, second_id = sorted([uuid.uuid4(), uuid.uuid4()], key=str)
    session = OrderedReadSession(
        [
            OrganizationLayoutModel(organization_id=first_id, position_x=1.0, position_y=2.0),
            OrganizationLayoutModel(organization_id=second_id, position_x=3.0, position_y=4.0),
        ]
    )

    positions = await OrderedReadRepository(session).get_all_positions()

    assert positions == [
        {"organization_id": first_id, "x": 1.0, "y": 2.0},
        {"organization_id": second_id, "x": 3.0, "y": 4.0},
    ]
    assert "ORDER BY organization_layouts.organization_id" in str(session.statement)


@pytest.mark.asyncio
async def test_repository_bulk_upsert_returns_positions_in_stable_id_order() -> None:
    """The real upsert method validates first and returns a stable ordering."""
    first_id, second_id = sorted([uuid.uuid4(), uuid.uuid4()], key=str)
    session = StableUpsertSession(
        [first_id, second_id],
        [
            OrganizationLayoutModel(organization_id=first_id, position_x=1.0, position_y=2.0),
            OrganizationLayoutModel(organization_id=second_id, position_x=3.0, position_y=4.0),
        ],
    )

    positions = await StableUpsertRepository(session).bulk_upsert_positions(
        [
            {"organization_id": second_id, "x": 3.0, "y": 4.0},
            {"organization_id": first_id, "x": 1.0, "y": 2.0},
        ]
    )

    assert positions == [
        {"organization_id": first_id, "x": 1.0, "y": 2.0},
        {"organization_id": second_id, "x": 3.0, "y": 4.0},
    ]
    assert "ON CONFLICT" in str(session.statements[1])
    assert "ORDER BY organization_layouts.organization_id" in str(session.statements[2])


@pytest.mark.asyncio
async def test_service_rejects_mixed_authority_batch_without_mutating_positions() -> None:
    """A single unauthorized ID prevents every position in the batch from saving."""
    writable_id, forbidden_id = uuid.uuid4(), uuid.uuid4()
    repository = InMemoryLayoutRepository({writable_id, forbidden_id}, {writable_id})
    service = OrganizationLayoutService()
    service.repo = repository  # type: ignore[assignment]

    with pytest.raises(ForbiddenError):
        await service.save_layout(
            uuid.uuid4(),
            [
                {"organization_id": writable_id, "x": 1.0, "y": 2.0},
                {"organization_id": forbidden_id, "x": 3.0, "y": 4.0},
            ],
        )

    assert repository.saved == {}
    assert repository.upsert_calls == 0


@pytest.mark.asyncio
async def test_service_rejects_unknown_ids_without_mutating_positions() -> None:
    """Unknown organizations return not-found before an upsert can begin."""
    unknown_id = uuid.uuid4()
    repository = InMemoryLayoutRepository(set(), {unknown_id})
    service = OrganizationLayoutService()
    service.repo = repository  # type: ignore[assignment]

    with pytest.raises(NotFoundError):
        await service.save_layout(
            uuid.uuid4(), [{"organization_id": unknown_id, "x": 1.0, "y": 2.0}]
        )

    assert repository.saved == {}
    assert repository.upsert_calls == 0


@pytest.mark.asyncio
async def test_controller_translates_duplicate_ids_to_bad_request() -> None:
    """Duplicate layout IDs use the API's required HTTP 400 contract."""
    organization_id = uuid.uuid4()
    repository = InMemoryLayoutRepository({organization_id}, {organization_id})
    service = OrganizationLayoutService()
    service.repo = repository  # type: ignore[assignment]
    controller = IsolatedOrganizationLayoutController(service)

    with pytest.raises(HTTPException) as error:
        await controller.save_layout(
            uuid.uuid4(),
            [
                {"organization_id": organization_id, "x": 1.0, "y": 2.0},
                {"organization_id": organization_id, "x": 3.0, "y": 4.0},
            ],
        )

    assert error.value.status_code == 400
    assert repository.saved == {}
