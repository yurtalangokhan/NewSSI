"""Tests for the flow validator — one test per design spec section 4.7 row.

Two rules reference node shapes that have no registered template yet:
AgentRef (P6) and the send_email/mail_config MCP tool node (P5). Both rules
are implemented generically against the *shape* of ``node.values`` rather
than a specific ``node.type``, so they are exercised here against a
stand-in registered type (``ReActAgent``) carrying those keys — the same
pattern Task 2 used for icon validation and Task 4 uses for migration
fixtures. See ``.tmp/flow-canvas-task-3-report.md``.

Brief: .tmp/flow-canvas-task-3-brief.md
"""

import pytest

from domain.flows.validator import (
    FLOW_CONDROUTER_DEFAULT_LOOPS,
    FLOW_CONDROUTER_MISSING_BRANCH,
    FLOW_FOREACH_BODY_NOT_LOOPING,
    FLOW_FOREACH_MISSING_BRANCH,
    FLOW_GUARDRAILS_MISSING_BRANCH,
    FLOW_GUARDRAILS_NO_CHECK,
    FLOW_HUMAN_INPUT_MISSING_ACTION,
    FLOW_HUMAN_INPUT_UNMATCHED_DISABLED,
    FLOW_ILLEGAL_CYCLE,
    FLOW_INVALID_OPTION,
    FLOW_INVALID_VARIABLE_NAME,
    FLOW_MAIL_CONFIG_REQUIRED,
    FLOW_MISSING_INPUT,
    FLOW_MULTIPLE_ENTRY,
    FLOW_NESTED_FLOW_REF,
    FLOW_NESTED_LOOP,
    FLOW_NO_ENTRY,
    FLOW_NO_EXIT,
    FLOW_ORPHAN_NODE,
    FLOW_RUNFLOW_MISSING_TARGET,
    FLOW_SMART_ROUTER_ELSE_DISABLED,
    FLOW_SMART_ROUTER_MISSING_ROUTE,
    FLOW_STRUCTURED_OUTPUT_SCHEMA,
    FLOW_TOOL_MODE_FLOW_EDGE,
    FLOW_TOOL_MODE_UNUSED,
    FLOW_TYPE_MISMATCH,
    FLOW_UNBOUNDED_LOOP,
    FLOW_UNKNOWN_COMPONENT,
    validate,
)
from models.flows import FlowEdge, FlowNode, FlowSpec


def _valid_flow_dict() -> dict:
    """ChatInput -> ReActAgent -> ChatOutput. Zero errors, zero warnings."""
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "agent-1", "type": "ReActAgent", "values": {"system_prompt": "Be helpful."}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "agent-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


def test_flow_without_chat_input_is_invalid():
    """3.8 — exactly one entry point is required."""
    spec = FlowSpec.model_validate({"nodes": [{"id": "out-1", "type": "ChatOutput"}], "edges": []})

    result = validate(spec)

    assert result.valid is False
    assert any(e.code == FLOW_NO_ENTRY for e in result.errors)


def test_flow_with_two_chat_inputs_is_invalid():
    """3.9 — more than one entry point is ambiguous."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {"id": "in-2", "type": "ChatInput"},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [],
        }
    )

    result = validate(spec)

    assert any(e.code == FLOW_MULTIPLE_ENTRY for e in result.errors)
    assert not any(e.code == FLOW_NO_ENTRY for e in result.errors)


def test_flow_without_reachable_chat_output_is_invalid():
    """3.10 — a Chat Output that exists but isn't wired doesn't count."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [],
        }
    )

    result = validate(spec)

    assert any(e.code == FLOW_NO_EXIT for e in result.errors)


def test_unreachable_execution_node_produces_warning():
    """3.11 — an orphan node is a warning, not a save-blocking error."""
    data = _valid_flow_dict()
    data["nodes"].append({"id": "orphan-1", "type": "TextInput", "values": {"text": "hi"}})
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert result.valid is True
    assert any(w.code == FLOW_ORPHAN_NODE and w.node_id == "orphan-1" for w in result.warnings)


def test_edge_between_incompatible_handles_is_invalid():
    """3.12 — Data cannot flow into a Message-only handle (the coercion is
    asymmetric: Data accepts anything, but nothing accepts Data)."""
    data = {
        "nodes": [
            {"id": "file-1", "type": "FileInput", "values": {"file": {"name": "x"}}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "file-1",
                "sourceHandle": "data",
                "target": "out-1",
                "targetHandle": "message",
            }
        ],
    }
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert any(e.code == FLOW_TYPE_MISMATCH and e.edge_id == "e1" for e in result.errors)


def test_missing_required_input_is_invalid():
    """3.13 — FileInput.file has no default; omitting it is an error."""
    data = _valid_flow_dict()
    data["nodes"].append({"id": "file-1", "type": "FileInput"})
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert any(e.code == FLOW_MISSING_INPUT and e.node_id == "file-1" for e in result.errors)


