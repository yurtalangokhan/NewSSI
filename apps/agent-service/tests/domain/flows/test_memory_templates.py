"""Tests for Memory resource templates.

Spec: .tmp/flow-canvas-design.md section 7.5.
Brief: .tmp/flow-canvas-task-35-brief.md
"""

from __future__ import annotations

import pytest

from domain.flows.registry import get_registry
from domain.flows.templates.icons import ICON_ALLOWLIST
from models.flows import ComponentKind, PortType


@pytest.fixture
def registry():
    return get_registry()


def test_memory_templates_register_without_error(registry):
    """35.1 — Memory templates register in memory category."""
    ltm = registry.get("LongTermMemory")
    assert ltm is not None
    assert ltm.category == "memory"

    tcp = registry.get("ThreadCheckpointer")
    assert tcp is not None
    assert tcp.category == "memory"


def test_long_term_memory_is_a_resource_emitting_memory_port(registry):
    """35.2 — LongTermMemory is kind=RESOURCE and outputs PortType.MEMORY."""
    ltm = registry.get("LongTermMemory")
    assert ltm.kind == ComponentKind.RESOURCE
    assert len(ltm.handles.outputs) == 1
    out_handle = ltm.handles.outputs[0]
    assert out_handle.name == "memory"
    assert PortType.MEMORY in out_handle.types


def test_thread_checkpointer_has_no_inputs(registry):
    """35.3 — ThreadCheckpointer has no inputs (visibility node)."""
    tcp = registry.get("ThreadCheckpointer")
    assert tcp.kind == ComponentKind.RESOURCE
    assert len(tcp.inputs) == 0
    assert len(tcp.handles.inputs) == 0


def test_agent_templates_gained_a_memory_input_handle(registry):
    """35.7 — All four Core agent templates accept PortType.MEMORY input."""
    agent_types = ["ZeroShotAgent", "ReActAgent", "PlanExecuteAgent", "SelfReflectAgent"]
    for at in agent_types:
        template = registry.get(at)
        assert template is not None
        assert any(
            h.name == "memory" and PortType.MEMORY in h.types for h in template.handles.inputs
        ), f"{at} is missing memory input handle"


def test_new_icons_are_in_the_allowlist(registry):
    """35.10 — New memory and agent icons are in the allowlist."""
    ltm = registry.get("LongTermMemory")
    tcp = registry.get("ThreadCheckpointer")
    aref = registry.get("AgentRef")
    assert ltm.icon in ICON_ALLOWLIST
    assert tcp.icon in ICON_ALLOWLIST
    assert aref.icon in ICON_ALLOWLIST
