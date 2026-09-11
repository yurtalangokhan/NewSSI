"""Which canvas node types may become a *timeline stage*.

A timeline stage is a node whose run produces user-visible answer text. Every
other node — routers, boundaries, value producers — must be excluded, or the
chat grows an empty numbered group for it.

This list went stale three times in a row (Phase 0 added ``SetVariable``,
Phase 3 renamed the counter loop to ``While``, Phase 4 added ``HumanInput``),
so it is no longer written out by hand: it is derived from the compiler's own
``PASSTHROUGH_NODE_TYPES`` — the same set it already uses to walk back to the
node that produces the answer. One list, one place to update.
"""

from agents.graphs import PASSTHROUGH_NODE_TYPES
from service.AgentStreamService import _NON_STAGE_NODE_TYPES


def test_non_stage_types_track_the_compilers_passthrough_set():
    assert _NON_STAGE_NODE_TYPES == frozenset(PASSTHROUGH_NODE_TYPES)


def test_every_control_flow_and_value_node_is_excluded():
    """Named explicitly so a regression names the node that broke."""
    for node_type in (
        "ChatInput",
        "ChatOutput",
        "Router",
        "Loop",  # foreach (Phase 3)
        "While",  # the renamed counter loop (Phase 3)
        "ConditionalRouter",
        "SmartRouter",  # Phase 2
        "HumanInput",  # Phase 4
        "Merge",
        "PromptTemplate",
        "TextInput",
        "FileInput",
        "SetVariable",  # Phase 0
    ):
        assert node_type in _NON_STAGE_NODE_TYPES, f"{node_type} must not be a timeline stage"


def test_agent_types_are_still_stages():
    for node_type in ("ZeroShotAgent", "ReActAgent", "PlanExecuteAgent", "SelfReflectAgent"):
        assert node_type not in _NON_STAGE_NODE_TYPES
