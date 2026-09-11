"""Tests for the Core and control-flow component templates.

The structural guards (2.7, 2.8, 2.14, 2.15) iterate the live registry so that
templates added in later phases are covered without new tests.

Spec: .tmp/flow-canvas-design.md sections 4.2, 4.3, 7.1, 7.2.
Brief: .tmp/flow-canvas-task-2-brief.md
"""

import pytest

from domain.flows.registry import get_registry
from domain.flows.sources import KNOWN_OPTIONS_SOURCES
from domain.flows.templates.icons import ICON_ALLOWLIST
from models.flows import ComponentKind, FieldType, PortType

CORE_TYPES = [
    "ChatInput",
    "ChatOutput",
    "TextInput",
    "FileInput",
    "PromptTemplate",
    "LLMModel",
    "OllamaModel",
    "ZeroShotAgent",
    "ReActAgent",
    "PlanExecuteAgent",
    "SelfReflectAgent",
]

CONTROL_FLOW_TYPES = [
    "Router",
    "Loop",
    "While",
    "Merge",
    "ConditionalRouter",
    "SmartRouter",
    "HumanInput",
    "Guardrails",
]

ALL_TYPES = CORE_TYPES + CONTROL_FLOW_TYPES


@pytest.fixture
def registry():
    return get_registry()


def _all_templates(registry):
    return [
        t
        for templates in registry.list_grouped(include_deprecated=True).values()
        for t in templates
    ]


def test_all_core_templates_are_registered(registry):
    """2.6 — every Core and control-flow template is present."""
    registered = {t.type for t in _all_templates(registry)}

    assert set(ALL_TYPES).issubset(registered)
    assert len(ALL_TYPES) == 19


def test_every_template_has_valid_field_types(registry):
    """2.7 — structural guard over the whole registry."""
    for template in _all_templates(registry):
        for name, field in template.inputs.items():
            assert isinstance(field.type, FieldType), (
                f"{template.type}.{name} has non-enum field type {field.type!r}"
            )


def test_every_template_has_valid_port_types(registry):
    """2.8 — structural guard over the whole registry."""
    for template in _all_templates(registry):
        handles = list(template.handles.inputs) + list(template.handles.outputs)
        for handle in handles:
            assert handle.types, f"{template.type}.{handle.name} declares no port type"
            for port in handle.types:
                assert isinstance(port, PortType), (
                    f"{template.type}.{handle.name} has non-enum port {port!r}"
                )


def test_resource_templates_have_no_message_input_handle(registry):
    """2.9 — resources are injected at build time, they do not consume messages."""
    for template in _all_templates(registry):
        if template.kind is not ComponentKind.RESOURCE:
            continue
        for handle in template.handles.inputs:
            assert PortType.MESSAGE not in handle.types, (
                f"resource {template.type} accepts Message on '{handle.name}'; "
                "resources are build-time injected, not message consumers"
            )


def test_chat_input_has_no_input_handles(registry):
    """2.10 — the entry node."""
    template = registry.get("ChatInput")

    assert template.handles.inputs == []
    assert [h.name for h in template.handles.outputs] == ["message"]


def test_chat_output_has_no_output_handles(registry):
    """2.11 — the exit node."""
    template = registry.get("ChatOutput")

    assert template.handles.outputs == []
    assert [h.name for h in template.handles.inputs] == ["message"]


def test_while_requires_max_iterations(registry):
    """2.12 — an unbounded counter loop is the canvas's deadlock risk (R2).
    The counter loop is now the While type; Loop is Langflow's foreach."""
    template = registry.get("While")

    assert "max_iterations" in template.inputs
    assert template.inputs["max_iterations"].required is True


def test_loop_is_a_foreach_with_item_and_done_branches(registry):
    """Loop matches Langflow: iterate a collection, no max_iterations."""
    template = registry.get("Loop")

    assert template.template_version == 2
    assert "max_iterations" not in template.inputs
    assert {h.name for h in template.handles.outputs} == {"item", "done"}


def test_agent_templates_accept_tools_handle(registry):
    """2.13 — only the tool-capable schemas expose a Tools input."""
    for type_name in ("ReActAgent", "PlanExecuteAgent"):
        handles = registry.get(type_name).handles.inputs
        tools = [h for h in handles if PortType.TOOLS in h.types]
        assert tools, f"{type_name} must accept Tools"

    for type_name in ("ZeroShotAgent", "SelfReflectAgent"):
        handles = registry.get(type_name).handles.inputs
        tools = [h for h in handles if PortType.TOOLS in h.types]
        assert not tools, (
            f"{type_name} must not accept Tools; its graph schema declares supports_tools=False"
        )


