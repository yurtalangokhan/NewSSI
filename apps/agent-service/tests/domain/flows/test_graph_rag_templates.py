"""Tests for Graph RAG templates.

Spec: .tmp/flow-canvas-design.md section 7.1.
Brief: .tmp/flow-canvas-task-33-brief.md
"""

from __future__ import annotations

import pytest

from domain.flows.registry import get_registry
from domain.flows.sources import KNOWN_OPTIONS_SOURCES
from domain.flows.templates.icons import ICON_ALLOWLIST
from models.flows import ComponentKind

GRAPH_RAG_TYPES = [
    "GraphSearch",
    "GraphEntitySearch",
    "GraphNeighborhood",
    "GraphStats",
]


@pytest.fixture
def registry():
    return get_registry()


def test_graph_rag_templates_registered(registry):
    """33.1 — 4 Graph RAG templates registered in knowledge category."""
    for type_name in GRAPH_RAG_TYPES:
        template = registry.get(type_name)
        assert template is not None
        assert template.category == "knowledge"
        assert template.kind == ComponentKind.EXECUTION


def test_graph_rag_icons_in_allowlist(registry):
    """33.2 — All Graph RAG template icons are in the allowlist."""
    for type_name in GRAPH_RAG_TYPES:
        template = registry.get(type_name)
        assert template.icon in ICON_ALLOWLIST, (
            f"{type_name} icon '{template.icon}' not in allowlist"
        )


def test_graph_rag_collection_options_source(registry):
    """33.3 — All Graph RAG templates use rag.graph_collections source."""
    for type_name in GRAPH_RAG_TYPES:
        template = registry.get(type_name)
        assert "collection" in template.inputs
        field = template.inputs["collection"]
        assert field.options_source == "rag.graph_collections"
        assert field.options_source in KNOWN_OPTIONS_SOURCES


def test_graph_rag_handle_specifications(registry):
    """33.4 — Graph RAG handles match design specs."""
    # GraphSearch: query -> graph_data
    gs = registry.get("GraphSearch")
    assert any(h.name == "query" for h in gs.handles.inputs)
    assert any(h.name == "graph_data" for h in gs.handles.outputs)

    # GraphEntitySearch: query -> entities
    ges = registry.get("GraphEntitySearch")
    assert any(h.name == "query" for h in ges.handles.inputs)
    assert any(h.name == "entities" for h in ges.handles.outputs)

    # GraphNeighborhood: entity_id -> subgraph
    gn = registry.get("GraphNeighborhood")
    assert any(h.name == "entity_id" for h in gn.handles.inputs)
    assert any(h.name == "subgraph" for h in gn.handles.outputs)

    # GraphStats: outputs stats
    gst = registry.get("GraphStats")
    assert any(h.name == "stats" for h in gst.handles.outputs)
