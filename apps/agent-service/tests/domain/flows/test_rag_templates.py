"""Tests for Vector RAG templates.

Spec: .tmp/flow-canvas-design.md section 7.2.
Brief: .tmp/flow-canvas-task-32-brief.md
"""

from __future__ import annotations

import pytest

from domain.flows.registry import get_registry
from domain.flows.sources import KNOWN_OPTIONS_SOURCES
from domain.flows.templates.icons import ICON_ALLOWLIST
from models.flows import ComponentKind, PortType


@pytest.fixture
def registry():
    return get_registry()


def test_rag_templates_registered(registry):
    """32.1 — DocumentSearch and DocumentContext templates are registered."""
    doc_search = registry.get("DocumentSearch")
    doc_context = registry.get("DocumentContext")
    assert doc_search is not None
    assert doc_context is not None
    assert doc_search.category == "knowledge"
    assert doc_context.category == "knowledge"


def test_document_search_template_specification(registry):
    """32.2 — DocumentSearch inputs and handles match spec."""
    t = registry.get("DocumentSearch")
    assert t.kind == ComponentKind.EXECUTION
    assert "collection" in t.inputs
    assert t.inputs["collection"].options_source == "rag.collections"
    assert t.inputs["collection"].options_source in KNOWN_OPTIONS_SOURCES
    assert t.icon in ICON_ALLOWLIST

    in_handle = next(h for h in t.handles.inputs if h.name == "query")
    assert PortType.DATA in in_handle.types or PortType.MESSAGE in in_handle.types

    out_handle = next(h for h in t.handles.outputs if h.name == "documents")
    assert PortType.DATA in out_handle.types


def test_document_context_template_specification(registry):
    """32.3 — DocumentContext inputs and handles match spec."""
    t = registry.get("DocumentContext")
    assert t.kind == ComponentKind.EXECUTION
    assert t.icon in ICON_ALLOWLIST

    doc_in = next(h for h in t.handles.inputs if h.name == "documents")
    assert PortType.DATA in doc_in.types

    ctx_out = next(h for h in t.handles.outputs if h.name == "context")
    assert PortType.DATA in ctx_out.types or PortType.MESSAGE in ctx_out.types
