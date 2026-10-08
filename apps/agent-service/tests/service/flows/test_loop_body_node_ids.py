"""_loop_body_node_ids: which execution nodes sit on a Loop/While cycle.

B18: a node here is known to iterate *before* a single run has proven it by
looping twice — the client folds its very first iteration into a
collapsible group instead of flashing it as a standalone stage card.
"""

from agents.graphs.flow import _loop_body_node_ids
from schemas.flows import FlowSpec


def _spec(nodes: list[tuple[str, str]], edges: list[tuple[str, str, str]]) -> FlowSpec:
    return FlowSpec.model_validate(
        {
            "nodes": [{"id": i, "type": t, "values": {}} for i, t in nodes],
            "edges": [
                {
                    "id": f"{s}->{d}:{h}",
                    "source": s,
                    "target": d,
                    "source_handle": h,
                    "target_handle": "",
                }
                for s, d, h in edges
            ],
        }
    )


def test_no_loop_at_all_is_empty():
    spec = _spec(
        [("in", "ChatInput"), ("a", "ReActAgent"), ("out", "ChatOutput")],
        [("in", "a", ""), ("a", "out", "")],
    )
    assert _loop_body_node_ids(spec, set()) == set()


def test_loop_exit_into_output_marks_the_loop_and_its_body():
    spec = _spec(
        [
            ("in", "ChatInput"),
            ("a", "ReActAgent"),
            ("loop", "Loop"),
            ("out", "ChatOutput"),
        ],
        [
            ("in", "loop", ""),
            ("loop", "a", "continue"),
            ("a", "loop", ""),
            ("loop", "out", "exit"),
        ],
    )
    assert _loop_body_node_ids(spec, set()) == {"loop", "a"}


def test_while_type_is_recognised_same_as_loop():
    spec = _spec(
        [
            ("in", "ChatInput"),
            ("esc", "Chatbot"),
            ("while", "While"),
            ("out", "ChatOutput"),
        ],
        [
            ("in", "while", ""),
            ("while", "esc", "continue"),
            ("esc", "while", ""),
            ("while", "out", "exit"),
        ],
    )
    assert _loop_body_node_ids(spec, set()) == {"while", "esc"}


def test_two_independent_loops_both_get_flagged():
    """F10 shape: a per-item Loop feeding a router (never reaching
    ChatOutput directly) and a separate While loop that does. Both loop
    bodies are structurally known to iterate, regardless of which one
    (if either) is the flow's final answer stage."""
    spec = _spec(
        [
            ("in", "ChatInput"),
            ("loop", "Loop"),
            ("perticket", "Chatbot"),
            ("router", "Router"),
            ("ok", "Chatbot"),
            ("while", "While"),
            ("esc", "Chatbot"),
            ("out", "ChatOutput"),
        ],
        [
            ("in", "loop", "items"),
            ("loop", "perticket", "item"),
            ("perticket", "loop", ""),
            ("loop", "router", "done"),
            ("router", "ok", "false_result"),
            ("router", "while", "true_result"),
            ("while", "esc", "continue"),
            ("esc", "while", ""),
            ("while", "out", "exit"),
            ("ok", "out", ""),
        ],
    )
    assert _loop_body_node_ids(spec, set()) == {"loop", "perticket", "while", "esc"}
    # neither the router nor the branches feeding straight to ChatOutput loop
    assert "router" not in _loop_body_node_ids(spec, set())
    assert "ok" not in _loop_body_node_ids(spec, set())
    assert "out" not in _loop_body_node_ids(spec, set())


def test_resource_edges_are_ignored():
    spec = _spec(
        [
            ("in", "ChatInput"),
            ("a", "ReActAgent"),
            ("m", "LLMModel"),
            ("loop", "Loop"),
            ("out", "ChatOutput"),
        ],
        [
            ("in", "loop", ""),
            ("loop", "a", "continue"),
            ("m", "a", ""),
            ("a", "loop", ""),
            ("loop", "out", "exit"),
        ],
    )
    # the model edge does not create a spurious cycle member
    assert _loop_body_node_ids(spec, {"m"}) == {"loop", "a"}


def test_a_loop_node_with_no_real_cycle_still_names_itself():
    """A malformed/never-taken-back Loop node — the validator's job to flag
    the flow, not this helper's — still reports itself so a bare Loop stage
    never looks like an ordinary one-shot node."""
    spec = _spec(
        [("in", "ChatInput"), ("loop", "Loop"), ("out", "ChatOutput")],
        [("in", "loop", ""), ("loop", "out", "exit")],
    )
    assert _loop_body_node_ids(spec, set()) == {"loop"}