def test_cycle_without_loop_node_is_invalid():
    """3.14 — a cycle with no Loop node is a deadlock risk (R2)."""
    data = {
        "nodes": [
            {"id": "a", "type": "ReActAgent", "values": {"system_prompt": "A"}},
            {"id": "b", "type": "Merge"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "a",
                "sourceHandle": "output",
                "target": "b",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "b",
                "sourceHandle": "output",
                "target": "a",
                "targetHandle": "input",
            },
        ],
    }
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert any(e.code == FLOW_ILLEGAL_CYCLE for e in result.errors)


def test_cycle_through_loop_node_is_valid():
    """3.15 — a Loop's own back-edge is the sanctioned exception."""
    data = {
        "nodes": [
            {"id": "a", "type": "ReActAgent", "values": {"system_prompt": "A"}},
            {"id": "loop-1", "type": "While", "values": {"condition": "x", "max_iterations": 3}},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "a",
                "sourceHandle": "output",
                "target": "loop-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "loop-1",
                "sourceHandle": "continue",
                "target": "a",
                "targetHandle": "input",
            },
        ],
    }
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert not any(e.code == FLOW_ILLEGAL_CYCLE for e in result.errors)


def test_loop_without_max_iterations_is_invalid():
    """3.16 — an explicit null bound is the deadlock risk R2 exists to catch."""
    data = {
        "nodes": [
            {"id": "a", "type": "ReActAgent", "values": {"system_prompt": "A"}},
            {
                "id": "loop-1",
                "type": "While",
                "values": {"condition": "x", "max_iterations": None},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source": "a",
                "sourceHandle": "output",
                "target": "loop-1",
                "targetHandle": "input",
            },
        ],
    }
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert any(e.code == FLOW_UNBOUNDED_LOOP and e.node_id == "loop-1" for e in result.errors)


# ---------------------------------------------------------------------------
# ConditionalRouter ("If-Else")
# ---------------------------------------------------------------------------


def _condrouter_flow_dict(**cr_values) -> dict:
    """ChatInput -> If-Else -[true]-> ChatOutput
    -[false]-> Agent -> (back to If-Else)."""
    values = {
        "operator": "contains",
        "match_text": "DONE",
        "max_iterations": 3,
        "default_route": "true_result",
    }
    values.update(cr_values)
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "cr-1", "type": "ConditionalRouter", "values": values},
            {"id": "agent-1", "type": "ReActAgent", "values": {"system_prompt": "A"}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "cr-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "cr-1",
                "sourceHandle": "true_result",
                "target": "out-1",
                "targetHandle": "message",
            },
            {
                "id": "e3",
                "source": "cr-1",
                "sourceHandle": "false_result",
                "target": "agent-1",
                "targetHandle": "input",
            },
            {
                "id": "e4",
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "cr-1",
                "targetHandle": "input",
            },
        ],
    }


def test_conditional_router_loop_is_valid():
    """A ConditionalRouter's own back-edge is a sanctioned cycle, like Loop's."""
    spec = FlowSpec.model_validate(_condrouter_flow_dict())

    result = validate(spec)

    assert result.valid is True, result.errors
    assert result.errors == []


def test_conditional_router_missing_branch_is_invalid():
    data = _condrouter_flow_dict()
    data["edges"] = [e for e in data["edges"] if e["id"] != "e3"]  # drop false_result
    data["nodes"] = [n for n in data["nodes"] if n["id"] != "agent-1"]
    data["edges"] = [e for e in data["edges"] if e["id"] != "e4"]
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert any(
        e.code == FLOW_CONDROUTER_MISSING_BRANCH and e.node_id == "cr-1" for e in result.errors
    )


def test_conditional_router_without_max_iterations_is_invalid():
    spec = FlowSpec.model_validate(_condrouter_flow_dict(max_iterations=None))

    result = validate(spec)

    assert any(e.code == FLOW_UNBOUNDED_LOOP and e.node_id == "cr-1" for e in result.errors)


def test_conditional_router_unknown_operator_is_invalid():
    spec = FlowSpec.model_validate(_condrouter_flow_dict(operator="sounds_like"))

    result = validate(spec)

    assert any(e.code == FLOW_INVALID_OPTION and e.node_id == "cr-1" for e in result.errors)


def test_conditional_router_default_route_that_loops_is_invalid():
    """default_route must be the branch that leaves the loop — here it is the
    branch wired back upstream, so hitting the bound would never terminate."""
    spec = FlowSpec.model_validate(_condrouter_flow_dict(default_route="false_result"))

    result = validate(spec)

    assert any(
        e.code == FLOW_CONDROUTER_DEFAULT_LOOPS and e.node_id == "cr-1" for e in result.errors
    )


