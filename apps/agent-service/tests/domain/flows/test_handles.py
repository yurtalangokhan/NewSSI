"""Tests for the values-aware view of a component template.

Pure and total, like test_handle_types.py: no I/O, and no input may raise.
"""

from __future__ import annotations

import pytest

from domain.flows.handles import (
    effective_input_handles,
    effective_output_handles,
    field_visible,
    resolved_values,
    visible_inputs,
)
from models.flows import (
    ComponentHandles,
    ComponentKind,
    ComponentTemplate,
    FieldType,
    Handle,
    InputField,
    PortType,
    ShowWhen,
    TableColumn,
)


def _expanding_template() -> ComponentTemplate:
    return ComponentTemplate(
        type="Expander",
        category="logic",
        display_name="Expander",
        kind=ComponentKind.EXECUTION,
        inputs={
            "routes": InputField(
                type=FieldType.TABLE,
                display_name="Routes",
                columns=[
                    TableColumn(name="condition", display_name="Condition"),
                    TableColumn(name="route", display_name="Route"),
                ],
            )
        },
        handles=ComponentHandles(
            inputs=[Handle(name="input", types=[PortType.MESSAGE])],
            outputs=[
                Handle(
                    name="routes",
                    types=[PortType.TRIGGER],
                    expands_from="routes",
                    expands_label_key="route",
                )
            ],
        ),
    )


def test_expands_one_handle_per_row():
    template = _expanding_template()
    values = {"routes": [{"condition": "a", "route": "high"}, {"condition": "b", "route": "low"}]}
    assert [h.name for h in effective_output_handles(template, values)] == ["high", "low"]
    assert all(h.types == [PortType.TRIGGER] for h in effective_output_handles(template, values))


def test_keeps_declared_handle_when_no_rows_yield_a_label():
    template = _expanding_template()
    assert [h.name for h in effective_output_handles(template, {"routes": []})] == ["routes"]
    assert [h.name for h in effective_output_handles(template, {})] == ["routes"]


def test_skips_rows_with_a_blank_or_missing_label():
    template = _expanding_template()
    values = {"routes": [{"route": ""}, {"condition": "b"}, {"route": "ok"}]}
    assert [h.name for h in effective_output_handles(template, values)] == ["ok"]


def test_non_expanding_handles_pass_through_untouched():
    template = ComponentTemplate(
        type="Plain",
        category="logic",
        display_name="Plain",
        kind=ComponentKind.EXECUTION,
        handles=ComponentHandles(outputs=[Handle(name="output", types=[PortType.MESSAGE])]),
    )
    assert [h.name for h in effective_output_handles(template, {})] == ["output"]


@pytest.mark.parametrize(
    ("rows",),
    [({"routes": "not-a-list"},), ({"routes": [None, 3, {"route": None}]},)],
)
def test_never_raises_on_malformed_values(rows):
    """Total: a hand-edited spec must not crash the validator."""
    assert effective_output_handles(_expanding_template(), rows)


def _field(**kw) -> InputField:
    return InputField(type=FieldType.BOOL, display_name="Flag", **kw)


def test_field_without_show_when_is_always_visible():
    assert field_visible(_field(), {}) is True


def test_not_equals_hides_only_on_match():
    field = _field(show_when=ShowWhen(field="operator", not_equals="regex"))
    assert field_visible(field, {"operator": "regex"}) is False
    assert field_visible(field, {"operator": "contains"}) is True


def test_equals_and_one_of():
    eq = _field(show_when=ShowWhen(field="mode", equals="on"))
    assert field_visible(eq, {"mode": "on"}) is True
    assert field_visible(eq, {"mode": "off"}) is False
    assert field_visible(eq, {}) is False  # missing sibling reads as None

    one_of = _field(show_when=ShowWhen(field="mode", one_of=["a", "b"]))
    assert field_visible(one_of, {"mode": "b"}) is True
    assert field_visible(one_of, {"mode": "c"}) is False


def test_resolved_values_fills_template_defaults():
    template = ComponentTemplate(
        type="Defaults",
        category="logic",
        display_name="Defaults",
        kind=ComponentKind.EXECUTION,
        inputs={"op": InputField(type=FieldType.STR, display_name="Op", value="contains")},
        handles=ComponentHandles(outputs=[Handle(name="out", types=[PortType.MESSAGE])]),
    )
    assert resolved_values(template, {}) == {"op": "contains"}
    assert resolved_values(template, {"op": "regex"}) == {"op": "regex"}


def test_visible_inputs_uses_resolved_defaults():
    """A field hidden by the template's *default* operator must be hidden
    even when the node overrides nothing."""
    template = ComponentTemplate(
        type="Hider",
        category="logic",
        display_name="Hider",
        kind=ComponentKind.EXECUTION,
        inputs={
            "operator": InputField(type=FieldType.STR, display_name="Op", value="regex"),
            "case_sensitive": InputField(
                type=FieldType.BOOL,
                display_name="Case sensitive",
                show_when=ShowWhen(field="operator", not_equals="regex"),
            ),
        },
        handles=ComponentHandles(outputs=[Handle(name="out", types=[PortType.MESSAGE])]),
    )
    assert set(visible_inputs(template, {})) == {"operator"}
    assert set(visible_inputs(template, {"operator": "contains"})) == {"operator", "case_sensitive"}


# ---------------------------------------------------------------------------
# Input handles — the mirror of the output resolver (Phase 4.5)
# ---------------------------------------------------------------------------


def _conditional_input_template() -> ComponentTemplate:
    return ComponentTemplate(
        type="X",
        category="logic",
        display_name="X",
        icon="SvgBranch",
        kind=ComponentKind.EXECUTION,
        inputs={"on": InputField(type=FieldType.BOOL, display_name="On", value=False)},
        handles=ComponentHandles(
            inputs=[
                Handle(name="always", types=[PortType.MESSAGE]),
                Handle(
                    name="maybe",
                    types=[PortType.MESSAGE],
                    show_when=ShowWhen(field="on", equals=True),
                ),
            ]
        ),
    )


def test_effective_input_handles_respects_show_when():
    template = _conditional_input_template()
    assert [h.name for h in effective_input_handles(template, {})] == ["always"]
    assert [h.name for h in effective_input_handles(template, {"on": True})] == [
        "always",
        "maybe",
    ]


def test_effective_input_handles_is_total_for_a_hand_edited_spec():
    template = _conditional_input_template()
    # Junk values must not raise — a stored spec is untrusted input.
    assert [h.name for h in effective_input_handles(template, {"on": "evet"})] == ["always"]


def test_handle_declares_fallback_field():
    handle = Handle(name="items", types=[PortType.DATA], fallback_field="items_source")
    assert handle.fallback_field == "items_source"
    assert Handle(name="plain", types=[PortType.DATA]).fallback_field is None
