"""Tests for the component template registry.

Spec: .tmp/flow-canvas-design.md section 4.2.
Brief: .tmp/flow-canvas-task-2-brief.md
"""

import pytest

from core.exceptions import UnknownComponentError
from domain.flows.registry import ComponentRegistry
from models.flows import (
    ComponentHandles,
    ComponentKind,
    ComponentTemplate,
    Handle,
    Lifecycle,
    PortType,
)


def _template(type_name: str, category: str = "core", **overrides) -> ComponentTemplate:
    data = {
        "type": type_name,
        "category": category,
        "display_name": type_name,
        "kind": ComponentKind.EXECUTION,
        "handles": ComponentHandles(
            outputs=[Handle(name="out", types=[PortType.MESSAGE])],
        ),
    }
    data.update(overrides)
    return ComponentTemplate.model_validate(data)


def test_get_template_returns_registered_template():
    """2.1 — lookup by type."""
    registry = ComponentRegistry()
    template = _template("Widget")
    registry.register(template)

    assert registry.get("Widget") is template


def test_get_template_raises_for_unknown_type():
    """2.2 — unknown type raises, and the message names it."""
    registry = ComponentRegistry()

    with pytest.raises(UnknownComponentError) as exc:
        registry.get("NoSuchComponent")

    assert "NoSuchComponent" in str(exc.value)


def test_list_templates_groups_by_category():
    """2.3 — listing is grouped by category."""
    registry = ComponentRegistry()
    registry.register(_template("A", category="core"))
    registry.register(_template("B", category="core"))
    registry.register(_template("C", category="knowledge"))

    grouped = registry.list_grouped()

    assert set(grouped) == {"core", "knowledge"}
    assert [t.type for t in grouped["core"]] == ["A", "B"]
    assert [t.type for t in grouped["knowledge"]] == ["C"]


def test_register_rejects_duplicate_type():
    """2.4 — registering the same type twice is a programming error."""
    registry = ComponentRegistry()
    registry.register(_template("Widget"))

    with pytest.raises(ValueError) as exc:
        registry.register(_template("Widget"))

    assert "Widget" in str(exc.value)


def test_list_templates_excludes_deprecated_by_default():
    """2.5 — deprecated components stay loadable but leave the sidebar."""
    registry = ComponentRegistry()
    registry.register(_template("Current"))
    registry.register(_template("Old", lifecycle=Lifecycle.DEPRECATED))

    default_types = {t.type for ts in registry.list_grouped().values() for t in ts}
    with_deprecated = {
        t.type for ts in registry.list_grouped(include_deprecated=True).values() for t in ts
    }

    assert default_types == {"Current"}
    assert with_deprecated == {"Current", "Old"}
    # still individually resolvable, so saved flows keep working
    assert registry.get("Old").type == "Old"
