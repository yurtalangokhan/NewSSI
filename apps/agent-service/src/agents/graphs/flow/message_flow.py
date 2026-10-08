"""How values and messages move through a compiled flow graph.

Port values are resolved from producer state, merge nodes collect their
arrivals, suppressed producers are kept out of the transcript, and the stage
walk decides which node actually yields the answer. The compiler and every flow
node factory read these rules from here.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from agents.graphs.flow.node_types import PASSTHROUGH_NODE_TYPES
from agents.graphs.flow.state import FlowState
from agents.graphs.stage_report import report_stage_output
from core.observability.logger import get_logger
from schemas.flows import FlowEdge, FlowNode, FlowSpec

logger = get_logger(__name__)


async def _noop_node(state: FlowState, config: RunnableConfig | None = None) -> dict[str, Any]:  # noqa: ARG001
    return {}


def _final_answer_message(messages: list[Any]) -> Any | None:
    """The last message that reads as an answer to a person: an AIMessage
    with visible content and no pending tool calls. Handoff notices, tool
    calls and tool results are skipped."""
    for msg in reversed(messages or []):
        is_ai = getattr(msg, "type", None) == "ai" or isinstance(msg, AIMessage)
        if not is_ai:
            continue
        if getattr(msg, "tool_calls", None):
            continue
        content = getattr(msg, "content", "")
        if isinstance(content, str) and content.strip():
            return msg
    return None


def _isolate_subagent_node(child: Any, node_id: str) -> Any:
    """Run an embedded AgentRef / Supervisor subgraph in isolation and return
    ONLY its final answer to the parent flow.

    Added directly as a node, a subgraph merges its *entire* message list
    into the parent via ``add_messages`` — a Supervisor's internal handoff
    chatter, its own system prompt, and the roster of sub-agents (with their
    prompts and tool status) then surfaced as user-visible turns (B16), and
    the real answer often arrived only as a trailing fragment (B17). Seeding
    the child with just the latest message and forwarding just its final
    answer keeps that transcript inside the subgraph where it belongs.
    """

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        seed = list(state.get("messages", []))[-1:]
        child_input = {"messages": seed, "scratch": {}, "arrivals": []}
        if hasattr(child, "ainvoke"):
            result = await child.ainvoke(child_input, config)
        else:
            # a plain node callable (used in tests, and a valid shape)
            result = await child(child_input, config)
        all_msgs = list(result.get("messages", []))
        # The child's answer: its last AIMessage with visible content and no
        # pending tool calls. Handoff notices, the supervisor's own prompt,
        # tool calls / results and the seed HumanMessage are all skipped —
        # so nothing but the answer crosses back (B16 / B17).
        final = _final_answer_message(all_msgs)
        if final is not None:
            answer = str(getattr(final, "content", ""))
        elif len(all_msgs) > len(seed):
            # child ended oddly (no closing AIMessage) — surface its last
            # produced text rather than leaving the parent silent.
            answer = str(getattr(all_msgs[-1], "content", "") or "")
        else:
            answer = ""
        # Make the sub-agent's answer visible when its timeline stage is
        # expanded — otherwise "Agent Reference" / "Supervisor" is a step
        # that appears to have done nothing.
        if answer:
            report_stage_output(node_id, answer[:2000])
        update: dict[str, Any] = {"scratch": {node_id: answer}}
        if final is not None:
            update["messages"] = [final]
        elif answer:
            update["messages"] = [AIMessage(content=answer)]
        return update

    return _run


def _handle_source_id(node_id: str, handle: str, edges: list[FlowEdge]) -> str | None:
    """The id of the node wired into ``node_id``'s ``handle`` input port.

    Langflow passes a value into a component along an edge; we carry the same
    idea by naming the *producer* and reading its scratch slot at runtime
    (``_resolve_port_value``). Returns ``None`` when nothing is wired, which is
    what lets a caller fall back to the handle's declared ``fallback_field``.
    """
    return next(
        (e.source for e in edges if e.target == node_id and e.target_handle == handle),
        None,
    )


def _resolve_port_value(state: FlowState, source_id: str | None) -> Any | None:
    """The value a wired input port carries.

    The producer's ``scratch`` slot when it wrote one, else the latest message
    text — an agent-terminated branch publishes no scratch value, but what it
    just said is the value it produced.

    ``None`` means *nothing is wired*, deliberately distinct from an edge
    carrying an empty value: only the former may fall back to a field.
    """
    if source_id is None:
        return None
    scratch = state.get("scratch", {})
    if source_id in scratch:
        return scratch[source_id]
    return _extract_last_message_text(state)


def _make_arrival_stamp(merge_id: str, source_id: str) -> Any:
    """Sits on one edge into a first/last Merge and records that branch's
    value — and the id of the message it produced — on the ordered
    ``arrivals`` channel, then passes through.

    It runs in the super-step after its upstream node, so a shorter branch
    stamps before a longer one — that ordering is what first/last read. The
    branch value is ``scratch[source_id]`` when the upstream node produced one
    (TextInput, PromptTemplate, Set Variable), else the latest message text
    (best effort for an agent-terminated branch). Merge uses the value to
    pick a branch and the message id to retract the others (B19)."""

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
        value = str(_resolve_port_value(state, source_id))
        return {"arrivals": [(merge_id, value)]}

    return _run


def _make_merge_node(node: FlowNode, *, expected_arrivals: int | None = None) -> Any:
    """ "concat" is a pure passthrough — `add_messages` already accumulated
    every branch's contribution before this node runs.

    "first"/"last" read the ``arrivals`` channel (populated by the compiler's
    arrival-stamp nodes on each incoming edge) and emit the earliest / latest
    branch's value as a fresh message, so it becomes ``messages[-1]`` — the
    ONLY message the whole branch tree contributes: every producer that feeds
    only this Merge had its own message suppressed at compile time (B19, see
    ``_message_suppressed_producer_ids``), so there is nothing left over to
    retract from the *branches*.

    That alone is not enough: LangGraph runs a node again each time any one
    of its several incoming static edges completes, not once after all of
    them have (that staggered re-running is exactly how "first"/"last" can
    tell arrival order apart in the first place — see ``_make_arrival_stamp``).
    Left unguarded, Merge itself would emit a message on every one of those
    partial runs — a "last" Merge would show the *earliest* branch's answer
    first, then silently correct it, each as its own transcript message.
    ``expected_arrivals`` (the compiler's count of edges wired into this
    Merge) gates that: no message is emitted until every branch's arrival is
    in, so the node contributes exactly one. ``None`` (a standalone call
    outside a compiled build) skips the gate and answers as soon as any
    value is present — the pre-B19 behaviour, fine when nothing else is
    racing to overwrite it.
    """
    strategy = node.values.get("strategy", "concat")
    if strategy == "concat":
        return _noop_node
    if strategy not in ("first", "last"):
        raise NotImplementedError(f"Merge strategy {strategy!r} is not implemented — use 'concat', 'first' or 'last'")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
        values = [value for (merge_id, value) in state.get("arrivals", []) if merge_id == node.id]
        if not values:
            return {}
        if expected_arrivals is not None and len(values) < expected_arrivals:
            return {}  # not every branch has arrived yet — stay silent
        chosen = values[0] if strategy == "first" else values[-1]
        # AIMessage, not HumanMessage: this is the flow's own answer, not a
        # fresh user turn. A HumanMessage here reads as the human speaking
        # again — SSE streaming happens to be type-agnostic (any message
        # that isn't the user's own echoed input still renders live), so a
        # live viewer saw the right text, but every persistence check keys
        # off `type == "ai"` to decide "this is the assistant's reply" —
        # with the wrong type nothing was ever saved as one. A reload (or
        # `GET /chat/sessions/{id}`) then showed the question with no
        # answer at all, even on a run the live stream displayed correctly.
        return {"messages": [AIMessage(content=chosen)]}

    return _run


def _message_suppressed_producer_ids(
    execution_adjacency: dict[str, list[str]],
    merge_ids: set[str],
    *,
    entry_ids: set[str] = frozenset(),
) -> set[str]:
    """Execution nodes whose every forward path ends at a first/last
    ``merge_ids`` node and nowhere else (B19).

    Such a node's own chat message would only ever be a losing (or
    intermediate) branch value — Merge alone constructs the transcript's one
    canonical message from whichever branch it picks. Retracting the loser's
    message after the fact needs a stable message id, which a branch ending
    in an agent or a sub-flow does not have across the parent/child boundary
    (four ``RemoveMessage`` variants were tried and each risked a reducer
    error that failed the run — see git history). Never adding the message
    in the first place sidesteps that entirely: nothing to retract, no
    dependency on message-id stability or branch execution order.

    Conservative by construction: a node with *any* forward path leaving the
    merge-only cone (a fan-out to something else, or a dead end that reaches
    no merge at all) is left OUT of the result and keeps emitting its
    message exactly as before. This never suppresses a message that some
    other consumer might need.

    ``entry_ids`` (ChatInput) are excluded from the result even when every
    forward path from one happens to be merge-only — a build entry point is
    never wrapped, so this is purely for a clean, non-misleading diagnostic
    set (``FlowGraphBuilder.message_suppressed_node_ids``).
    """
    memo: dict[str, bool] = {}

    def _reaches_only_merge(node_id: str, visiting: frozenset[str]) -> bool:
        if node_id in merge_ids:
            return True
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            # A cycle that never resolves into a merge — conservative.
            return False
        succs = execution_adjacency.get(node_id, [])
        if not succs:
            return False  # a dead end that never reaches a merge
        result = all(_reaches_only_merge(s, visiting | {node_id}) for s in succs)
        memo[node_id] = result
        return result

    return {
        node_id
        for node_id in execution_adjacency
        if node_id not in merge_ids and node_id not in entry_ids and _reaches_only_merge(node_id, frozenset())
    }


def _suppress_messages(fn: Any) -> Any:
    """Wrap a node runnable so its state update never touches ``messages``.

    For a producer whose only consumer is a first/last Merge: the branch's
    value keeps flowing through ``scratch``/``arrivals`` exactly as before,
    it just never lands in the transcript on its own — see
    ``_message_suppressed_producer_ids``.
    """

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        update = await fn(state, config)
        if not update or "messages" not in update:
            return update
        return {k: v for k, v in update.items() if k != "messages"}

    return _run


def _extract_last_message_text(state: FlowState) -> str:
    """The text of the most recent message, or ``""`` if there is none.

    Deliberately narrower than ``_extract_query``: a ConditionalRouter tests
    what the flow just produced, never a stale scratch value."""
    messages = state.get("messages", [])
    if not messages:
        return ""
    last = messages[-1]
    content = getattr(last, "content", None)
    if content is None and isinstance(last, dict):
        content = last.get("content", "")
    return str(content) if content is not None else ""


def _strip_marker(text: str, marker: str, *, case_sensitive: bool) -> str:
    """Remove every occurrence of ``marker`` from ``text`` and tidy the
    trailing whitespace it leaves behind. A no-op if the marker is absent
    (e.g. numeric / regex / negative operators leave nothing to strip)."""
    if not marker:
        return text
    if case_sensitive:
        if marker not in text:
            return text
        cleaned = text.replace(marker, "")
    else:
        if marker.lower() not in text.lower():
            return text
        cleaned = re.sub(re.escape(marker), "", text, flags=re.IGNORECASE)
    return cleaned.rstrip()


def _resolve_final_stage_nodes(
    spec: FlowSpec,
    resource_ids: set[str],
    *,
    message_suppressed_ids: set[str] | None = None,
) -> set[str]:
    """Execution nodes whose output is the flow's answer: the direct
    predecessors of any ``ChatOutput`` node, walking back through nodes that
    only forward state (routers, ``Merge``, ``PromptTemplate``, boundary
    no-ops) to the nearest AI-message-producing node.

    Structure only — never touches graph execution. Used to tell the live
    SSE layer and read-time reconstruction which stage produces the single
    final answer bubble; every earlier stage folds into the timeline.
    """
    node_type = {n.id: n.type for n in spec.nodes}
    exit_ids = {n.id for n in spec.nodes if n.type == "ChatOutput"}

    preds: dict[str, list[str]] = {}
    for edge in spec.edges:
        if edge.source in resource_ids or edge.target in resource_ids:
            continue
        preds.setdefault(edge.target, []).append(edge.source)

    final: set[str] = set()
    seen: set[str] = set()
    stack = [src for xid in exit_ids for src in preds.get(xid, [])]
    while stack:
        nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        if message_suppressed_ids and nid in message_suppressed_ids:
            # B19: a producer whose only consumer is a first/last Merge has its messages
            # suppressed. It never produces the final answer on its own.
            continue
        if node_type.get(nid) in PASSTHROUGH_NODE_TYPES:
            # Forwards, does not produce — keep walking back.
            stack.extend(preds.get(nid, []))
        else:
            final.add(nid)
    return final


def _final_stage_in_cycle(spec: FlowSpec, resource_ids: set[str], final_ids: set[str]) -> bool:
    """True when a final-answer node sits on a Loop / ConditionalRouter cycle
    and so can run several times. The live SSE layer then folds every
    iteration and promotes only the last one to the answer bubble."""
    if not final_ids:
        return False
    adj: dict[str, list[str]] = {}
    for edge in spec.edges:
        if edge.source in resource_ids or edge.target in resource_ids:
            continue
        adj.setdefault(edge.source, []).append(edge.target)
    for start in final_ids:
        stack = list(adj.get(start, []))
        walked: set[str] = set()
        while stack:
            nid = stack.pop()
            if nid == start:
                return True
            if nid in walked:
                continue
            walked.add(nid)
            stack.extend(adj.get(nid, []))
    return False


def _loop_body_node_ids(spec: FlowSpec, resource_ids: set[str]) -> set[str]:
    """Execution nodes that sit on a cycle through a ``Loop``/``While`` node —
    structurally known to iterate, before a single run has proven it (B18).

    The client folds a node's repeated stages into one collapsible group only
    once it has *seen* a second iteration — so a loop's very first pass
    renders as a standalone numbered stage card, then gets pulled into the
    group and disappears the moment iteration two starts. Over a fast loop
    this reads as separate messages flashing by. Nodes in this set are known
    to loop before they ever run, so the client can fold from iteration one
    and render one steadily-growing card instead.

    A node is on the cycle when it is both reachable *from* the loop node and
    able to reach *back to* it — the standard "on a cycle through X" test,
    computed once per loop node and unioned.
    """
    adj: dict[str, list[str]] = {}
    radj: dict[str, list[str]] = {}
    for edge in spec.edges:
        if edge.source in resource_ids or edge.target in resource_ids:
            continue
        adj.setdefault(edge.source, []).append(edge.target)
        radj.setdefault(edge.target, []).append(edge.source)

    def _reachable(start_ids: list[str], graph: dict[str, list[str]]) -> set[str]:
        seen: set[str] = set()
        stack = list(start_ids)
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            stack.extend(graph.get(nid, []))
        return seen

    node_type = {n.id: n.type for n in spec.nodes}
    body: set[str] = set()
    for loop_id, ntype in node_type.items():
        if ntype not in ("Loop", "While"):
            continue
        forward = _reachable(adj.get(loop_id, []), adj)
        backward = _reachable(radj.get(loop_id, []), radj)
        body |= forward & backward
        body.add(loop_id)
    return body


def derive_tool_name(node: FlowNode) -> str:
    """The name the model sees.

    A configured ``tool_name`` wins; otherwise the node id, which already has
    the ``<type>-<short id>`` shape the canvas generates. Formatted to
    ``^[a-zA-Z0-9_-]+$`` the way Langflow's ``_format_tool_name`` does — the
    model picks a tool by its name, so a readable one is a real difference.
    """
    configured = str(node.values.get("tool_name", "") or "").strip()
    return re.sub(r"[^a-zA-Z0-9_-]", "-", configured or node.id)