def test_options_source_fields_reference_known_sources(registry):
    """2.14 — structural guard: no template may name a source nobody resolves."""
    for template in _all_templates(registry):
        for name, field in template.inputs.items():
            if field.options_source is None:
                continue
            assert field.options_source in KNOWN_OPTIONS_SOURCES, (
                f"{template.type}.{name} names unknown options_source '{field.options_source}'"
            )


def test_every_template_declares_a_known_icon(registry):
    """2.15 — structural guard: a bad icon name renders as a blank node."""
    for template in _all_templates(registry):
        assert template.icon, f"{template.type} declares no icon"
        assert template.icon in ICON_ALLOWLIST, (
            f"{template.type} declares icon '{template.icon}' which is not exported by @opal/icons"
        )


def test_agent_templates_reuse_existing_schema_defaults(registry):
    """2.16 — field defaults must match agents/graphs/schemas.py verbatim.

    Divergence here becomes a migration later, so it is asserted against the
    live schema registry rather than hardcoded strings.
    """
    from agents.graphs.schemas import get_schema

    pairs = [
        ("ZeroShotAgent", "zero_shot"),
        ("ReActAgent", "react"),
        ("PlanExecuteAgent", "plan_execute"),
        ("SelfReflectAgent", "self_reflect"),
    ]
    for type_name, schema_type in pairs:
        template = registry.get(type_name)
        schema = get_schema(schema_type)
        assert schema is not None

        for field_name, spec in schema.config_schema.items():
            if field_name not in template.inputs:
                continue
            expected = spec.get("default")
            if expected is None:
                continue
            assert template.inputs[field_name].value == expected, (
                f"{type_name}.{field_name} default {template.inputs[field_name].value!r} "
                f"diverges from {schema_type} schema default {expected!r}"
            )


def test_router_declares_its_dynamic_expansion_and_columns():
    """The canvas must learn Router's shape from the template, not from a
    hardcoded per-type map on its own side."""
    template = get_registry().get("Router")
    handle = template.handles.outputs[0]
    assert handle.expands_from == "routes"
    assert handle.expands_label_key == "route"


def test_router_v2_declares_operator_columns():
    """v2: a route row is an operator comparison, not a truthy scratch key.
    The canvas learns the four columns from the template."""
    template = get_registry().get("Router")
    assert template.template_version == 2
    columns = template.inputs["routes"].columns
    assert [c.name for c in columns] == ["source", "operator", "match_text", "route"]


def test_conditional_router_hides_case_sensitive_for_regex():
    """Exact Langflow parity: ConditionalRouterComponent.update_build_config
    pops case_sensitive when the operator is regex."""
    template = get_registry().get("ConditionalRouter")
    rule = template.inputs["case_sensitive"].show_when
    assert rule is not None
    assert rule.field == "operator"
    assert rule.not_equals == "regex"


def test_smart_router_expands_a_port_per_route():
    template = get_registry().get("SmartRouter")
    routes_handle = next(h for h in template.handles.outputs if h.expands_from)
    assert routes_handle.expands_from == "routes"
    assert routes_handle.expands_label_key == "route_category"
    assert [c.name for c in template.inputs["routes"].columns] == [
        "route_category",
        "route_description",
        "output_value",
    ]


def test_smart_router_else_output_is_declared_conditionally():
    template = get_registry().get("SmartRouter")
    else_handle = next(h for h in template.handles.outputs if h.name == "else")
    assert else_handle.show_when is not None
    assert else_handle.show_when.field == "enable_else_output"
    assert else_handle.show_when.equals is True


def test_guardrails_offers_langflows_six_checks():
    template = get_registry().get("Guardrails")
    assert template.inputs["enabled_guardrails"].options == [
        "PII",
        "Tokens/Passwords",
        "Jailbreak",
        "Offensive Content",
        "Malicious Code",
        "Prompt Injection",
    ]
    # Langflow's own default: the three that block a leak or a takeover.
    assert template.inputs["enabled_guardrails"].value == [
        "PII",
        "Tokens/Passwords",
        "Jailbreak",
    ]


def test_guardrails_publishes_two_verdict_branches_and_a_record():
    template = get_registry().get("Guardrails")
    outputs = {h.name: h for h in template.handles.outputs}
    assert set(outputs) == {"pass_result", "fail_result", "data_result"}
    assert outputs["pass_result"].types == [PortType.MESSAGE]
    # Result Data is JSON, not a third branch — it carries the verdict record.
    assert outputs["data_result"].types == [PortType.DATA]


def test_the_custom_guardrail_description_appears_only_when_it_is_enabled():
    field = get_registry().get("Guardrails").inputs["custom_guardrail_explanation"]
    assert field.show_when is not None
    assert field.show_when.field == "enable_custom_guardrail"
    assert field.show_when.equals is True


