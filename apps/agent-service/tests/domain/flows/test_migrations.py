"""Tests for the template migration registry.

No real migrations exist yet — every production template is at v1. Tests use
fixture templates registered into a fresh ``ComponentRegistry()``, not the
production one, so they stay independent of what P5/P6/P8 eventually ship.

Spec: .tmp/flow-canvas-design.md section 4.6.
Brief: .tmp/flow-canvas-task-4-brief.md
"""

import pytest

from core.exceptions import MissingMigrationError, UnknownComponentError
from domain.flows.migrations import (
    migrate_node_values,
    migrate_spec,
    register_handle_rename,
    register_migration,
)
from domain.flows.registry import ComponentRegistry, get_registry
from models.flows import (
    ComponentHandles,
    ComponentKind,
    ComponentTemplate,
    FlowSpec,
    Handle,
    PortType,
)


def _template(type_name: str, template_version: int = 1) -> ComponentTemplate:
    return ComponentTemplate(
        type=type_name,
        category="test",
        display_name=type_name,
        template_version=template_version,
        kind=ComponentKind.EXECUTION,
        handles=ComponentHandles(outputs=[Handle(name="out", types=[PortType.MESSAGE])]),
    )


def test_values_at_current_version_pass_through_unchanged():
    """4.1 — identity when from_version == to_version."""
    registry = ComponentRegistry()
    registry.register(_template("MigrationTestIdentity", template_version=1))

    result = migrate_node_values("MigrationTestIdentity", 1, 1, {"a": 1}, registry=registry)

    assert result == {"a": 1}


def test_single_step_migration_transforms_values():
    """4.2 — v1 -> v2 applies the registered transform."""
    registry = ComponentRegistry()
    registry.register(_template("MigrationTestSingleStep", template_version=2))
    register_migration(
        "MigrationTestSingleStep",
        1,
        lambda values: {
            **{k: v for k, v in values.items() if k != "old_name"},
            "new_name": values["old_name"],
        },
    )

    result = migrate_node_values(
        "MigrationTestSingleStep", 1, 2, {"old_name": "hello"}, registry=registry
    )

    assert result == {"new_name": "hello"}


def test_multi_step_migration_chains_in_order():
    """4.3 — v1 -> v3 applies both steps, in order."""
    registry = ComponentRegistry()
    registry.register(_template("MigrationTestChain", template_version=3))
    register_migration(
        "MigrationTestChain", 1, lambda v: {**v, "steps": [*v.get("steps", []), "1to2"]}
    )
    register_migration(
        "MigrationTestChain", 2, lambda v: {**v, "steps": [*v.get("steps", []), "2to3"]}
    )

    result = migrate_node_values("MigrationTestChain", 1, 3, {"steps": []}, registry=registry)

    assert result["steps"] == ["1to2", "2to3"]


def test_missing_migration_raises_with_actionable_message():
    """4.4 — a version bump with no migration is a test failure, not a silent gap."""
    registry = ComponentRegistry()
    registry.register(_template("MigrationTestMissing", template_version=2))
    # deliberately no register_migration call for version 1

    with pytest.raises(MissingMigrationError) as exc:
        migrate_node_values("MigrationTestMissing", 1, 2, {}, registry=registry)

    message = str(exc.value)
    assert "MigrationTestMissing" in message
    assert "1" in message


def test_migration_does_not_mutate_input_dict():
    """4.5 — migrations run on cached config dicts; a mutation would corrupt the cache."""
    registry = ComponentRegistry()
    registry.register(_template("MigrationTestMutate", template_version=2))
    register_migration("MigrationTestMutate", 1, lambda v: {**v, "extra": True})

    original = {"a": 1}
    migrate_node_values("MigrationTestMutate", 1, 2, original, registry=registry)

    assert original == {"a": 1}


def test_downgrade_is_rejected():
    """4.6 — migrations only move forward."""
    registry = ComponentRegistry()
    registry.register(_template("MigrationTestDowngrade", template_version=1))

    with pytest.raises(ValueError):
        migrate_node_values("MigrationTestDowngrade", 2, 1, {}, registry=registry)


def test_every_registered_template_version_has_a_migration_path():
    """4.7 — registry-wide guard: a version bump without a migration fails here,
    not at runtime. Runs against the real, live registry."""
    registry = get_registry()
    for templates in registry.list_grouped(include_deprecated=True).values():
        for template in templates:
            migrate_node_values(template.type, 1, template.template_version, {}, registry=registry)


def test_unknown_component_type_raises_unknown_component_error():
    """4.8 — a bogus type gets the actionable Task 2 error, not a migration-shaped one."""
    registry = ComponentRegistry()

    with pytest.raises(UnknownComponentError):
        migrate_node_values("NoSuchThing", 1, 1, {}, registry=registry)


def test_router_v1_rows_become_is_truthy_comparisons():
    """Router v1->v2: the registry's first real migration. Old rows kept the
    branch label under "route" (canvas) or "label" (hand-authored); both
    normalise to a v2 operator row that means exactly the same thing."""
    registry = get_registry()

    canvas = migrate_node_values(
        "Router", 1, 2, {"routes": [{"condition": "x", "route": "hi"}]}, registry=registry
    )
    assert canvas["routes"] == [
        {"source": "x", "operator": "is_truthy", "match_text": "", "route": "hi"}
    ]

    legacy = migrate_node_values(
        "Router", 1, 2, {"routes": [{"condition": "x", "label": "hi"}]}, registry=registry
    )
    assert legacy["routes"] == canvas["routes"]


