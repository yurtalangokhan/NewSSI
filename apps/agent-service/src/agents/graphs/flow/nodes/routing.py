"""Flow routing and branching node factories (Loop, While, CondRouter, SmartRouter, Guardrails, HumanInput)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from agents.graphs.flow.message_flow import (
    _extract_last_message_text,
    _resolve_port_value,
    _strip_marker,
)
from agents.graphs.flow.state import FlowState
from core.exceptions import FlowBuildError
from core.observability.logger import get_logger
from schemas.flows import FlowEdge, FlowNode
from service.flow_model.comparison import evaluate_comparison
from service.flow_model.guardrails import (
    DEFAULT_HEURISTIC_THRESHOLD,
    HEURISTIC_CHECKS,
    build_check_prompt,
    checks_to_run,
    heuristic_jailbreak_score,
    justification_for,
    parse_guardrail_decision,
    sanitize_input,
)

logger = get_logger(__name__)


def evaluate_condition(condition: str, state: dict[str, Any]) -> bool:
    """Safely evaluate a Router/Loop condition.

    A condition is a `scratch` key name; the route is taken when that key's
    value is truthy. Deliberately **not** `eval()` — a condition string that
    looks like code is treated as a literal (almost certainly nonexistent)
    key name and is never executed. Matches tools-service's own
    `calculate` tool precedent of rejecting arbitrary expression evaluation
    rather than sandboxing one.
    """
    return bool(state.get("scratch", {}).get(condition))


def _loop_counter_key(loop_id: str) -> str:
    return f"_loop_iterations_{loop_id}"


def _make_loop_node(node: FlowNode) -> Any:
    """The Loop's own node: increments its private iteration counter in
    scratch. The bound check happens separately, in the conditional-edge
    routing function below, which reads this counter *after* it updates."""
    counter_key = _loop_counter_key(node.id)

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        current = state.get("scratch", {}).get(counter_key, 0)
        return {"scratch": {counter_key: current + 1}}

    return _run


def _make_loop_route_fn(loop_node: FlowNode, edges: list[FlowEdge]):
    """continue while the condition holds AND the bound hasn't been hit;
    exit unconditionally once the bound is reached — the R2 guarantee."""
    condition = loop_node.values.get("condition", "")
    # A While node stored before it carried the field — or a `Loop` v1 node
    # renamed to `While` by migration — arrives with no `max_iterations`.
    # Fall back to the template default (5) instead of letting `iterations <
    # None` raise an unhandled TypeError that 500s the whole run.
    _raw_max = loop_node.values.get("max_iterations")
    max_iterations = int(_raw_max) if _raw_max is not None else 5
    counter_key = _loop_counter_key(loop_node.id)

    continue_target = next(
        (e.target for e in edges if e.source == loop_node.id and e.source_handle == "continue"),
        None,
    )
    exit_target = next(
        (e.target for e in edges if e.source == loop_node.id and e.source_handle == "exit"),
        None,
    )

    def _route(state: FlowState) -> str:
        iterations = state.get("scratch", {}).get(counter_key, 0)
        # An empty condition means "no early-out test" — a plain bounded loop
        # that runs until max_iterations. A populated condition keeps the
        # original scratch-key-truthiness semantics.
        condition_holds = evaluate_condition(condition, state) if condition else True
        if iterations < max_iterations and condition_holds:
            if continue_target is None:
                raise FlowBuildError(f"While '{loop_node.id}' has no 'continue' edge")
            return continue_target
        if exit_target is None:
            raise FlowBuildError(f"While '{loop_node.id}' has no 'exit' edge")
        return exit_target

    return _route


def _foreach_items_key(node_id: str) -> str:
    return f"_foreach_items_{node_id}"


def _foreach_idx_key(node_id: str) -> str:
    return f"_foreach_idx_{node_id}"


def _foreach_agg_key(node_id: str) -> str:
    return f"_foreach_agg_{node_id}"


def _is_dataframe(value: Any) -> bool:
    """True for a pandas DataFrame, without importing pandas at module load."""
    return type(value).__name__ == "DataFrame" and hasattr(value, "to_dict")


def _resolve_loop_items(items_source: str, state: FlowState, port_source: str | None = None) -> list[Any]:
    """The collection a Loop iterates.

    Precedence is the compiler's one rule: a wired Items port wins, then the
    named Set Variable, then the non-blank lines of the latest message.

    A list is passed through element-wise, so dict rows — a document search
    result, say — reach the body with their structure intact. This is what
    Langflow's ``HandleInput`` accepting DataFrame / Table / Data / Message
    buys, expressed in the types we actually carry.

    A named source (field or port) that holds nothing iterates nothing: it
    must *not* fall back to the message, which would run the body over the
    wrong data and look like it worked.
    """
    raw: Any = None
    named = bool(items_source) or port_source is not None
    if port_source is not None:
        raw = _resolve_port_value(state, port_source)
    # A DataFrame has no truth value, so it must be recognised before any
    # `raw in (None, "")` test rather than after one.
    if not _is_dataframe(raw) and raw in (None, "") and items_source:
        raw = state.get("scratch", {}).get(items_source)
    if _is_dataframe(raw):
        # Langflow expands a DataFrame to its rows; without this the whole
        # table would be a single item. Split Text produces exactly this shape.
        return raw.to_dict(orient="records")
    if isinstance(raw, (list, tuple)):
        return list(raw)
    if isinstance(raw, str) and raw:
        return [line for line in raw.splitlines() if line.strip()]
    if raw not in (None, ""):
        return [raw]
    if named:
        return []
    return [line for line in _extract_last_message_text(state).splitlines() if line.strip()]


def _make_foreach_node(
    node: FlowNode,
    port_sources: dict[str, str] | None = None,
    body_end_id: str | None = None,
) -> Any:
    """First entry resolves the collection; every later entry (from the body
    via the back-edge) collects the body's latest output and advances. Each
    pass places the current item as the message the body consumes; when the
    list is exhausted it emits the joined results and stores the list under
    the node id for ``{node-id}`` interpolation."""
    items_source = str(node.values.get("items_source", "") or "")
    items_port = (port_sources or {}).get("items")
    items_key = _foreach_items_key(node.id)
    idx_key = _foreach_idx_key(node.id)
    agg_key = _foreach_agg_key(node.id)

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        scratch = state.get("scratch", {})
        if scratch.get(items_key) is None:
            items = _resolve_loop_items(items_source, state, items_port)
            idx = 0
            agg: list[Any] = []
        else:
            items = list(scratch.get(items_key) or [])
            # Langflow aggregates the body end-vertex's output. Reading that
            # node's scratch slot keeps whatever structure it produced;
            # _resolve_port_value falls back to the message for a body that
            # ends in an agent and publishes no slot.
            produced = _resolve_port_value(state, body_end_id) if body_end_id else _extract_last_message_text(state)
            agg = [*scratch.get(agg_key, []), produced]
            idx = scratch.get(idx_key, 0) + 1

        update: dict[str, Any] = {"scratch": {items_key: items, idx_key: idx, agg_key: agg}}
        if idx < len(items):
            # One slot, two meanings that are never live at once: while the
            # `item` branch runs this is the current element; once the list is
            # exhausted the `done` branch replaces it with the aggregate. The
            # old `_foreach_item_<id>` key was unreadable by any consumer (a
            # leading underscore and a dash make it an invalid placeholder),
            # so the item's structure never left the node.
            update["scratch"][node.id] = items[idx]
            update["messages"] = [HumanMessage(content=str(items[idx]))]
        else:
            update["scratch"][node.id] = agg
            update["messages"] = [HumanMessage(content="\n".join(str(x) for x in agg))]
        return update

    return _run


def _make_foreach_route_fn(node: FlowNode, edges: list[FlowEdge]):
    """Pure read: more items -> ``item`` branch, else -> ``done`` branch."""
    idx_key = _foreach_idx_key(node.id)
    items_key = _foreach_items_key(node.id)
    item_target = next((e.target for e in edges if e.source == node.id and e.source_handle == "item"), None)
    done_target = next((e.target for e in edges if e.source == node.id and e.source_handle == "done"), None)

    def _route(state: FlowState) -> str:
        scratch = state.get("scratch", {})
        idx = scratch.get(idx_key, 0)
        items = scratch.get(items_key) or []
        if idx < len(items):
            if item_target is None:
                raise FlowBuildError(f"Loop '{node.id}' has no 'item' edge")
            return item_target
        if done_target is None:
            raise FlowBuildError(f"Loop '{node.id}' has no 'done' edge")
        return done_target

    return _route


_CONDROUTER_BRANCHES = ("true_result", "false_result")


def _condrouter_counter_key(node_id: str) -> str:
    return f"_condrouter_iterations_{node_id}"


def _condrouter_result_key(node_id: str) -> str:
    return f"_condrouter_matched_{node_id}"


def _make_condrouter_node(node: FlowNode, port_sources: dict[str, str] | None = None) -> Any:
    """The router's own node. Does everything that needs the running state,
    so the conditional edge below is a pure scratch read (mirrors Loop):

    - increments the per-turn iteration counter;
    - evaluates ``operator``/``match_text`` against the latest message and
      stores the boolean under ``_condrouter_matched_<id>``;
    - when ``strip_match`` is on, removes ``match_text`` from that message
      (same id → ``add_messages`` replaces it) so a completion marker never
      reaches the user or the next loop pass;
    - when the taken branch has a case message configured, replaces that
      message's text with it (Langflow's ``true_case_message`` /
      ``false_case_message``); a blank one forwards the input unchanged.

    The branch is chosen from ``matched``; on the turn the ``max_iterations``
    bound forces ``default_route`` the case message still follows ``matched``,
    which is a corner acceptable for an exit turn.
    """
    counter_key = _condrouter_counter_key(node.id)
    result_key = _condrouter_result_key(node.id)
    operator = str(node.values.get("operator") or "contains")
    match_text = str(node.values.get("match_text", "") or "")
    case_sensitive = bool(node.values.get("case_sensitive", True))
    strip_match = bool(node.values.get("strip_match", False))
    # Langflow's ``input_text`` port: a Set Variable name whose value is
    # compared instead of the latest message. Blank keeps the original
    # "test what the flow just produced" behaviour, so this is additive.
    input_source = str(node.values.get("input_source", "") or "")
    true_case_message = str(node.values.get("true_case_message", "") or "")
    false_case_message = str(node.values.get("false_case_message", "") or "")
    input_src = (port_sources or {}).get("input_text")
    true_src = (port_sources or {}).get("true_case_message")
    false_src = (port_sources or {}).get("false_case_message")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        current = state.get("scratch", {}).get(counter_key, 0)
        # Wired port > input_source field > the latest message. Langflow's
        # port is required, so its "no input" case cannot arise; ours can, and
        # testing what the flow just produced beats failing.
        wired_input = _resolve_port_value(state, input_src)
        if wired_input is not None:
            compared = str(wired_input)
        elif input_source:
            compared = str(state.get("scratch", {}).get(input_source, ""))
        else:
            compared = _extract_last_message_text(state)
        matched = evaluate_comparison(operator, compared, match_text, case_sensitive=case_sensitive)
        update: dict[str, Any] = {"scratch": {counter_key: current + 1, result_key: matched}}

        messages = state.get("messages", [])
        last = messages[-1] if messages else None
        content = getattr(last, "content", None)
        if isinstance(content, str) and hasattr(last, "model_copy"):
            wired_case = _resolve_port_value(state, true_src if matched else false_src)
            override = (
                str(wired_case)
                if wired_case not in (None, "")
                else (true_case_message if matched else false_case_message)
            )
            if override:
                update["messages"] = [last.model_copy(update={"content": override})]
            elif strip_match and match_text:
                cleaned = _strip_marker(content, match_text, case_sensitive=case_sensitive)
                if cleaned != content:
                    update["messages"] = [last.model_copy(update={"content": cleaned})]

        return update

    return _run


def _make_set_variable_node(node: FlowNode) -> Any:
    """Stores a value in ``scratch`` under a user-chosen name.

    Node ids also live in ``scratch``, but they contain a dash, and internal
    counters start with an underscore; the validator's name rule keeps the
    three families from ever colliding. A blank name stores nothing rather
    than writing under "" — the validator rejects it, but an unvalidated spec
    must not corrupt scratch.
    """
    name = str(node.values.get("name", "") or "")
    configured = node.values.get("value")
    append = bool(node.values.get("append", False))

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        if not name:
            return {}
        value: Any = configured if configured not in (None, "") else _extract_last_message_text(state)
        if append:
            current = state.get("scratch", {}).get(name)
            if current is None:
                value = [value]
            elif isinstance(current, list):
                value = [*current, value]
            else:
                value = [current, value]
        return {"scratch": {name: value}}

    return _run


def _make_condrouter_route_fn(node: FlowNode, edges: list[FlowEdge]):
    """Pure state read: route on the boolean the node stored, unless the
    per-turn iteration count reached ``max_iterations`` — then the
    ``default_route`` branch is taken unconditionally (the R2
    no-infinite-loop guarantee, identical to Loop's bound)."""
    max_iterations = node.values.get("max_iterations")
    default_route = str(node.values.get("default_route") or "false_result")
    counter_key = _condrouter_counter_key(node.id)
    result_key = _condrouter_result_key(node.id)

    branch_target = {
        handle: next(
            (e.target for e in edges if e.source == node.id and e.source_handle == handle),
            None,
        )
        for handle in _CONDROUTER_BRANCHES
    }

    def _target(handle: str) -> str:
        target = branch_target.get(handle)
        if target is None:
            raise FlowBuildError(f"ConditionalRouter '{node.id}' has no '{handle}' edge")
        return target

    def _route(state: FlowState) -> str:
        scratch = state.get("scratch", {})
        iterations = scratch.get(counter_key, 0)
        if max_iterations is not None and iterations >= max_iterations:
            return _target(default_route)
        return _target("true_result" if scratch.get(result_key) else "false_result")

    return _route


_SMART_ROUTER_ELSE = "__else__"


def _smart_router_result_key(node_id: str) -> str:
    return f"_smart_router_choice_{node_id}"


def _make_smart_router_node(
    node: FlowNode,
    model: BaseChatModel | None,
    port_sources: dict[str, str] | None = None,
) -> Any:
    """Categorises the latest message with a single LLM call and records the
    chosen category in ``scratch``; the conditional edge below is a pure read
    (mirrors ConditionalRouter). A faithful port of Langflow's Smart Router.

    No wired Model resource falls back to the default model, exactly like a
    classic agent with no LLM override.
    """
    if model is None:
        from config_manager import env

        from infrastructure.llm import get_model

        model = get_model(env.DEFAULT_MODEL)

    rows = [r for r in node.values.get("routes", []) if isinstance(r, dict)]
    categories = [str(r.get("route_category", "")).strip() for r in rows]
    categories = [c for c in categories if c]
    enable_else = bool(node.values.get("enable_else_output", False))
    custom_prompt = str(node.values.get("custom_prompt", "") or "")
    override_field = str(node.values.get("message", "") or "")
    override_src = (port_sources or {}).get("message")
    result_key = _smart_router_result_key(node.id)
    value_by_category = {
        str(r.get("route_category", "")).strip(): r.get("output_value")
        for r in rows
        if str(r.get("route_category", "")).strip()
    }

    def _pick(reply_text: str) -> str | None:
        low = reply_text.strip().lower()
        for category in categories:
            if category.lower() == low:
                return category
        for category in categories:  # the LLM added surrounding words
            if category.lower() in low:
                return category
        return None

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        if not categories:
            return {"scratch": {result_key: _SMART_ROUTER_ELSE}}

        message = _extract_last_message_text(state)
        listing = "\n".join(f"- {r.get('route_category', '')}: {r.get('route_description', '')}" for r in rows)
        base = (
            f"Categories:\n{listing}\n\nMessage: {message}\n\n"
            "Reply with exactly one category name from the list and nothing else."
        )
        if custom_prompt:
            # Langflow calls this "Additional Instructions" and *appends* it.
            # Replacing the base prompt would delete the one instruction that
            # makes the reply a bare category name, which the router then has
            # to guess at.
            simple_routes = ", ".join(f'"{c}"' for c in categories)
            extra = custom_prompt.replace("{input_text}", message).replace("{routes}", simple_routes)
            human = f"{base}\n\nAdditional Instructions:\n{extra}"
        else:
            human = base

        # `skip_stream`: this is an internal classification call, not part of
        # the answer. Without the tag its category reply ("yeterli", "iptal",
        # …) streams to the client as visible assistant text, landing as a
        # stray bubble next to the branch it was only meant to choose.
        reply = await model.ainvoke(
            [
                SystemMessage(content="You are a precise text classifier."),
                HumanMessage(content=human),
            ],
            config={"tags": ["skip_stream"]},
        )
        chosen = _pick(str(getattr(reply, "content", "")))

        # Override Output beats everything, for every route — matched or else
        # (Langflow's rule).
        wired = _resolve_port_value(state, override_src)
        override = str(wired) if wired not in (None, "") else override_field

        if chosen is None:
            if not enable_else:
                raise FlowBuildError(f"SmartRouter '{node.id}' matched no category and 'Enable Else output' is off")
            # Send the conversation *down* the else branch as a concrete
            # message: the Override Output if set, otherwise the input passed
            # through. Without this, `else -> ChatOutput` surfaces nothing and
            # the user sees an unanswered turn (B10).
            else_out: dict[str, Any] = {result_key: _SMART_ROUTER_ELSE}
            else_text = override if override.strip() else message
            if else_text.strip():
                else_out[node.id] = else_text
                return {
                    "scratch": else_out,
                    "messages": [HumanMessage(content=else_text)],
                }
            return {"scratch": else_out}

        out: dict[str, Any] = {result_key: chosen}
        if override.strip():
            out[node.id] = override
            return {"scratch": out, "messages": [HumanMessage(content=override)]}
        # Langflow sends the row's value *down the branch* as the message; a
        # blank one (or the literal "none") passes the input through instead.
        configured = value_by_category.get(chosen)
        if configured is not None and str(configured).strip() and str(configured).strip().lower() != "none":
            text = str(configured)
            out[node.id] = text
            return {"scratch": out, "messages": [HumanMessage(content=text)]}
        return {"scratch": out}

    return _run


def _make_smart_router_route_fn(node: FlowNode, edges: list[FlowEdge]):
    """Pure state read: route on the category the node stored."""
    result_key = _smart_router_result_key(node.id)
    label_to_target = {e.source_handle: e.target for e in edges if e.source == node.id}

    def _route(state: FlowState) -> str:
        choice = state.get("scratch", {}).get(result_key)
        handle = "else" if choice == _SMART_ROUTER_ELSE else choice
        target = label_to_target.get(handle) or label_to_target.get("else")
        if target is None:
            raise FlowBuildError(f"SmartRouter '{node.id}' has no edge for category {choice!r}")
        return target

    return _route


def _guardrails_result_key(node_id: str) -> str:
    return f"_guardrails_passed_{node_id}"


def _make_guardrails_node(
    node: FlowNode,
    model: BaseChatModel | None,
    port_sources: dict[str, str] | None = None,
) -> Any:
    """A faithful port of Langflow's Guardrails: validate a piece of text
    against a set of LLM-backed checks and record the verdict in ``scratch``;
    the conditional edge below is a pure read (mirrors SmartRouter).

    Checks run in the order they were enabled and stop at the first failure —
    Langflow's fail-fast, which is observable, because a blocked input costs
    one model call rather than all of them. Jailbreak and Prompt Injection are
    screened by a regex score first and may be blocked without any call at all.

    ``scratch[node.id]`` holds Langflow's *Result Data* payload (the text, the
    verdict, and the justification on a failure) rather than the branch text,
    because that is the value the third output publishes and the richer of the
    two; the branch text travels as a message, which is how ``pass_result`` and
    ``fail_result`` reach whatever they are wired to.

    No wired Model resource falls back to the default model, exactly like
    SmartRouter and a classic agent with no LLM override.
    """
    if model is None:
        from config_manager import env

        from infrastructure.llm import get_model

        model = get_model(env.DEFAULT_MODEL)

    enabled = [str(v) for v in (node.values.get("enabled_guardrails") or []) if v]
    custom = (
        str(node.values.get("custom_guardrail_explanation", "") or "")
        if node.values.get("enable_custom_guardrail", False)
        else ""
    )
    checks = checks_to_run(enabled, custom)
    threshold = float(node.values.get("heuristic_threshold") or DEFAULT_HEURISTIC_THRESHOLD)
    # Langflow's ``input_text`` port; blank falls back to the latest message,
    # the same precedence ConditionalRouter uses.
    input_source = str(node.values.get("input_source", "") or "")
    input_src = (port_sources or {}).get("input_text")
    result_key = _guardrails_result_key(node.id)

    async def _check(name: str, description: str, text: str) -> bool:
        if name in HEURISTIC_CHECKS:
            score = heuristic_jailbreak_score(text)
            if score is not None and score >= threshold:
                return False
        prompt = build_check_prompt(name, description, sanitize_input(text))
        # `skip_stream`: an internal verdict call, never answer text — see the
        # same tag on SmartRouter's classifier for why it matters.
        reply = await model.ainvoke(prompt, config={"tags": ["skip_stream"]})
        try:
            return parse_guardrail_decision(str(getattr(reply, "content", reply)), check_type=name)
        except RuntimeError as exc:
            # An empty or error-shaped reply is not a verdict. Langflow raises
            # here too; naming the node turns it into something the flow author
            # can act on rather than a bare provider error.
            raise FlowBuildError(f"Guardrails '{node.id}': {exc}") from exc

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        if not checks:
            raise FlowBuildError(f"Guardrails '{node.id}' has no guardrail enabled; select at least one")

        latest = _extract_last_message_text(state)
        wired = _resolve_port_value(state, input_src)
        if wired is not None:
            text = str(wired)
        elif input_source:
            text = str(state.get("scratch", {}).get(input_source, ""))
        else:
            text = latest
        if not text.strip():
            raise FlowBuildError(f"Guardrails '{node.id}' received empty text to validate")

        failed: list[str] = []
        for name, description in checks:
            if not await _check(name, description, text):
                # Langflow reports its own fixed sentence, never the model's
                # explanation — so a blocked input is not echoed back through
                # the justification the user reads.
                failed.append(f"{name}: {justification_for(name)}")
                break  # fail fast

        passed = not failed
        payload: dict[str, Any] = {"text": text, "result": "pass" if passed else "fail"}
        if not passed:
            payload["justification"] = "\n".join(failed)

        update: dict[str, Any] = {"scratch": {result_key: passed, node.id: payload}}
        if not passed:
            update["messages"] = [HumanMessage(content=payload["justification"])]
        elif text != latest:
            # Langflow's pass output is the validated text itself, which only
            # differs from the conversation when the text came from the port
            # or the named variable.
            update["messages"] = [HumanMessage(content=text)]
        return update

    return _run


_GUARDRAILS_BRANCHES = ("pass_result", "fail_result")


def _make_guardrails_route_fn(node: FlowNode, edges: list[FlowEdge]):
    """Pure state read: the verdict picks one branch, and ``data_result`` — if
    wired — runs alongside it.

    Langflow stops whichever of Pass/Fail did not fire but never stops Result
    Data, so an audit or logging path sees every verdict. Returning a list is
    how LangGraph expresses that same fan-out.
    """
    result_key = _guardrails_result_key(node.id)
    target_by_handle = {e.source_handle: e.target for e in edges if e.source == node.id}

    def _route(state: FlowState) -> list[str]:
        passed = bool(state.get("scratch", {}).get(result_key))
        handle = "pass_result" if passed else "fail_result"
        target = target_by_handle.get(handle)
        if target is None:
            raise FlowBuildError(f"Guardrails '{node.id}' has no '{handle}' edge")
        data_target = target_by_handle.get("data_result")
        return [target, data_target] if data_target else [target]

    return _route


_HUMAN_INPUT_UNMATCHED = "__unmatched__"


def _human_input_result_key(node_id: str) -> str:
    return f"_human_input_choice_{node_id}"


def _match_decision(answer: Any, labels: Sequence[str]) -> str | None:
    """The decision label the human's answer selects, or None.

    Accepts the answer as a bare string (the plain resume path) or a
    ``{"decision": ...}`` dict (the structured resume Phase 4b adds)."""
    if isinstance(answer, dict):
        answer = answer.get("decision", "")
    text = str(answer or "").strip().lower()
    for label in labels:
        if label.lower() == text:
            return label
    return None


def _make_human_input_node(node: FlowNode) -> Any:
    """Pauses the flow with ``interrupt()``, then routes on the action the
    person picked. A faithful port of Langflow's Human Input, on the
    platform's existing interrupt/resume pipeline. No timeout — the run waits
    in the thread until a reply arrives."""
    prompt = str(node.values.get("prompt", "") or "")
    labels = [str(r.get("label", "")).strip() for r in node.values.get("decisions", []) if isinstance(r, dict)]
    labels = [label for label in labels if label]
    enable_unmatched = bool(node.values.get("enable_unmatched", False))
    result_key = _human_input_result_key(node.id)

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        answer = interrupt(
            {
                "type": "human_input",
                "node_id": node.id,
                "prompt": prompt,
                "decisions": labels,
            }
        )
        chosen = _match_decision(answer, labels)
        if chosen is None:
            if not enable_unmatched:
                raise FlowBuildError(
                    f"HumanInput '{node.id}' got an answer matching no action "
                    f"({answer!r}) and no unmatched branch is enabled"
                )
            # B9: the node used to route on `chosen` but never put the human's
            # decision into the message stream. A downstream agent reads its
            # input off the *last message* (`_extract_query`), so it saw
            # whatever preceded HumanInput — never the decision — and fell
            # back to re-answering the original request. One clean message
            # carries both what happened and (for the unmatched branch,
            # where there is no label) the raw text so the continuing agent
            # can react to it.
            visible = str(answer.get("decision") if isinstance(answer, dict) else answer or "")
            chosen = _HUMAN_INPUT_UNMATCHED
        else:
            visible = chosen
        update: dict[str, Any] = {"scratch": {result_key: chosen, node.id: answer}}
        if visible.strip():
            update["messages"] = [HumanMessage(content=visible)]
        return update

    return _run


def _make_human_input_route_fn(node: FlowNode, edges: list[FlowEdge]):
    """Pure state read: route on the decision the node stored."""
    result_key = _human_input_result_key(node.id)
    label_to_target = {e.source_handle: e.target for e in edges if e.source == node.id}

    def _route(state: FlowState) -> str:
        choice = state.get("scratch", {}).get(result_key)
        handle = "unmatched" if choice == _HUMAN_INPUT_UNMATCHED else choice
        target = label_to_target.get(handle) or label_to_target.get("unmatched")
        if target is None:
            raise FlowBuildError(f"HumanInput '{node.id}' has no edge for action {choice!r}")
        return target

    return _route