def test_conditional_router_pure_branch_without_cycle_is_valid():
    """No loop-back: default_route can point at either branch."""
    data = {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {
                "id": "cr-1",
                "type": "ConditionalRouter",
                "values": {"match_text": "x", "max_iterations": 5, "default_route": "false_result"},
            },
            {"id": "a", "type": "ReActAgent", "values": {"system_prompt": "A"}},
            {"id": "b", "type": "ReActAgent", "values": {"system_prompt": "B"}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "cr-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "cr-1",
                "sourceHandle": "true_result",
                "target": "a",
                "targetHandle": "input",
            },
            {
                "id": "e3",
                "source": "cr-1",
                "sourceHandle": "false_result",
                "target": "b",
                "targetHandle": "input",
            },
            {
                "id": "e4",
                "source": "a",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
            {
                "id": "e5",
                "source": "b",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert result.valid is True, result.errors


def test_loop_without_condition_is_valid():
    """condition is now optional — an empty one means a plain bounded loop."""
    data = {
        "nodes": [
            {"id": "a", "type": "ReActAgent", "values": {"system_prompt": "A"}},
            {"id": "loop-1", "type": "While", "values": {"max_iterations": 3}},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "a",
                "sourceHandle": "output",
                "target": "loop-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "loop-1",
                "sourceHandle": "continue",
                "target": "a",
                "targetHandle": "input",
            },
        ],
    }
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert not any(e.code == FLOW_MISSING_INPUT and e.node_id == "loop-1" for e in result.errors)


def test_unknown_component_type_is_invalid():
    """3.17 — a node type absent from the registry is caught, named, and
    does not cascade into spurious downstream errors."""
    data = _valid_flow_dict()
    data["nodes"].append({"id": "mystery-1", "type": "TotallyMadeUp"})
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert any(e.code == FLOW_UNKNOWN_COMPONENT and e.node_id == "mystery-1" for e in result.errors)
    assert "TotallyMadeUp" in next(
        e.message for e in result.errors if e.code == FLOW_UNKNOWN_COMPONENT
    )


def test_agent_ref_targeting_a_flow_is_invalid():
    """3.18 — flows cannot reference other flows (design spec 5.4)."""
    data = _valid_flow_dict()
    data["nodes"].append(
        {"id": "ref-1", "type": "ReActAgent", "values": {"agent_id": "flow-agent-1"}}
    )
    spec = FlowSpec.model_validate(data)

    result = validate(spec, is_flow_backed=lambda agent_id: agent_id == "flow-agent-1")

    assert any(e.code == FLOW_NESTED_FLOW_REF and e.node_id == "ref-1" for e in result.errors)


def test_agent_ref_targeting_a_classic_agent_is_valid():
    """3.18b — the allowed direction: referencing a non-flow agent is fine."""
    data = _valid_flow_dict()
    data["nodes"].append(
        {"id": "ref-1", "type": "ReActAgent", "values": {"agent_id": "classic-agent-1"}}
    )
    spec = FlowSpec.model_validate(data)

    result = validate(spec, is_flow_backed=lambda agent_id: False)

    assert not any(e.code == FLOW_NESTED_FLOW_REF for e in result.errors)


def test_send_email_without_mail_config_is_invalid():
    """3.19 — mirrors the existing persona rule: send_email needs a mail config."""
    data = _valid_flow_dict()
    data["nodes"].append(
        {
            "id": "mail-1",
            "type": "ReActAgent",
            "values": {"system_prompt": "x", "mcp_tools": ["send_email"]},
        }
    )
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert any(e.code == FLOW_MAIL_CONFIG_REQUIRED and e.node_id == "mail-1" for e in result.errors)


def test_send_email_with_mail_config_is_valid():
    """3.19b — the satisfied case must not false-positive."""
    data = _valid_flow_dict()
    data["nodes"].append(
        {
            "id": "mail-1",
            "type": "ReActAgent",
            "values": {
                "system_prompt": "x",
                "mcp_tools": ["send_email"],
                "mcp_tool_configs": {"send_email": {"mail_config_id": "cfg-1"}},
            },
        }
    )
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert not any(e.code == FLOW_MAIL_CONFIG_REQUIRED for e in result.errors)


def test_valid_flow_returns_no_errors():
    """3.20 — the happy path."""
    spec = FlowSpec.model_validate(_valid_flow_dict())

    result = validate(spec)

    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []


def test_validator_reports_all_errors_not_just_the_first():
    """3.21 — fixing a canvas one error per round-trip is unusable; report everything."""
    data = {
        "nodes": [
            {"id": "out-1", "type": "ChatOutput"},
            {"id": "mystery-1", "type": "NoSuchThing"},
        ],
        "edges": [],
    }
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    codes = {e.code for e in result.errors}
    assert FLOW_NO_ENTRY in codes
    assert FLOW_UNKNOWN_COMPONENT in codes
    assert len(result.errors) >= 2


# ---------------------------------------------------------------------------
# Bugfix #2 (live API testing) — validator/compiler reachability alignment.
#
# FlowGraphBuilder partitions RESOURCE-kind nodes out of the compiled graph
# and treats every edge touching one as build-time wiring, never a StateGraph
# edge (flow_builder.py build()). The reachability and cycle checks must do
# the same, or a flow like ChatInput → OllamaModel → ChatOutput validates and
# publishes but compiles into a dead-end graph that silently echoes the input.
# ---------------------------------------------------------------------------


def test_exit_reachable_only_through_resource_node_is_invalid():
    """The live bug, verbatim payload: the only path to Chat Output runs
    through a resource node, which the compiler drops from the graph."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {"id": "llm-1", "type": "OllamaModel", "values": {"model": "llama3.1:8b"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "out",
                    "target": "llm-1",
                    "targetHandle": "in",
                },
                {
                    "id": "e2",
                    "source": "llm-1",
                    "sourceHandle": "out",
                    "target": "out-1",
                    "targetHandle": "in",
                },
            ],
        }
    )

    result = validate(spec)

    assert result.valid is False
    assert any(e.code == FLOW_NO_EXIT for e in result.errors)


def test_model_resource_side_wiring_keeps_flow_valid():
    """The intended wiring — model resource feeds the agent's model handle
    while the message chain runs ChatInput → agent → ChatOutput — must stay
    valid, with no orphan warnings for the resource node."""
    data = _valid_flow_dict()
    data["nodes"].append(
        {"id": "model-1", "type": "OllamaModel", "values": {"model": "llama3.1:8b"}}
    )
    data["edges"].append(
        {
            "id": "e-model",
            "source": "model-1",
            "sourceHandle": "model",
            "target": "agent-1",
            "targetHandle": "model",
        }
    )
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []


def test_execution_node_fed_only_by_a_resource_is_orphan():
    """in-1 → LLMModel(resource) → agent-1 → out-1: the agent's only inbound
    path is resource wiring, so in the execution graph it is an orphan and no
    exit is reachable."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {"id": "llm-1", "type": "LLMModel", "values": {"model": "fake"}},
                {"id": "agent-1", "type": "ZeroShotAgent", "values": {"system_prompt": "x"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "llm-1",
                    "targetHandle": "model",
                },
                {
                    "id": "e2",
                    "source": "llm-1",
                    "sourceHandle": "model",
                    "target": "agent-1",
                    "targetHandle": "model",
                },
                {
                    "id": "e3",
                    "source": "agent-1",
                    "sourceHandle": "output",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )

    result = validate(spec)

    assert any(e.code == FLOW_NO_EXIT for e in result.errors)
    assert any(w.code == FLOW_ORPHAN_NODE and w.node_id == "agent-1" for w in result.warnings)


def test_resource_wiring_does_not_create_illegal_cycle():
    """agent-1 → MailTools(resource) → agent-1 is build-time wiring, not an
    execution cycle — the compiler never turns either edge into a graph edge,
    so the cycle check must not flag it."""
    data = _valid_flow_dict()
    data["nodes"].append(
        {"id": "mail-1", "type": "MailTools", "values": {"tools": ["search_email"]}}
    )
    data["edges"] += [
        {
            "id": "e-mail-in",
            "source": "agent-1",
            "sourceHandle": "output",
            "target": "mail-1",
            "targetHandle": "mail_config",
        },
        {
            "id": "e-mail-out",
            "source": "mail-1",
            "sourceHandle": "tools",
            "target": "agent-1",
            "targetHandle": "tools",
        },
    ]
    spec = FlowSpec.model_validate(data)

    result = validate(spec)

    assert not any(e.code == FLOW_ILLEGAL_CYCLE for e in result.errors)
    assert result.valid is True


def test_hidden_required_field_is_not_reported_missing():
    """A field hidden by show_when cannot be filled in, so requiring it would
    be a trap. ConditionalRouter's case_sensitive is hidden for the regex
    operator (Langflow parity)."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {
                    "id": "cr-1",
                    "type": "ConditionalRouter",
                    "values": {
                        "operator": "regex",
                        "match_text": "^ok",
                        "max_iterations": 3,
                        "default_route": "false_result",
                    },
                },
                {"id": "agent-1", "type": "ZeroShotAgent", "values": {"system_prompt": "hi"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "cr-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "cr-1",
                    "sourceHandle": "true_result",
                    "target": "out-1",
                    "targetHandle": "message",
                },
                {
                    "id": "e3",
                    "source": "cr-1",
                    "sourceHandle": "false_result",
                    "target": "agent-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e4",
                    "source": "agent-1",
                    "sourceHandle": "output",
                    "target": "cr-1",
                    "targetHandle": "input",
                },
            ],
        }
    )
    result = validate(spec)
    assert not [i for i in result.errors if i.code == FLOW_MISSING_INPUT]


@pytest.mark.parametrize(
    ("name", "valid"),
    [
        ("tone", True),
        ("tone_2", True),
        ("_internal", False),  # would collide with iteration counter keys
        ("my-var", False),  # would collide with node ids and break {name}
        ("2fast", False),  # not a valid str.format placeholder
        ("", False),
    ],
)
def test_variable_name_rule(name, valid):
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {"id": "set-1", "type": "SetVariable", "values": {"name": name, "value": "x"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "set-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "set-1",
                    "sourceHandle": "output",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )
    issues = [i for i in validate(spec).errors if i.code == FLOW_INVALID_VARIABLE_NAME]
    assert (not issues) == valid


def test_router_branch_edge_to_a_message_input_is_type_valid():
    """Router branch ports carry Message (like If-Else), so routing into an
    agent is not a type mismatch."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {
                    "id": "r",
                    "type": "Router",
                    "template_version": 2,
                    "values": {
                        "routes": [
                            {
                                "source": "x",
                                "operator": "is_truthy",
                                "match_text": "",
                                "route": "left",
                            },
                        ]
                    },
                },
                {"id": "a", "type": "ZeroShotAgent", "values": {"system_prompt": "hi"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "r",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "r",
                    "sourceHandle": "left",
                    "target": "a",
                    "targetHandle": "input",
                },
                {
                    "id": "e3",
                    "source": "r",
                    "sourceHandle": "default",
                    "target": "out-1",
                    "targetHandle": "message",
                },
                {
                    "id": "e4",
                    "source": "a",
                    "sourceHandle": "output",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )
    result = validate(spec)
    assert not [e for e in result.errors if e.code == FLOW_TYPE_MISMATCH]


def _smart_router_flow(*, enable_else, wire_billing=True, wire_else=False) -> dict:
    edges = [
        {
            "id": "e1",
            "source": "in-1",
            "sourceHandle": "message",
            "target": "sr-1",
            "targetHandle": "input",
        },
        {
            "id": "e-agent",
            "source": "a",
            "sourceHandle": "output",
            "target": "out-1",
            "targetHandle": "message",
        },
    ]
    if wire_billing:
        edges.append(
            {
                "id": "e2",
                "source": "sr-1",
                "sourceHandle": "billing",
                "target": "a",
                "targetHandle": "input",
            }
        )
    if wire_else:
        edges.append(
            {
                "id": "e3",
                "source": "sr-1",
                "sourceHandle": "else",
                "target": "out-1",
                "targetHandle": "message",
            }
        )
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {
                "id": "sr-1",
                "type": "SmartRouter",
                "values": {
                    "enable_else_output": enable_else,
                    "routes": [{"route_category": "billing", "route_description": "x"}],
                },
            },
            {"id": "a", "type": "ZeroShotAgent", "values": {"system_prompt": "hi"}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": edges,
    }


def test_smart_router_unwired_category_is_invalid():
    spec = FlowSpec.model_validate(_smart_router_flow(enable_else=False, wire_billing=False))
    result = validate(spec)
    assert any(e.code == FLOW_SMART_ROUTER_MISSING_ROUTE for e in result.errors)


def test_smart_router_else_edge_without_the_toggle_is_invalid():
    spec = FlowSpec.model_validate(_smart_router_flow(enable_else=False, wire_else=True))
    result = validate(spec)
    assert any(e.code == FLOW_SMART_ROUTER_ELSE_DISABLED for e in result.errors)


def test_smart_router_fully_wired_with_else_enabled_is_clean():
    spec = FlowSpec.model_validate(_smart_router_flow(enable_else=True, wire_else=True))
    result = validate(spec)
    assert not [
        e
        for e in result.errors
        if e.code in (FLOW_SMART_ROUTER_MISSING_ROUTE, FLOW_SMART_ROUTER_ELSE_DISABLED)
    ]


def _foreach_flow(*, wire_item=True, wire_done=True, body_loops_back=True, nested=False) -> dict:
    nodes = [
        {"id": "in-1", "type": "ChatInput"},
        {"id": "loop-1", "type": "Loop", "template_version": 2, "values": {"items_source": ""}},
        {"id": "body", "type": "ZeroShotAgent", "values": {"system_prompt": "hi"}},
        {"id": "out-1", "type": "ChatOutput"},
    ]
    edges = [
        {
            "id": "e1",
            "source": "in-1",
            "sourceHandle": "message",
            "target": "loop-1",
            "targetHandle": "input",
        },
    ]
    if wire_item:
        edges.append(
            {
                "id": "e2",
                "source": "loop-1",
                "sourceHandle": "item",
                "target": "body",
                "targetHandle": "input",
            }
        )
    if wire_done:
        edges.append(
            {
                "id": "e4",
                "source": "loop-1",
                "sourceHandle": "done",
                "target": "out-1",
                "targetHandle": "message",
            }
        )
    if body_loops_back:
        edges.append(
            {
                "id": "e3",
                "source": "body",
                "sourceHandle": "output",
                "target": "loop-1",
                "targetHandle": "input",
            }
        )
    else:
        edges.append(
            {
                "id": "e3",
                "source": "body",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            }
        )
    if nested:
        nodes.append(
            {"id": "loop-2", "type": "Loop", "template_version": 2, "values": {"items_source": ""}}
        )
        edges.append(
            {
                "id": "e5",
                "source": "body",
                "sourceHandle": "output",
                "target": "loop-2",
                "targetHandle": "input",
            }
        )
        edges.append(
            {
                "id": "e6",
                "source": "loop-2",
                "sourceHandle": "item",
                "target": "loop-1",
                "targetHandle": "input",
            }
        )
        edges.append(
            {
                "id": "e7",
                "source": "loop-2",
                "sourceHandle": "done",
                "target": "loop-1",
                "targetHandle": "input",
            }
        )
    return {"nodes": nodes, "edges": edges}


def test_foreach_loop_missing_branch_is_invalid():
    spec = FlowSpec.model_validate(_foreach_flow(wire_done=False))
    assert any(e.code == FLOW_FOREACH_MISSING_BRANCH for e in validate(spec).errors)


def test_foreach_body_that_never_returns_is_invalid():
    spec = FlowSpec.model_validate(_foreach_flow(body_loops_back=False))
    assert any(e.code == FLOW_FOREACH_BODY_NOT_LOOPING for e in validate(spec).errors)


def test_nested_foreach_loop_is_rejected():
    spec = FlowSpec.model_validate(_foreach_flow(nested=True))
    assert any(e.code == FLOW_NESTED_LOOP for e in validate(spec).errors)


def test_well_formed_foreach_loop_is_clean():
    spec = FlowSpec.model_validate(_foreach_flow())
    codes = {e.code for e in validate(spec).errors}
    assert not codes & {
        FLOW_FOREACH_MISSING_BRANCH,
        FLOW_FOREACH_BODY_NOT_LOOPING,
        FLOW_NESTED_LOOP,
    }


def _hitl_validator_flow(*, enable_unmatched, wire_reject=True, wire_unmatched=False) -> dict:
    edges = [
        {
            "id": "e1",
            "source": "in-1",
            "sourceHandle": "message",
            "target": "hi-1",
            "targetHandle": "input",
        },
        {
            "id": "e2",
            "source": "hi-1",
            "sourceHandle": "approve",
            "target": "out-1",
            "targetHandle": "message",
        },
    ]
    if wire_reject:
        edges.append(
            {
                "id": "e3",
                "source": "hi-1",
                "sourceHandle": "reject",
                "target": "out-1",
                "targetHandle": "message",
            }
        )
    if wire_unmatched:
        edges.append(
            {
                "id": "e4",
                "source": "hi-1",
                "sourceHandle": "unmatched",
                "target": "out-1",
                "targetHandle": "message",
            }
        )
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {
                "id": "hi-1",
                "type": "HumanInput",
                "values": {
                    "prompt": "Ship it?",
                    "decisions": [{"label": "approve"}, {"label": "reject"}],
                    "enable_unmatched": enable_unmatched,
                },
            },
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": edges,
    }


def test_human_input_unwired_action_is_invalid():
    spec = FlowSpec.model_validate(_hitl_validator_flow(enable_unmatched=False, wire_reject=False))
    assert any(e.code == FLOW_HUMAN_INPUT_MISSING_ACTION for e in validate(spec).errors)


def test_human_input_fallback_edge_without_the_toggle_is_invalid():
    spec = FlowSpec.model_validate(
        _hitl_validator_flow(enable_unmatched=False, wire_unmatched=True)
    )
    assert any(e.code == FLOW_HUMAN_INPUT_UNMATCHED_DISABLED for e in validate(spec).errors)


def test_human_input_fully_wired_is_clean():
    spec = FlowSpec.model_validate(_hitl_validator_flow(enable_unmatched=True, wire_unmatched=True))
    codes = {e.code for e in validate(spec).errors}
    assert not codes & {FLOW_HUMAN_INPUT_MISSING_ACTION, FLOW_HUMAN_INPUT_UNMATCHED_DISABLED}


def test_foreach_body_closing_on_the_items_port_is_invalid():
    """With a collection port, a body that closes onto Items instead of Input
    would re-resolve the collection every pass and never finish. The old
    reachability check could not tell the two ports apart."""
    flow = _foreach_flow()
    for edge in flow["edges"]:
        if edge["source"] == "body" and edge["target"] == "loop-1":
            edge["targetHandle"] = "items"
    spec = FlowSpec.model_validate(flow)
    assert any(e.code == FLOW_FOREACH_BODY_NOT_LOOPING for e in validate(spec).errors)


# ---------------------------------------------------------------------------
# RunFlow (Phase 5)
# ---------------------------------------------------------------------------


def _run_flow_spec(flow_id: str = "11111111-1111-1111-1111-111111111111") -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "rf-1", "type": "RunFlow", "values": {"flow_id": flow_id}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "rf-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "rf-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


def test_run_flow_without_a_target_is_invalid():
    spec = FlowSpec.model_validate(_run_flow_spec(flow_id=""))
    assert any(e.code == FLOW_RUNFLOW_MISSING_TARGET for e in validate(spec).errors)


def test_a_configured_run_flow_is_structurally_clean():
    """Whether the target exists, is published, cycles or contains a Human
    Input all need I/O and are checked in FlowService, not here."""
    spec = FlowSpec.model_validate(_run_flow_spec())
    codes = {e.code for e in validate(spec).errors}
    assert not {c for c in codes if c.startswith("FLOW_RUNFLOW")}


def test_agent_ref_still_cannot_target_a_flow_backed_agent():
    """Scope decision 5.5: RunFlow is the only door. Langflow made the same
    call — SubFlow and FlowTool are legacy, both replaced by RunFlow. AgentRef
    means 'embed a classic agent', and a flow is not one. This test exists
    because that decision lives in a document, and a document cannot fail."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {"id": "ar-1", "type": "AgentRef", "values": {"agent_id": "flow-agent"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "ar-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "ar-1",
                    "sourceHandle": "output",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )
    issues = validate(spec, is_flow_backed=lambda _id: True).errors
    assert any(e.code == FLOW_NESTED_FLOW_REF for e in issues)


# ---------------------------------------------------------------------------
# StructuredOutput
# ---------------------------------------------------------------------------


def _structured_spec(schema) -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "so-1", "type": "StructuredOutput", "values": {"output_schema": schema}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "so-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "so-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


def test_structured_output_needs_at_least_one_field():
    spec = FlowSpec.model_validate(_structured_spec([]))
    assert any(e.code == FLOW_STRUCTURED_OUTPUT_SCHEMA for e in validate(spec).errors)


def test_structured_output_rejects_a_field_name_that_cannot_be_an_attribute():
    """Caught here rather than at compile time: the author sees it before the
    flow is ever published."""
    spec = FlowSpec.model_validate(_structured_spec([{"name": "iki kelime", "type": "str"}]))
    assert any(e.code == FLOW_STRUCTURED_OUTPUT_SCHEMA for e in validate(spec).errors)


def test_structured_output_rejects_an_unknown_type():
    spec = FlowSpec.model_validate(_structured_spec([{"name": "tarih", "type": "datetime"}]))
    assert any(e.code == FLOW_STRUCTURED_OUTPUT_SCHEMA for e in validate(spec).errors)


def test_structured_output_rejects_duplicate_field_names():
    spec = FlowSpec.model_validate(
        _structured_spec([{"name": "a", "type": "str"}, {"name": "a", "type": "int"}])
    )
    assert any(e.code == FLOW_STRUCTURED_OUTPUT_SCHEMA for e in validate(spec).errors)


def test_a_well_formed_structured_output_is_clean():
    spec = FlowSpec.model_validate(
        _structured_spec(
            [
                {"name": "baslik", "description": "x", "type": "str", "multiple": False},
                {"name": "etiketler", "description": "y", "type": "str", "multiple": True},
            ]
        )
    )
    assert not [e for e in validate(spec).errors if e.code == FLOW_STRUCTURED_OUTPUT_SCHEMA]


# ---------------------------------------------------------------------------
# Data Operations
# ---------------------------------------------------------------------------


def _operations_spec(operation: str) -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "op-1", "type": "Operations", "values": {"operation": operation}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "op-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "op-1",
                "sourceHandle": "message_output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


def test_an_unknown_operation_is_rejected_before_it_can_be_saved():
    """Otherwise the only signal is a build failure the first time it runs."""
    spec = FlowSpec.model_validate(_operations_spec("Yok Böyle"))
    assert any(e.code == FLOW_INVALID_OPTION for e in validate(spec).errors)


def test_every_langflow_operation_is_accepted():
    from domain.flows.data_ops import ALL_OPERATIONS

    for operation in ALL_OPERATIONS:
        spec = FlowSpec.model_validate(_operations_spec(operation))
        codes = {e.code for e in validate(spec).errors}
        assert FLOW_INVALID_OPTION not in codes, operation


# ---------------------------------------------------------------------------
# tool_mode — a tool is not a step
# ---------------------------------------------------------------------------


def _tool_mode_spec(*, flow_edge: bool = False, wire_tool: bool = True) -> dict:
    edges = [
        {
            "id": "e1",
            "source": "in-1",
            "sourceHandle": "message",
            "target": "agent-1",
            "targetHandle": "input",
        },
        {
            "id": "e3",
            "source": "agent-1",
            "sourceHandle": "output",
            "target": "out-1",
            "targetHandle": "message",
        },
    ]
    if wire_tool:
        edges.append(
            {
                "id": "e2",
                "source": "ws-1",
                "sourceHandle": "tool",
                "target": "agent-1",
                "targetHandle": "tools",
            }
        )
    if flow_edge:
        edges.append(
            {
                "id": "e4",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "ws-1",
                "targetHandle": "query",
            }
        )
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "ws-1", "type": "WebSearch", "values": {"tool_mode": True}},
            {"id": "agent-1", "type": "ReActAgent", "values": {"system_prompt": "x"}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": edges,
    }


def test_a_flow_edge_into_a_tool_mode_node_is_rejected():
    """It would look wired and do nothing: the flow never runs that node."""
    spec = FlowSpec.model_validate(_tool_mode_spec(flow_edge=True))
    assert any(e.code == FLOW_TOOL_MODE_FLOW_EDGE for e in validate(spec).errors)


def test_a_tool_mode_node_wired_to_no_agent_is_rejected():
    """The tool exists and nothing can call it."""
    spec = FlowSpec.model_validate(_tool_mode_spec(wire_tool=False))
    assert any(e.code == FLOW_TOOL_MODE_UNUSED for e in validate(spec).errors)


def test_a_correctly_wired_tool_mode_node_is_clean():
    spec = FlowSpec.model_validate(_tool_mode_spec())
    codes = {e.code for e in validate(spec).errors}
    assert not {c for c in codes if c.startswith("FLOW_TOOL_MODE")}


def test_the_same_node_without_tool_mode_may_be_wired_into_the_flow():
    """The rules apply only in tool mode; the component is still an ordinary
    step otherwise."""
    spec_dict = _tool_mode_spec(flow_edge=True, wire_tool=False)
    for node in spec_dict["nodes"]:
        if node["id"] == "ws-1":
            node["values"] = {"tool_mode": False}
    spec = FlowSpec.model_validate(spec_dict)
    codes = {e.code for e in validate(spec).errors}
    assert not {c for c in codes if c.startswith("FLOW_TOOL_MODE")}


# ---------------------------------------------------------------------------
# Router row operators
#
# `evaluate_comparison` returns False for an operator it does not know — a
# routing function must not raise — so a typo silently means "this route never
# fires" and the flow falls through to `default`. Nothing reported it before.
# ---------------------------------------------------------------------------


def _router_spec(operator: str) -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {
                "id": "r-1",
                "type": "Router",
                "template_version": 2,
                "values": {
                    "routes": [
                        {"source": "", "operator": operator, "match_text": "x", "route": "a"},
                    ]
                },
            },
            {"id": "a1", "type": "ZeroShotAgent", "values": {"system_prompt": "x"}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "r-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "r-1",
                "sourceHandle": "a",
                "target": "a1",
                "targetHandle": "input",
            },
            {
                "id": "e3",
                "source": "a1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


def test_a_misspelled_router_operator_is_reported():
    spec = FlowSpec.model_validate(_router_spec("equal"))
    assert any(e.code == FLOW_INVALID_OPTION for e in validate(spec).errors)


def test_a_router_operator_with_the_wrong_case_is_reported():
    """`Contains` is not `contains`; the comparison is exact."""
    spec = FlowSpec.model_validate(_router_spec("Contains"))
    assert any(e.code == FLOW_INVALID_OPTION for e in validate(spec).errors)


def test_every_known_operator_is_accepted_in_a_router_row():
    from domain.flows.comparison import CONDITION_OPERATORS

    for operator in CONDITION_OPERATORS:
        spec = FlowSpec.model_validate(_router_spec(operator))
        codes = {e.code for e in validate(spec).errors}
        assert FLOW_INVALID_OPTION not in codes, operator


def test_a_blank_router_operator_is_allowed():
    """The compiler reads a blank one as `is_truthy`, which is what the v1
    migration produces; it is a default, not a mistake."""
    spec = FlowSpec.model_validate(_router_spec(""))
    codes = {e.code for e in validate(spec).errors}
    assert FLOW_INVALID_OPTION not in codes


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


def _guardrails_spec(*, wired=("pass_result", "fail_result"), **values):
    """Chat Input -> Guardrails -> both branches into Chat Output."""
    base = {"enabled_guardrails": ["PII"]}
    base.update(values)
    edges = [
        {
            "id": "e0",
            "source": "in-1",
            "sourceHandle": "message",
            "target": "g-1",
            "targetHandle": "input",
        }
    ]
    edges += [
        {
            "id": f"e{index + 1}",
            "source": "g-1",
            "sourceHandle": handle,
            "target": "out-1",
            "targetHandle": "message",
        }
        for index, handle in enumerate(wired)
    ]
    return FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {"id": "g-1", "type": "Guardrails", "values": base},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": edges,
        }
    )


def _codes(spec):
    return [issue.code for issue in validate(spec).errors]


def test_guardrails_with_both_branches_wired_is_valid():
    assert validate(_guardrails_spec()).valid


def test_guardrails_missing_the_fail_branch_is_rejected():
    """Both branches must exist: the compiler has to have somewhere to send a
    blocked input, and a dead end would drop the run without an answer."""
    assert FLOW_GUARDRAILS_MISSING_BRANCH in _codes(_guardrails_spec(wired=("pass_result",)))


def test_guardrails_missing_the_pass_branch_is_rejected():
    assert FLOW_GUARDRAILS_MISSING_BRANCH in _codes(_guardrails_spec(wired=("fail_result",)))


def test_the_data_result_branch_carries_json_to_an_audit_node():
    """Result Data is typed Data, not Message: it feeds something that reads a
    record, which is what makes it an audit trail rather than a third branch."""
    spec = _guardrails_spec()
    spec.nodes.append(
        FlowNode.model_validate(
            {
                "id": "log-1",
                "type": "Parser",
                "values": {"mode": "Stringify", "pattern": "", "sep": "\n"},
            }
        )
    )
    spec.edges.append(
        FlowEdge.model_validate(
            {
                "id": "e9",
                "source": "g-1",
                "sourceHandle": "data_result",
                "target": "log-1",
                "targetHandle": "input_data",
            }
        )
    )
    spec.edges.append(
        FlowEdge.model_validate(
            {
                "id": "e10",
                "source": "log-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            }
        )
    )
    assert validate(spec).valid


def test_guardrails_with_no_check_enabled_is_rejected():
    """It would raise at run time; catching it here names the node instead."""
    assert FLOW_GUARDRAILS_NO_CHECK in _codes(_guardrails_spec(enabled_guardrails=[]))


def test_a_custom_guardrail_alone_satisfies_the_check_requirement():
    spec = _guardrails_spec(
        enabled_guardrails=[],
        enable_custom_guardrail=True,
        custom_guardrail_explanation="Detects medical terminology",
    )
    assert validate(spec).valid


def test_a_custom_guardrail_turned_on_with_no_description_does_not_count():
    spec = _guardrails_spec(
        enabled_guardrails=[], enable_custom_guardrail=True, custom_guardrail_explanation="  "
    )
    assert FLOW_GUARDRAILS_NO_CHECK in _codes(spec)


def test_an_unknown_guardrail_name_is_rejected():
    """A name the runtime does not know is silently dropped there, which would
    leave a check the author believes is running."""
    assert FLOW_INVALID_OPTION in _codes(_guardrails_spec(enabled_guardrails=["PII", "Nope"]))
