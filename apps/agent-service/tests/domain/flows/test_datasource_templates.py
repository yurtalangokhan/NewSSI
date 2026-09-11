"""Tests for datasource component templates and options sources (P8 Task 47).

Spec: .tmp/flow-canvas-design.md section 7.6.
Brief: .tmp/flow-canvas-task-47-brief.md
"""

from __future__ import annotations

from domain.flows.registry import get_registry
from domain.flows.templates.icons import ICON_ALLOWLIST
from domain.flows.validator import validate
from models.flows import ComponentKind, FlowEdge, FlowNode, FlowSpec, PortType


def test_datasource_templates_register_without_error():
    """47.1 — Registry accepts both datasource templates."""
    reg = get_registry()
    ad = reg.get("AirbyteDatasource")
    st = reg.get("SyncTrigger")

    assert ad.category == "datasources"
    assert st.category == "datasources"


def test_airbyte_datasource_is_resource_emits_data():
    """47.2 — AirbyteDatasource is ComponentKind.RESOURCE and emits Data output."""
    reg = get_registry()
    ad = reg.get("AirbyteDatasource")
    assert ad.kind == ComponentKind.RESOURCE
    assert len(ad.handles.outputs) == 1
    assert ad.handles.outputs[0].name == "data"
    assert PortType.DATA in ad.handles.outputs[0].types


def test_sync_trigger_is_execution_with_trigger_input():
    """47.3 — SyncTrigger is ComponentKind.EXECUTION with Trigger-typed input handle."""
    reg = get_registry()
    st = reg.get("SyncTrigger")
    assert st.kind == ComponentKind.EXECUTION
    assert len(st.handles.inputs) == 1
    assert st.handles.inputs[0].name == "trigger"
    assert PortType.TRIGGER in st.handles.inputs[0].types


def test_required_datasource_id_field_fails_generic_validation_when_unset():
    """47.10 — Generic validator rejects SyncTrigger or AirbyteDatasource if datasource_id is unset."""
    spec = FlowSpec(
        nodes=[
            FlowNode(id="in", type="ChatInput", values={}),
            FlowNode(id="st_1", type="SyncTrigger", values={}),
            FlowNode(id="out", type="ChatOutput", values={}),
        ],
        edges=[
            FlowEdge(
                id="e1", source="in", source_handle="output", target="st_1", target_handle="trigger"
            ),
            FlowEdge(
                id="e2", source="st_1", source_handle="result", target="out", target_handle="input"
            ),
        ],
    )
    result = validate(spec)
    assert result.valid is False
    assert any(
        "datasource_id" in issue.message or "st_1" in (issue.node_id or "")
        for issue in result.errors
    )


def test_new_icons_are_in_the_allowlist():
    """47.11 — Icons declared by datasource templates exist in ICON_ALLOWLIST."""
    reg = get_registry()
    for name in ("AirbyteDatasource", "SyncTrigger"):
        template = reg.get(name)
        assert template.icon in ICON_ALLOWLIST
