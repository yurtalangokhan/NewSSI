"""In-memory storage session fixture for agents/storage tests.

Pure in-memory test store, enforcing:
- FK cascade: deleting definition cascades to its versions
- UniqueConstraint(definition_id, version_no) -> raises IntegrityError
- One draft per definition (unique partial index) -> raises IntegrityError
- Atomic transaction commit/rollback
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import copy
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from infrastructure.db.models.agent_definition import (
    AgentDefinitionModel,
    AgentFlowVersionModel,
    FlowVersionStatus,
)


class _Result:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._row

    def scalar(self):
        return self._row

    def scalars(self):
        return self

    def all(self):
        return self._rows


class FakeStorageDB:
    def __init__(self):
        self.definitions: dict[UUID, AgentDefinitionModel] = {}
        self.versions: dict[UUID, AgentFlowVersionModel] = {}

    def copy(self) -> FakeStorageDB:
        new_db = FakeStorageDB()
        new_db.definitions = {k: copy(v) for k, v in self.definitions.items()}
        new_db.versions = {k: copy(v) for k, v in self.versions.items()}
        return new_db


class FakeSession:
    def __init__(self, db: FakeStorageDB):
        self.db = db
        self._snapshot = db.copy()
        self.pending_adds: list[Any] = []
        self.pending_deletes: list[Any] = []

    @property
    def no_autoflush(self):
        @contextmanager
        def _no_af():
            yield

        return _no_af()

    async def connection(self, **execution_options: object):
        """``_read_session`` checks out a connection with AUTOCOMMIT options."""
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
        else:
            try:
                await self.commit()
            except Exception:
                await self.rollback()
                raise

    async def get(self, entity_class: Any, ident: Any) -> Any:
        await self.flush()
        parsed = UUID(str(ident)) if isinstance(ident, (str, UUID)) else ident
        if entity_class == AgentDefinitionModel:
            return self.db.definitions.get(parsed)
        return self.db.versions.get(parsed)

    def add(self, obj: Any):
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid4()
        self.pending_adds.append(obj)

    def add_all(self, objs: list[Any]):
        for o in objs:
            self.add(o)

    async def delete(self, obj: Any):
        self.pending_deletes.append(obj)

    async def flush(self):
        # Apply pending deletes
        for obj in self.pending_deletes:
            if isinstance(obj, AgentDefinitionModel):
                self.db.definitions.pop(obj.id, None)
                # CASCADE delete versions
                cascade_ids = [
                    vid for vid, v in self.db.versions.items() if v.definition_id == obj.id
                ]
                for vid in cascade_ids:
                    self.db.versions.pop(vid, None)
            elif isinstance(obj, AgentFlowVersionModel):
                self.db.versions.pop(obj.id, None)
        self.pending_deletes.clear()

        # Apply pending adds with constraint validations
        adds = list(self.pending_adds)
        self.pending_adds.clear()

        for obj in adds:
            if isinstance(obj, AgentDefinitionModel):
                self.db.definitions[obj.id] = obj
            elif isinstance(obj, AgentFlowVersionModel):
                existing = [
                    v
                    for v in self.db.versions.values()
                    if v.definition_id == obj.definition_id and v.id != obj.id
                ]
                for ex in existing:
                    if ex.version_no == obj.version_no:
                        raise IntegrityError(
                            "insert",
                            (),
                            Exception(
                                "unique constraint uq_agent_flow_versions_def_version violated"
                            ),
                        )

                if obj.status == FlowVersionStatus.DRAFT.value:
                    for ex in existing:
                        if ex.status == FlowVersionStatus.DRAFT.value:
                            raise IntegrityError(
                                "insert",
                                (),
                                Exception(
                                    "unique index ix_agent_flow_versions_one_draft_per_definition violated"
                                ),
                            )

                self.db.versions[obj.id] = obj

        # Check in-place modifications
        drafts_per_def: dict[UUID, int] = {}
        versions_per_def: dict[tuple[UUID, int], int] = {}
        for v in self.db.versions.values():
            if v.status == FlowVersionStatus.DRAFT.value:
                drafts_per_def[v.definition_id] = drafts_per_def.get(v.definition_id, 0) + 1
                if drafts_per_def[v.definition_id] > 1:
                    raise IntegrityError(
                        "insert",
                        (),
                        Exception(
                            "unique index ix_agent_flow_versions_one_draft_per_definition violated"
                        ),
                    )
            versions_per_def[(v.definition_id, v.version_no)] = (
                versions_per_def.get((v.definition_id, v.version_no), 0) + 1
            )
            if versions_per_def[(v.definition_id, v.version_no)] > 1:
                raise IntegrityError(
                    "insert",
                    (),
                    Exception("unique constraint uq_agent_flow_versions_def_version violated"),
                )

    async def commit(self):
        await self.flush()
        self._snapshot = self.db.copy()

    async def rollback(self):
        self.db.definitions = {k: copy(v) for k, v in self._snapshot.definitions.items()}
        self.db.versions = {k: copy(v) for k, v in self._snapshot.versions.items()}
        self.pending_adds.clear()
        self.pending_deletes.clear()

    async def refresh(self, obj: Any):
        await self.flush()

    async def execute(self, statement: Any):
        await self.flush()
        from sqlalchemy.sql.dml import Update
        from sqlalchemy.sql.selectable import Select

        if isinstance(statement, Select):
            str_stmt = str(statement)
            params = statement.compile().params

            # 1. func.max(AgentFlowVersionModel.version_no)
            if "max(agent_flow_versions.version_no)" in str_stmt:
                def_id = None
                exclude_draft = (
                    "agent_flow_versions.status !=" in str_stmt or "status !=" in str_stmt
                )
                for p in params.values():
                    if isinstance(p, UUID) or (isinstance(p, str) and len(p) == 36):
                        def_id = UUID(str(p)) if isinstance(p, str) else p
                matching = [v for v in self.db.versions.values() if v.definition_id == def_id]
                if exclude_draft:
                    matching = [v for v in matching if v.status != FlowVersionStatus.DRAFT.value]
                if not matching:
                    return _Result(row=None)
                return _Result(row=max(v.version_no for v in matching))

            # 2. select AgentFlowVersionModel
            if "FROM agent_flow_versions" in str_stmt:
                def_id = None
                status_val = None
                version_no_val = None
                for k, v in params.items():
                    if isinstance(v, (UUID, str)) and (len(str(v)) == 36 or "definition_id" in k):
                        def_id = UUID(str(v)) if isinstance(v, str) else v
                    elif v in {"draft", "published", "archived"}:
                        status_val = v
                    elif isinstance(v, int):
                        version_no_val = v

                matching = [
                    v
                    for v in self.db.versions.values()
                    if def_id is None or v.definition_id == def_id
                ]
                if status_val is not None:
                    matching = [v for v in matching if v.status == status_val]
                if version_no_val is not None:
                    matching = [v for v in matching if v.version_no == version_no_val]

                if "ORDER BY agent_flow_versions.version_no DESC" in str_stmt:
                    matching.sort(key=lambda v: v.version_no, reverse=True)

                if "WHERE" in str_stmt and (status_val is not None or version_no_val is not None):
                    return _Result(row=matching[0] if matching else None)
                return _Result(rows=matching)

            # 3. select AgentDefinitionModel
            if "FROM agent_definitions" in str_stmt:
                def_id = None
                for p in params.values():
                    if isinstance(p, UUID) or (isinstance(p, str) and len(p) == 36):
                        def_id = UUID(str(p)) if isinstance(p, str) else p
                row = self.db.definitions.get(def_id)
                return _Result(row=row)

        elif isinstance(statement, Update):
            params = statement.compile().params
            values = statement._values
            str_stmt = str(statement)

            if "agent_definitions" in str_stmt:
                def_id = None
                for p in params.values():
                    if isinstance(p, UUID) or (isinstance(p, str) and len(p) == 36):
                        def_id = UUID(str(p)) if isinstance(p, str) else p
                target = self.db.definitions.get(def_id)
                if target:
                    for col, val in values.items():
                        col_name = col.name if hasattr(col, "name") else str(col)
                        actual = getattr(val, "value", val)
                        setattr(target, col_name, actual)
                return _Result()

        return _Result()


@pytest_asyncio.fixture
async def flow_version_session_factory():
    shared_db = FakeStorageDB()

    def session_maker():
        return FakeSession(shared_db)

    yield session_maker


@pytest.fixture
def patched_repository_session(flow_version_session_factory, monkeypatch):
    import infrastructure.db.repositories.base as base_module

    monkeypatch.setattr(base_module, "get_session_factory", lambda: flow_version_session_factory)
    return flow_version_session_factory