@pytest.mark.parametrize("bad", [{}, {"routes": None}, {"routes": "nope"}, {"routes": [None, 3]}])
def test_router_v1_to_v2_never_crashes_on_a_malformed_routes_value(bad):
    out = migrate_node_values("Router", 1, 2, bad, registry=get_registry())
    assert out["routes"] == []


def test_v1_loop_node_is_renamed_to_while_on_migrate_spec():
    """Phase 3: the counter loop kept its behaviour but lost the 'Loop' name
    to Langflow's foreach. A stored v1 Loop node becomes a While node,
    values intact, so archived flows keep working."""
    from models.flows import FlowSpec

    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {
                    "id": "node-loop-control",
                    "type": "Loop",
                    "template_version": 1,
                    "values": {"condition": "needs_more_work", "max_iterations": 3},
                },
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [],
        }
    )
    migrated = migrate_spec(spec)
    loop = next(n for n in migrated.nodes if n.id == "node-loop-control")
    assert loop.type == "While"
    assert loop.template_version == 1
    assert loop.values == {"condition": "needs_more_work", "max_iterations": 3}


def test_v2_loop_node_is_left_alone():
    """A foreach Loop (v2) is not the renamed counter loop."""
    from models.flows import FlowSpec

    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {
                    "id": "l",
                    "type": "Loop",
                    "template_version": 2,
                    "values": {"items_source": "xs"},
                },
            ],
            "edges": [],
        }
    )
    migrated = migrate_spec(spec)
    assert migrated.nodes[0].type == "Loop"


def test_router_v1_to_v2_passes_through_rows_that_are_already_v2():
    """A hand-authored spec can carry v2 rows while still declaring
    template_version 1 (easy to forget when writing JSON by hand). Rewriting
    those rows destroys them — operator is forced to is_truthy and match_text
    is wiped, so the first row then matches everything. A row that already
    names a source/operator is left alone."""
    already_v2 = {
        "routes": [
            {"source": "", "operator": "contains", "match_text": "fatura", "route": "billing"},
            {"source": "score", "operator": "greater_than", "match_text": "5", "route": "high"},
        ]
    }
    out = migrate_node_values("Router", 1, 2, already_v2, registry=get_registry())
    assert out["routes"] == already_v2["routes"]


def test_router_v1_to_v2_still_rewrites_a_genuine_v1_row():
    out = migrate_node_values(
        "Router", 1, 2, {"routes": [{"condition": "x", "route": "hi"}]}, registry=get_registry()
    )
    assert out["routes"] == [
        {"source": "x", "operator": "is_truthy", "match_text": "", "route": "hi"}
    ]


def test_smart_router_v1_custom_prompt_placeholders_migrate():
    """v1 used {input}/{categories}; v2 uses Langflow's {input_text}/{routes}."""
    out = migrate_node_values("SmartRouter", 1, 2, {"custom_prompt": "In {input}, of {categories}"})
    assert out["custom_prompt"] == "In {input_text}, of {routes}"


def test_smart_router_v1_without_a_custom_prompt_is_untouched():
    values = {"routes": [{"route_category": "billing"}]}
    assert migrate_node_values("SmartRouter", 1, 2, values) == values


def test_handle_rename_rewrites_only_the_renamed_types_edges():
    """The value registry moves a type's values forward and _type_renames moves
    its name; neither can follow a *port* whose name changed, and a stale
    handle silently detaches a branch."""
    register_handle_rename("HandleRenameTest", 1, "old", "new")
    registry = ComponentRegistry()
    registry.register(
        ComponentTemplate(
            type="HandleRenameTest",
            category="logic",
            display_name="Handle Rename Test",
            icon="SvgBranch",
            kind=ComponentKind.EXECUTION,
            handles=ComponentHandles(outputs=[Handle(name="new", types=[PortType.MESSAGE])]),
        )
    )
    registry.register(
        ComponentTemplate(
            type="HandleRenameOther",
            category="logic",
            display_name="Other",
            icon="SvgBranch",
            kind=ComponentKind.EXECUTION,
            handles=ComponentHandles(outputs=[Handle(name="old", types=[PortType.MESSAGE])]),
        )
    )
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "a", "type": "HandleRenameTest", "template_version": 1},
                {"id": "b", "type": "HandleRenameOther", "template_version": 1},
                {"id": "z", "type": "HandleRenameOther", "template_version": 1},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "a",
                    "sourceHandle": "old",
                    "target": "z",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "b",
                    "sourceHandle": "old",
                    "target": "z",
                    "targetHandle": "input",
                },
            ],
        }
    )
    migrated = migrate_spec(spec, registry=registry)
    handles = {e.id: e.source_handle for e in migrated.edges}
    assert handles["e1"] == "new"  # renamed
    assert handles["e2"] == "old"  # a different type: untouched


def test_human_input_v1_migrates_the_field_and_its_edge():
    """Langflow's `fallback` is its *timeout* path; ours is the
    unmatched-answer path — a case Langflow's button UI cannot even produce.
    Different job, so a different name; stored flows must survive it."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {
                    "id": "hi",
                    "type": "HumanInput",
                    "template_version": 1,
                    "values": {
                        "prompt": "?",
                        "decisions": [{"label": "Onayla"}],
                        "enable_fallback": True,
                    },
                },
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "hi",
                    "sourceHandle": "fallback",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )
    migrated = migrate_spec(spec)
    node = migrated.nodes[0]
    assert node.template_version == 2
    assert node.values["enable_unmatched"] is True
    assert "enable_fallback" not in node.values
    assert migrated.edges[0].source_handle == "unmatched"
