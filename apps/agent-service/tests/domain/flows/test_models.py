"""Tests for FlowSpec and ComponentTemplate models.

Spec: .tmp/flow-canvas-design.md sections 4.2 and 4.4.
Brief: .tmp/flow-canvas-task-1-brief.md
"""

import pytest
from pydantic import ValidationError

from models.flows import (
    ComponentTemplate,
    FlowEdge,
    FlowNode,
    FlowSpec,
    InputField,
)


def _minimal_spec_dict() -> dict:
    return {
        "version": "1.0",
        "nodes": [
            {"id": "chat_input-a1", "type": "ChatInput", "position": {"x": 0, "y": 120}},
            {
                "id": "agent-b2",
                "type": "ReActAgent",
                "position": {"x": 320, "y": 120},
                "values": {"system_prompt": "You are helpful.", "max_iterations": 6},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source": "chat_input-a1",
                "sourceHandle": "message",
                "target": "agent-b2",
                "targetHandle": "input",
            }
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def _template_dict(**overrides) -> dict:
    base = {
        "type": "GraphRagSearch",
        "category": "knowledge",
        "display_name": "Graph RAG Search",
        "description": "Hybrid vector + graph traversal search with RRF fusion.",
        "icon": "SvgNetworkGraph",
        "kind": "execution",
        "inputs": {
            "collection_id": {
                "type": "options",
                "display_name": "Graph collection",
                "required": True,
                "options_source": "rag.graph_collections",
            }
        },
        "handles": {
            "inputs": [{"name": "query", "types": ["Message", "Text"]}],
            "outputs": [{"name": "documents", "types": ["Documents"]}],
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# FlowSpec
# ---------------------------------------------------------------------------


def test_flow_spec_parses_minimal_valid_spec():
    """1.1 — two nodes and one edge round-trip through FlowSpec."""
    spec = FlowSpec.model_validate(_minimal_spec_dict())

    assert len(spec.nodes) == 2
    assert len(spec.edges) == 1
    assert spec.nodes[0].id == "chat_input-a1"
    assert spec.nodes[1].values["max_iterations"] == 6
    assert spec.viewport is not None
    assert spec.viewport.zoom == 1


def test_flow_spec_rejects_duplicate_node_ids():
    """1.2 — duplicate node ids must be impossible to construct."""
    data = _minimal_spec_dict()
    data["nodes"][1]["id"] = data["nodes"][0]["id"]

    with pytest.raises(ValidationError) as exc:
        FlowSpec.model_validate(data)

    assert "chat_input-a1" in str(exc.value)


def test_flow_spec_rejects_edge_referencing_unknown_node():
    """1.3 — dangling edges must be impossible to construct."""
    data = _minimal_spec_dict()
    data["edges"][0]["target"] = "does-not-exist"

    with pytest.raises(ValidationError) as exc:
        FlowSpec.model_validate(data)

    assert "does-not-exist" in str(exc.value)


def test_flow_edge_uses_camel_case_handle_aliases():
    """1.4 — @xyflow/react emits sourceHandle/targetHandle; match it both ways."""
    edge = FlowEdge.model_validate(
        {
            "id": "e1",
            "source": "a",
            "sourceHandle": "out",
            "target": "b",
            "targetHandle": "in",
        }
    )

    assert edge.source_handle == "out"
    assert edge.target_handle == "in"

    dumped = edge.model_dump(by_alias=True)
    assert dumped["sourceHandle"] == "out"
    assert dumped["targetHandle"] == "in"
    assert "source_handle" not in dumped


def test_flow_node_defaults_template_version_to_one():
    """1.5 — omitted template_version defaults to 1."""
    node = FlowNode.model_validate({"id": "n1", "type": "ChatInput"})

    assert node.template_version == 1
    assert node.values == {}


def test_flow_spec_round_trips_without_loss():
    """1.6 — parse(dump(spec)) == spec, viewport included."""
    spec = FlowSpec.model_validate(_minimal_spec_dict())

    reparsed = FlowSpec.model_validate(spec.model_dump(by_alias=True))

    assert reparsed == spec


# ---------------------------------------------------------------------------
# ComponentTemplate
# ---------------------------------------------------------------------------


def test_component_template_requires_at_least_one_handle():
    """1.7 — a template with no input and no output handles is unusable."""
    data = _template_dict(handles={"inputs": [], "outputs": []})

    with pytest.raises(ValidationError) as exc:
        ComponentTemplate.model_validate(data)

    assert "handle" in str(exc.value).lower()


def test_input_field_rejects_unknown_field_type():
    """1.8 — unknown field types must fail with the valid set named."""
    with pytest.raises(ValidationError) as exc:
        InputField.model_validate({"type": "wysiwyg", "display_name": "Nope"})

    assert "wysiwyg" in str(exc.value)


def test_slider_field_requires_min_and_max():
    """1.9 — a slider without bounds cannot be rendered."""
    with pytest.raises(ValidationError) as exc:
        InputField.model_validate({"type": "slider", "display_name": "Weight"})

    message = str(exc.value).lower()
    assert "min" in message and "max" in message


def test_options_field_accepts_a_static_option_list():
    """1.11 — not every dropdown is user data; some are fixed sets."""
    field = InputField.model_validate(
        {
            "type": "options",
            "display_name": "Merge strategy",
            "options": ["concat", "first", "last"],
            "value": "concat",
        }
    )

    assert field.options == ["concat", "first", "last"]
    assert field.options_source is None


def test_options_field_requires_either_static_options_or_a_source():
    """1.12 — a dropdown with nothing to show cannot be rendered."""
    with pytest.raises(ValidationError) as exc:
        InputField.model_validate({"type": "options", "display_name": "Empty"})

    message = str(exc.value).lower()
    assert "options" in message and "options_source" in message


def test_component_template_defaults_lifecycle_to_stable():
    """1.10 — omitted lifecycle defaults to stable."""
    template = ComponentTemplate.model_validate(_template_dict())

    assert template.lifecycle == "stable"
    assert template.template_version == 1
