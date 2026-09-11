"""Tests for FlowService's draft methods — save_draft/load_draft/list_versions.

Uses a fake FlowVersionRepository, matching this project's established DI
pattern (Tasks 2/4/5/6) rather than a real database — FlowVersionRepository's
own real-DB behavior is covered by test_flow_version_repository.py (Task 15).

save_flow (writing agent_definitions.flow_spec directly) is UNCHANGED by this
task — see .tmp/flow-canvas-task-15-brief.md "What save_flow does after this
task". Both paths are deliberately live at once until Task 16 re-points
flow_spec to mean "published cache".

Spec: .tmp/flow-canvas-design.md section 5.2.
Brief: .tmp/flow-canvas-task-15-brief.md
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from domain.flows.service import FlowService
from models.flows import FlowSpec


def _valid_flow_dict() -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "agent-1", "type": "ReActAgent", "values": {"system_prompt": "Be helpful."}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "agent-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


class _FakeVersionRepo:
    def __init__(self) -> None:
        self.drafts: dict = {}
        self.upsert_calls: list[dict] = []

    async def upsert_draft(self, definition_id, flow_spec, *, created_by=None, notes=None):
        self.upsert_calls.append(
            {"definition_id": definition_id, "flow_spec": flow_spec, "created_by": created_by}
        )
        version = self.drafts.get(definition_id)
        if version is None:
            version = SimpleNamespace(
                id=uuid4(),
                definition_id=definition_id,
                version_no=1,
                flow_spec=flow_spec,
                status="draft",
                created_by=created_by,
                notes=notes,
            )
        else:
            version.flow_spec = flow_spec
        self.drafts[definition_id] = version
        return version

    async def get_draft(self, definition_id):
        return self.drafts.get(definition_id)

    async def list_versions(self, definition_id):
        version = self.drafts.get(definition_id)
        return [version] if version else []


# ---------------------------------------------------------------------------
# 15.7 — save_draft migrates template values (reuses Task 4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_draft_migrates_template_values():
    from domain.flows.migrations import register_migration
    from domain.flows.registry import ComponentRegistry
    from models.flows import ComponentHandles, ComponentKind, ComponentTemplate, Handle, PortType

    registry = ComponentRegistry()
    registry.register(
        ComponentTemplate(
            type="MigratableWidget",
            category="test",
            display_name="MigratableWidget",
            template_version=2,
            kind=ComponentKind.EXECUTION,
            handles=ComponentHandles(outputs=[Handle(name="out", types=[PortType.MESSAGE])]),
        )
    )
    register_migration("MigratableWidget", 1, lambda v: {**v, "migrated": True})

    version_repo = _FakeVersionRepo()
    service = FlowService(registry=registry, version_repository=version_repo)
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "n1", "type": "MigratableWidget", "template_version": 1, "values": {"a": 1}}
            ],
            "edges": [],
        }
    )

    await service.save_draft(definition_id=uuid4(), flow_spec=spec, user_id="u1")

    saved_spec = version_repo.upsert_calls[0]["flow_spec"]
    assert saved_spec["nodes"][0]["template_version"] == 2
    assert saved_spec["nodes"][0]["values"] == {"a": 1, "migrated": True}


# ---------------------------------------------------------------------------
# 15.8 — the headline test: saving a draft never touches flow_spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_draft_does_not_change_definition_flow_spec():
    version_repo = _FakeVersionRepo()

    class _FakeDefRepo:
        def __init__(self):
            self.update_called = False

        async def update(self, *args, **kwargs):
            self.update_called = True

    def_repo = _FakeDefRepo()
    service = FlowService(repository=def_repo, version_repository=version_repo)
    spec = FlowSpec.model_validate(_valid_flow_dict())

    await service.save_draft(definition_id=uuid4(), flow_spec=spec, user_id="u1")

    assert def_repo.update_called is False


# ---------------------------------------------------------------------------
# 15.9 — load_draft round-trips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_draft_round_trips_flow_spec():
    version_repo = _FakeVersionRepo()
    service = FlowService(version_repository=version_repo)
    spec = FlowSpec.model_validate(_valid_flow_dict())
    definition_id = uuid4()

    await service.save_draft(definition_id=definition_id, flow_spec=spec, user_id="u1")
    loaded = await service.load_draft(definition_id)

    assert loaded == spec


@pytest.mark.asyncio
async def test_load_draft_returns_none_when_absent():
    version_repo = _FakeVersionRepo()
    service = FlowService(version_repository=version_repo)

    loaded = await service.load_draft(uuid4())

    assert loaded is None


# ---------------------------------------------------------------------------
# list_versions passthrough
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_versions_delegates_to_repository():
    version_repo = _FakeVersionRepo()
    service = FlowService(version_repository=version_repo)
    spec = FlowSpec.model_validate(_valid_flow_dict())
    definition_id = uuid4()
    await service.save_draft(definition_id=definition_id, flow_spec=spec, user_id="u1")

    versions = await service.list_versions(definition_id)

    assert len(versions) == 1


# ---------------------------------------------------------------------------
# Migrations run on read, not only on write
#
# `migrations.py`: "Migrations run **on read** — in the compiler and the editor
# load path". The compiler, flow_agent and the Playground all call
# `migrate_spec`; the editor load path did not, so a draft stored before a
# template version bump reached the canvas in its old shape. The canvas then
# rendered it against the *current* template — for the Phase 3 `Loop` -> `While`
# rename that means orphaned handles — and the next autosave persisted that.
# ---------------------------------------------------------------------------


def _stale_spec_and_registry():
    """A one-node spec stored at template_version 1, plus a registry whose
    template is at 2 with a migration registered."""
    from domain.flows.migrations import register_migration
    from domain.flows.registry import ComponentRegistry
    from models.flows import ComponentHandles, ComponentKind, ComponentTemplate, Handle, PortType

    registry = ComponentRegistry()
    registry.register(
        ComponentTemplate(
            type="StaleWidget",
            category="test",
            display_name="StaleWidget",
            template_version=2,
            kind=ComponentKind.EXECUTION,
            handles=ComponentHandles(outputs=[Handle(name="out", types=[PortType.MESSAGE])]),
        )
    )
    register_migration("StaleWidget", 1, lambda v: {**v, "migrated": True})

    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "n1", "type": "StaleWidget", "template_version": 1, "values": {"a": 1}}
            ],
            "edges": [],
        }
    )
    return spec, registry


@pytest.mark.asyncio
async def test_load_draft_migrates_a_stale_stored_spec():
    spec, registry = _stale_spec_and_registry()
    version_repo = _FakeVersionRepo()
    definition_id = uuid4()
    version_repo.drafts[definition_id] = SimpleNamespace(
        flow_spec=spec.model_dump(by_alias=True, mode="json")
    )
    service = FlowService(registry=registry, version_repository=version_repo)

    loaded = await service.load_draft(definition_id)

    assert loaded is not None
    assert loaded.nodes[0].template_version == 2
    assert loaded.nodes[0].values == {"a": 1, "migrated": True}


@pytest.mark.asyncio
async def test_load_published_migrates_a_stale_stored_spec():
    spec, registry = _stale_spec_and_registry()
    version_repo = _FakeVersionRepo()
    definition_id = uuid4()
    version_repo.published = {
        definition_id: SimpleNamespace(flow_spec=spec.model_dump(by_alias=True, mode="json"))
    }

    async def _get_published(did):
        return version_repo.published.get(did)

    version_repo.get_published = _get_published
    service = FlowService(registry=registry, version_repository=version_repo)

    loaded = await service.load_published(definition_id)

    assert loaded is not None
    assert loaded.nodes[0].template_version == 2
    assert loaded.nodes[0].values == {"a": 1, "migrated": True}
