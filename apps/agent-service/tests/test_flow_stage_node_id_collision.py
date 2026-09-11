"""A canvas node whose id happens to match a LangGraph-internal name.

``_INFRA_NODES`` exists to silence a compiled agent subgraph's own steps
("model", "call_model", "tools", "agent"). Those only ever arrive under a
namespace. A *top-level* FlowAgent node id is user-authored — and an imported
or hand-written spec can legitimately name a node ``agent``. Filtering it as
infrastructure silently dropped its stage events: the chip stayed grey as if
the node never ran, and the agent's reasoning got attributed to whichever
stage was open before it.
"""

from service.AgentStreamService import _is_infra_node


def test_graph_internal_names_are_infra_at_every_level():
    for name in ("__start__", "__end__", "__interrupt__"):
        assert _is_infra_node(name, is_top_level=True)
        assert _is_infra_node(name, is_top_level=False)


def test_subgraph_step_names_are_infra_only_inside_a_subgraph():
    for name in ("model", "call_model", "tools", "agent"):
        assert _is_infra_node(name, is_top_level=False), f"{name} inside a subgraph is infra"
        assert not _is_infra_node(name, is_top_level=True), (
            f"a top-level canvas node called {name!r} is a real stage"
        )


def test_ordinary_canvas_ids_are_never_infra():
    for name in ("ZeroShotAgent-f296f72f", "keep", "pt", "loop-1"):
        assert not _is_infra_node(name, is_top_level=True)
        assert not _is_infra_node(name, is_top_level=False)
