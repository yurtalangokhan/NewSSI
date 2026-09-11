"""Tests for MailConfig validation rules in flows.

Spec: .tmp/flow-canvas-design.md sections 4.7 (FLOW_MAIL_CONFIG_REQUIRED).
Brief: .tmp/flow-canvas-task-30-brief.md
"""

from __future__ import annotations

from domain.flows.validator import FLOW_MAIL_CONFIG_REQUIRED, validate
from models.flows import FlowSpec


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


def test_mail_tools_without_a_wired_mail_config_fails_validation():
    """30.4 — MailTools with send_email enabled but no incoming MailConfig fails."""
    spec = _make_flow(
        nodes=[
            {
                "id": "mail-tools-1",
                "type": "MailTools",
                "values": {"tools": ["send_email"]},
            }
        ]
    )
    res = validate(spec)
    assert res.valid is False
    codes = [e.code for e in res.errors]
    assert FLOW_MAIL_CONFIG_REQUIRED in codes


def test_mail_tools_with_a_wired_mail_config_passes():
    """30.5 — MailTools with send_email and a configured wired MailConfig passes."""
    spec = _make_flow(
        nodes=[
            {
                "id": "mail-cfg",
                "type": "MailConfig",
                "values": {"config_id": "smtp-cfg-123"},
            },
            {
                "id": "mail-tools-1",
                "type": "MailTools",
                "values": {"tools": ["send_email"]},
            },
        ],
        edges=[
            {
                "id": "e_mc",
                "source": "mail-cfg",
                "sourceHandle": "data",
                "target": "mail-tools-1",
                "targetHandle": "mail_config",
            }
        ],
    )
    res = validate(spec)
    assert res.valid is True


def test_mail_config_node_with_empty_config_id_fails_validation():
    """30.6 — Wired MailConfig node with empty/missing config_id fails validation."""
    spec = _make_flow(
        nodes=[
            {
                "id": "mail-cfg",
                "type": "MailConfig",
                "values": {"config_id": ""},
            },
            {
                "id": "mail-tools-1",
                "type": "MailTools",
                "values": {"tools": ["send_email"]},
            },
        ],
        edges=[
            {
                "id": "e_mc",
                "source": "mail-cfg",
                "sourceHandle": "data",
                "target": "mail-tools-1",
                "targetHandle": "mail_config",
            }
        ],
    )
    res = validate(spec)
    assert res.valid is False
    codes = [e.code for e in res.errors]
    assert FLOW_MAIL_CONFIG_REQUIRED in codes


def test_mail_tools_without_send_email_selected_needs_no_config():
    """30.7 — MailTools with other tools (e.g. read_email) but not send_email needs no config."""
    spec = _make_flow(
        nodes=[
            {
                "id": "mail-tools-1",
                "type": "MailTools",
                "values": {"tools": ["read_email", "search_emails"]},
            }
        ]
    )
    res = validate(spec)
    assert res.valid is True


def test_classic_shaped_mail_config_rule_still_applies():
    """30.8 — Regression: classic-shaped values on agent node still checked."""
    spec = _make_flow(
        nodes=[
            {
                "id": "agent-1",
                "type": "ReActAgent",
                "values": {"mcp_tools": ["send_email"], "mcp_tool_configs": {}},
            }
        ]
    )
    res = validate(spec)
    assert res.valid is False
    codes = [e.code for e in res.errors]
    assert FLOW_MAIL_CONFIG_REQUIRED in codes
