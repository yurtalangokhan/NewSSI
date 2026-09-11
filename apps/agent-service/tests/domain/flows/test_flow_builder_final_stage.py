"""_resolve_final_stage_nodes: which execution nodes feed ChatOutput."""

from agents.graphs.flow_builder import _resolve_final_stage_nodes
from models.flows import FlowSpec


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


def test_linear_flow_single_final_stage():
    spec = _spec(
        [("in", "ChatInput"), ("a", "ReActAgent"), ("out", "ChatOutput")],
        [("in", "a", ""), ("a", "out", "")],
    )
    assert _resolve_final_stage_nodes(spec, set()) == {"a"}


def test_two_chat_outputs_two_final_stages():
    spec = _spec(
        [
            ("in", "ChatInput"),
            ("a", "ReActAgent"),
            ("b", "ReActAgent"),
            ("o1", "ChatOutput"),
            ("o2", "ChatOutput"),
            ("r", "Router"),
        ],
        [("in", "r", ""), ("r", "a", "x"), ("r", "b", "y"), ("a", "o1", ""), ("b", "o2", "")],
    )
    assert _resolve_final_stage_nodes(spec, set()) == {"a", "b"}


def test_router_between_agent_and_output_walks_back():
    spec = _spec(
        [
            ("in", "ChatInput"),
            ("a", "ReActAgent"),
            ("cr", "ConditionalRouter"),
            ("out", "ChatOutput"),
        ],
        [("in", "a", ""), ("a", "cr", ""), ("cr", "out", "true_result")],
    )
    assert _resolve_final_stage_nodes(spec, set()) == {"a"}


def test_loop_exit_into_output():
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
    assert _resolve_final_stage_nodes(spec, set()) == {"a"}


def test_resource_edges_ignored():
    spec = _spec(
        [
            ("in", "ChatInput"),
            ("a", "ReActAgent"),
            ("m", "LLMModel"),
            ("out", "ChatOutput"),
        ],
        [("in", "a", ""), ("m", "a", ""), ("a", "out", "")],
    )
    assert _resolve_final_stage_nodes(spec, {"m"}) == {"a"}


def test_node_after_chat_output_does_not_change_the_set():
    spec = _spec(
        [
            ("in", "ChatInput"),
            ("a", "ReActAgent"),
            ("out", "ChatOutput"),
            ("b", "ReActAgent"),
            ("out2", "ChatOutput"),
        ],
        [("in", "a", ""), ("a", "out", ""), ("out", "b", ""), ("b", "out2", "")],
    )
    # Both ChatOutput feeders count; a node wired downstream of a ChatOutput
    # does not remove its predecessor from the set.
    assert _resolve_final_stage_nodes(spec, set()) == {"a", "b"}


def test_merge_and_loop_between_agent_and_output_walk_back_to_agent():
    """Persona 50 shape: ...ReActAgent -> Loop -> Merge -> ChatOutput.
    The answer stage is the ReActAgent, not Merge (which produces no message)."""
    spec = _spec(
        [
            ("in", "ChatInput"),
            ("research", "PipelineStage"),
            ("analysis", "PipelineStage"),
            ("react", "ReActAgent"),
            ("loop", "Loop"),
            ("merge", "Merge"),
            ("out", "ChatOutput"),
        ],
        [
            ("in", "research", ""),
            ("research", "analysis", ""),
            ("analysis", "react", ""),
            ("react", "loop", ""),
            ("loop", "research", "continue"),
            ("loop", "merge", "exit"),
            ("merge", "out", ""),
        ],
    )
    assert _resolve_final_stage_nodes(spec, set()) == {"react"}


def test_prompt_template_feeding_output_walks_back():
    spec = _spec(
        [
            ("in", "ChatInput"),
            ("a", "ReActAgent"),
            ("pt", "PromptTemplate"),
            ("out", "ChatOutput"),
        ],
        [("in", "a", ""), ("a", "pt", ""), ("pt", "out", "")],
    )
    assert _resolve_final_stage_nodes(spec, set()) == {"a"}