def test_the_guardrails_threshold_is_a_bounded_slider():
    field = get_registry().get("Guardrails").inputs["heuristic_threshold"]
    assert (field.type, field.min, field.max, field.value) == (FieldType.SLIDER, 0, 1, 0.7)


def test_guardrails_is_not_offered_as_an_agent_tool():
    """It branches; an agent calling it would have nowhere to send the verdict."""
    assert get_registry().get("Guardrails").tool_mode_field is None


def test_human_input_expands_a_branch_per_action():
    template = get_registry().get("HumanInput")
    decisions_handle = next(h for h in template.handles.outputs if h.expands_from)
    assert decisions_handle.expands_from == "decisions"
    assert decisions_handle.expands_label_key == "label"
    fallback = next(h for h in template.handles.outputs if h.name == "unmatched")
    assert fallback.show_when is not None
    assert fallback.show_when.field == "enable_unmatched"


# ---------------------------------------------------------------------------
# tool_mode — decision 6.2
# ---------------------------------------------------------------------------

TOOL_MODE_TYPES = {
    "WebSearch",
    "FetchWebpage",
    "ContentCrawl",
    "DocumentSearch",
    "KnowledgeBase",
    "GraphSearch",
    "GraphEntitySearch",
    "GraphNeighborhood",
    "GraphStats",
    "Operations",
    "SplitText",
    "TypeConverter",
    "Parser",
    "StructuredOutput",
    "RunFlow",
}


def test_exactly_the_intended_components_declare_tool_mode():
    """A component that does not declare this does not have the capability —
    it is not a partial version of one."""
    registry = get_registry()
    declaring = {
        t.type
        for templates in registry.list_grouped().values()
        for t in templates
        if t.tool_mode_field
    }
    assert declaring == TOOL_MODE_TYPES


def test_no_control_flow_component_can_become_a_tool():
    registry = get_registry()
    for control_type in (
        "ChatInput",
        "ChatOutput",
        "Router",
        "ConditionalRouter",
        "Loop",
        "While",
        "Merge",
        "HumanInput",
        "SmartRouter",
    ):
        assert registry.get(control_type).tool_mode_field is None, control_type


def test_a_tool_mode_component_offers_a_tool_output_only_in_tool_mode():
    from domain.flows.handles import effective_output_handles

    for component_type in sorted(TOOL_MODE_TYPES):
        template = get_registry().get(component_type)
        off = {h.name for h in effective_output_handles(template, {"tool_mode": False})}
        on = {h.name for h in effective_output_handles(template, {"tool_mode": True})}
        assert "tool" not in off, component_type
        assert "tool" in on, component_type


def test_a_plain_output_is_hidden_in_tool_mode():
    """`ShowWhen` tests one field, so a handle whose visibility already depends
    on another one (Data Operations' typed outputs, Type Convert's) keeps that
    rule and can still appear. Wiring it on a tool-mode node is a validation
    error, which is the real guard; this test pins the common case."""
    from domain.flows.handles import effective_output_handles

    template = get_registry().get("WebSearch")
    on = {h.name for h in effective_output_handles(template, {"tool_mode": True})}
    assert on == {"tool"}


def test_every_tool_mode_component_carries_both_configuration_fields():
    for component_type in sorted(TOOL_MODE_TYPES):
        template = get_registry().get(component_type)
        assert "tool_mode" in template.inputs, component_type
        assert "tool_name" in template.inputs, component_type


# ---------------------------------------------------------------------------
# Table column types
#
# Langflow's TableInput gives each column a type and, where it applies, its
# options. Without that every cell is a free-text box — which is how a Router
# operator typo became possible in the first place.
# ---------------------------------------------------------------------------


def _column(component_type: str, field: str, column: str):
    template = get_registry().get(component_type)
    return next(c for c in template.inputs[field].columns if c.name == column)


def test_the_router_operator_column_offers_the_comparison_operators():
    from domain.flows.comparison import CONDITION_OPERATORS

    column = _column("Router", "routes", "operator")
    assert column.type == FieldType.OPTIONS
    assert column.options == list(CONDITION_OPERATORS)


def test_the_structured_output_type_column_offers_the_schema_types():
    from domain.flows.output_schema import SCHEMA_TYPES

    column = _column("StructuredOutput", "output_schema", "type")
    assert column.type == FieldType.OPTIONS
    assert column.options == sorted(SCHEMA_TYPES)


def test_the_structured_output_multiple_column_is_a_boolean():
    assert _column("StructuredOutput", "output_schema", "multiple").type == FieldType.BOOL


def test_a_free_text_column_stays_free_text():
    """Not every column should be constrained: a category name or an action
    label is whatever the author types."""
    assert _column("SmartRouter", "routes", "route_category").type == FieldType.STR
    assert _column("HumanInput", "decisions", "label").type == FieldType.STR
    assert _column("Router", "routes", "match_text").type == FieldType.STR
