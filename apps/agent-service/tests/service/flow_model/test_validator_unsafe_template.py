"""Tests for PromptTemplate template validation. Spec T1
(FLOW_UNSAFE_TEMPLATE): a template shaped like
"{x.__init__.__globals__[os].environ}" must fail validation at save time,
not reach safe_format at run time.
"""

from __future__ import annotations

from schemas.flows import FlowSpec
from service.flow_model.validator import FLOW_UNSAFE_TEMPLATE, validate


def _make_flow(nodes, edges=None):
    base_nodes = [
        {"id": "in", "type": "ChatInput"},
        {"id": "out", "type": "ChatOutput"},
    ]
    base_edges = [
        {
            "id": "e_io",
            "source": "in",
            "sourceHandle": "message",
            "target": "out",
            "targetHandle": "message",
        }
    ]
    return FlowSpec.model_validate(
        {
            "nodes": base_nodes + nodes,
            "edges": base_edges + (edges or []),
        }
    )


def test_plain_template_passes_validation():
    spec = _make_flow(
        nodes=[
            {
                "id": "pt-1",
                "type": "PromptTemplate",
                "values": {"template": "Hello {name}, welcome to {place}"},
            }
        ]
    )
    res = validate(spec)
    codes = [e.code for e in res.errors]
    assert FLOW_UNSAFE_TEMPLATE not in codes


def test_attribute_traversal_template_fails_validation():
    spec = _make_flow(
        nodes=[
            {
                "id": "pt-1",
                "type": "PromptTemplate",
                "values": {"template": "{x.__init__.__globals__[os].environ}"},
            }
        ]
    )
    res = validate(spec)
    assert res.valid is False
    codes = [e.code for e in res.errors]
    assert FLOW_UNSAFE_TEMPLATE in codes


def test_empty_template_needs_no_check():
    spec = _make_flow(nodes=[{"id": "pt-1", "type": "PromptTemplate", "values": {"template": ""}}])
    res = validate(spec)
    codes = [e.code for e in res.errors]
    assert FLOW_UNSAFE_TEMPLATE not in codes
