from __future__ import annotations

from config_manager import env
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.store.base import BaseStore
from localization import t
from pydantic import ValidationError

from agents.clarification import is_clarification_tool
from agents.clarification.prompt import ASK_USER_PROMPT
from agents.clarification.tool import get_clarification_tools
from agents.graphs.middleware import dead_end_nudge
from agents.tooling.attachment_manifest import has_attachment_tool, with_attachment_manifest
from agents.tooling.document_tool_messages import unexpected_failure
from agents.tooling.document_tools import (
    DOCUMENT_TOOL_PROMPT,
    bind_document_tools,
    get_document_tools,
    recover_document_tool_args,
    recover_edit_tool_args,
)
from core.observability.logger import get_logger
from infrastructure.llm.llm import get_model_from_config
from infrastructure.runtime.checkpointer import get_checkpointer
from memory.long_term import (
    extract_memories_for_turn,
    latest_human_message_text,
    recall_context_for_turn,
    tag_response_with_ltm_recall,
)

logger = get_logger(__name__)

# Bounded so a model that keeps emitting tool_calls can't loop forever.
# list → read → edit → retry → answer fits (design 4.8)
_MAX_DOCUMENT_TOOL_ITERATIONS = 6
# Times a turn that produced neither text nor a tool call is re-asked.
_MAX_DEAD_END_RETRIES = 2


# What to fix on a rejected call, per tool: the body of a document is not what
# every tool is missing, and a wrong hint sends the model down the wrong path.
_RETRY_HINTS = {
    "create_document": "the full document body belongs in `content` (Markdown; a JSON string for json).",
    "create_spreadsheet": 'the data belongs in `sheets` as [{"name": ..., "rows": [[...], ...]}].',
    "rewrite_document": (
        "pass document_id, base_revision_no and summary, and the complete new body in `content` "
        "(for a spreadsheet, the JSON sheets array)."
    ),
    "edit_document": (
        "pass document_id, base_revision_no, summary and `edits`: a list of "
        "{old_str, new_str} objects copied from the latest draft."
    ),
    "read_document": "pass the document_id shown by list_documents.",
    "list_documents": "it takes no arguments.",
    "list_attachments": "it takes no arguments.",
}


def _describe_validation_error(tool_name: str, exc: ValidationError) -> str:
    """Turn a rejected tool call into instructions the model can act on.

    Models regularly call `create_document` without `content` (or with the body
    under some invented key). Naming the offending arguments gives the next
    iteration a real chance of getting it right.
    """
    missing: list[str] = []
    invalid: list[str] = []

    for error in exc.errors():
        field = ".".join(str(part) for part in error.get("loc") or ()) or "argument"
        if error.get("type") == "missing":
            missing.append(field)
        else:
            invalid.append(f"{field} ({error.get('msg', 'invalid')})")

    details: list[str] = []
    if missing:
        details.append(f"missing required argument(s): {', '.join(missing)}")
    if invalid:
        details.append(f"invalid argument(s): {', '.join(invalid)}")

    hint = _RETRY_HINTS.get(tool_name)
    return (
        f"Error: {tool_name} was not run — {'; '.join(details) or exc}. "
        "Call it again with every required argument" + (f"; {hint}" if hint else ".")
    )


async def _run_tool_call(tool, call: dict, config: RunnableConfig) -> str:
    """Invoke one tool call, returning its result or an error for the model.

    A malformed tool call must never end the run: LangGraph's prebuilt ToolNode
    reports tool errors back as the tool's result so the agent can correct
    itself, and this hand-rolled loop has to behave the same way. Letting the
    exception escape kills the whole SSE stream mid-answer.
    """
    tool_name = call.get("name", "tool")
    args = call.get("args") or {}
    if tool_name == "create_document" or tool_name == "rewrite_document":
        args = recover_document_tool_args(args)
    elif tool_name == "edit_document":
        args = recover_edit_tool_args(args)
    try:
        return str(await tool.ainvoke(args, config))
    except GraphBubbleUp:
        # An `interrupt()` (ask_user) pausing the run — NOT a tool failure.
        # It has to bubble past this hand-rolled loop the way it would pass
        # through a prebuilt ToolNode, or the pause turns into an error string.
        raise
    except ValidationError as exc:
        logger.warning("Rejected tool call for %s: %s", tool_name, exc)
        return _describe_validation_error(tool_name, exc)
    except Exception as exc:
        # The real exception goes to the log only (see unexpected_failure).
        return unexpected_failure(tool_name, exc)


# Provider wordings for "this model cannot take tools". Anything broader (a bare
# "tool" in the message) matches unrelated provider errors and would silently
# discard a run that should have failed or been retried.
_TOOLS_UNSUPPORTED_MARKERS = (
    "does not support tools",
    "tools are not supported",
    "not support tool",
)


def _is_tools_unsupported(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TOOLS_UNSUPPORTED_MARKERS)


async def _close_with_plain_answer(model, conversation: list, new_messages: list) -> None:
    """Append a closing answer from the unbound model (no tools available).

    Falls back to a fixed, localized apology when even that call fails, so the
    turn always ends with assistant text.
    """
    try:
        new_messages.append(await model.ainvoke(conversation))
    except Exception as exc:
        logger.error("Fallback answer after tool loop failed: %s", exc, exc_info=True)
        new_messages.append(AIMessage(content=t("agent.tool_loop_incomplete")))


async def _invoke_retrying_dead_end(bound_model, conversation: list) -> AIMessage:
    """Call the model, re-asking a turn that ends with no text and no tool call.

    A reasoning model can plan "I will create the document" and then stop
    without attaching the call; accepted as the final answer, that turn leaves
    the user with a blank or invented reply and no document. The nudge steers
    the retry only — it never enters the saved conversation. This is the same
    recovery the react path gets from DeadEndTurnRetryMiddleware.
    """
    ai_message = await bound_model.ainvoke(conversation)
    nudge_text = dead_end_nudge(ai_message)
    if nudge_text is None:
        return ai_message

    nudged = [*conversation, HumanMessage(content=nudge_text)]
    for attempt in range(_MAX_DEAD_END_RETRIES):
        ai_message = await bound_model.ainvoke(nudged)
        if dead_end_nudge(ai_message) is None:
            return ai_message
        logger.warning("Chatbot turn still a dead end after retry %s/%s", attempt + 1, _MAX_DEAD_END_RETRIES)
    return AIMessage(content=t("agent.tool_loop_incomplete"))


async def _run_with_document_tools(
    model,
    messages: list,
    config: RunnableConfig,
) -> list:
    """Run a bounded tool-calling loop over the document tools and `ask_user`.

    Returns every new message produced (tool-call AIMessages, ToolMessages,
    and the final answer) so the caller can persist them all onto the graph
    state — matching how react-based agents expose tool steps natively.

    `ask_user` rides the same loop as the document tools for BINDING and
    prompting, but not for execution: when the model asks, this returns and
    lets the `clarify` node do the pausing. Nothing here has to guard against
    a resume re-running a document write, because this node is finished and
    committed by the time the run parks.
    """
    document_tools = get_document_tools()
    # Only offer ask_user when a resume is possible (design 5.3, E13). In prod
    # the chatbot graph is handed the global checkpointer at request time.
    clarification_tools = get_clarification_tools() if get_checkpointer() else []
    loop_tools = [*document_tools, *clarification_tools]
    if not loop_tools:
        response = await model.ainvoke(messages)
        return [response]

    bound_model, tools_enabled = bind_document_tools(model, loop_tools)
    if not tools_enabled:
        response = await model.ainvoke(messages)
        return [response]

    tools_by_name = {tool.name: tool for tool in loop_tools}
    system_prompt = DOCUMENT_TOOL_PROMPT
    if clarification_tools:
        system_prompt = f"{system_prompt}\n{ASK_USER_PROMPT}"
    if has_attachment_tool(loop_tools):
        # Resolved once per node run: the tool loop below reuses this conversation.
        system_prompt = await with_attachment_manifest(system_prompt, config)
    conversation = [SystemMessage(content=system_prompt), *messages]
    new_messages: list = []

    for _ in range(_MAX_DOCUMENT_TOOL_ITERATIONS):
        try:
            ai_message = await _invoke_retrying_dead_end(bound_model, conversation)
        except Exception as exc:
            if new_messages:
                # Tool calls already ran and their results are committed work
                # (a saved draft); losing them from the graph state would hide
                # it from the model and the user. Close with a plain answer.
                logger.error("Model call failed mid tool loop: %s", exc, exc_info=True)
                await _close_with_plain_answer(model, conversation, new_messages)
                return new_messages
            if not _is_tools_unsupported(exc):
                raise
            logger.warning(
                "Model does not support tools at runtime (%s: %s); falling back to direct invocation without tools",
                type(exc).__name__,
                exc,
            )
            try:
                response = await model.ainvoke(messages)
                return [response]
            except Exception as fallback_exc:
                logger.error(
                    "Fallback plain invocation also failed: %s",
                    fallback_exc,
                    exc_info=True,
                )
                raise

        conversation.append(ai_message)
        new_messages.append(ai_message)

        tool_calls = getattr(ai_message, "tool_calls", None) or []
        if not tool_calls:
            return new_messages

        def _tool_message(call: dict, index: int, content: str, **extra) -> ToolMessage:
            return ToolMessage(
                content=content,
                # Models occasionally omit the id; a synthetic one keeps the
                # call/result pairing valid instead of raising.
                tool_call_id=call.get("id") or f"call-{len(new_messages)}-{index}",
                name=call.get("name", "tool"),
                **extra,
            )

        ask_calls = [c for c in tool_calls if is_clarification_tool(c.get("name"))]
        other_calls = [c for c in tool_calls if not is_clarification_tool(c.get("name"))]

        if ask_calls:
            # Ask first, then act: anything alongside the question is not run
            # (matching AskUserAloneMiddleware on the react paths). Extra
            # questions beyond the first wait their turn too — one card at a
            # time keeps "which question am I answering" unambiguous.
            for index, call in enumerate(other_calls + ask_calls[1:]):
                skipped = _tool_message(
                    call,
                    index,
                    "Not run: ask_user must be called alone. Call this again after the user has answered.",
                )
                conversation.append(skipped)
                new_messages.append(skipped)

            # The question is NOT asked here. Returning hands it to the
            # `clarify` node, which pauses in a superstep of its own — see
            # that node for why the pause cannot happen inside this one.
            return new_messages

        for index, call in enumerate(other_calls):
            tool_name = call.get("name", "tool")
            tool = tools_by_name.get(tool_name)
            if tool is None:
                content = f"Error: unknown tool '{tool_name}'."
            else:
                content = await _run_tool_call(tool, call, config)

            tool_message = _tool_message(call, index, content)
            conversation.append(tool_message)
            new_messages.append(tool_message)

    # The loop ran out of iterations while the model was still calling tools.
    # Without a closing answer the reply would be a raw tool result, so ask the
    # unbound model (no tools available) for one final plain-text response.
    logger.warning(
        "Document tool loop hit its %s-iteration limit; asking for a plain answer",
        _MAX_DOCUMENT_TOOL_ITERATIONS,
    )
    await _close_with_plain_answer(model, conversation, new_messages)
    return new_messages


async def call_model(state: MessagesState, config: RunnableConfig, *, store: BaseStore) -> MessagesState:
    messages = state["messages"]
    configurable = config.get("configurable", {})
    model = get_model_from_config(configurable, env.DEFAULT_MODEL)

    # Long-term memory: recall user facts if enabled
    long_term_memory = configurable.get("long_term_memory", False)
    user_id = configurable.get("user_id")
    memories: dict = {}

    logger.debug(
        "long_term_memory=%s, user_id=%s, store=%s, store_type=%s",
        long_term_memory,
        user_id,
        store is not None,
        type(store).__name__ if store else "None",
    )

    if long_term_memory and user_id:
        try:
            query = latest_human_message_text(messages)
            memories, memory_context = await recall_context_for_turn(user_id, query, configurable)
            logger.debug("Recalled memories: %s", memories)
            if memory_context:
                messages = [SystemMessage(content=memory_context), *messages]
                logger.debug("Injected memory context into messages")
            else:
                logger.debug("No memory context to inject (empty)")
        except Exception as e:
            logger.error("ERROR during recall: %s", e)
    else:
        logger.debug(
            "Skipping memory: long_term_memory=%s, store=%s, user_id=%s",
            long_term_memory,
            store is not None,
            user_id,
        )

    system_prompt = configurable.get("system_prompt")
    if isinstance(system_prompt, str) and system_prompt.strip():
        messages = [SystemMessage(content=system_prompt.strip()), *messages]

    new_messages = await _run_with_document_tools(model, messages, config)
    # The last message is not always the answer: when the model asks a
    # question, the loop returns with refusals for whatever it called
    # alongside, so the tail can be a ToolMessage. The recall badge belongs on
    # an AIMessage or history reconstruction never finds it.
    response = next(
        (m for m in reversed(new_messages) if isinstance(m, AIMessage)),
        new_messages[-1],
    )
    tag_response_with_ltm_recall(response, memories)

    # Long-term memory: extract and save new facts
    if long_term_memory and user_id:
        try:
            await extract_memories_for_turn(
                user_id,
                configurable,
                list(state["messages"]) + new_messages,
                model,
                memories,
            )
            logger.debug("Memory extraction completed")
        except Exception as e:
            logger.error("ERROR during extraction: %s", e)

    return {"messages": new_messages}


def _pending_ask_user(messages: list) -> dict | None:
    """The `ask_user` call the model made and nobody has answered yet.

    Not simply "the last message asked": the loop appends a refusal for every
    tool the model called ALONGSIDE the question, so the asking AIMessage is
    usually not last. What makes a call pending is the absence of a result for
    it — the same rule a provider applies when it validates the transcript.
    """
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage) and getattr(m, "tool_call_id", None)}
    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        for call in getattr(message, "tool_calls", None) or []:
            if is_clarification_tool(call.get("name")) and call.get("id") not in answered:
                return call
        # Only the most recent turn can still be waiting; an older unanswered
        # question belongs to an abandoned branch.
        return None
    return None


async def clarify(state: MessagesState, config: RunnableConfig) -> MessagesState:
    """Park the run on the model's question — in a superstep of its own.

    Why this is not done inside `call_model`, where the rest of the tool loop
    lives: everything a node writes before `interrupt()` is DISCARDED. Measured
    on a real paused thread, whose newest checkpoint held only the user's
    message — the reasoning, the recalled memories and the tool call had all
    been thrown away, so a reloaded chat showed the question card floating
    alone while the live stream had shown a full timeline.

    Splitting the pause out is what a react graph gets for free from
    model -> tools: the model node commits, and only then does the run park.

    Nothing before the `interrupt()` here has a side effect, which matters
    because a resumed node re-runs from the top (design 3.2). Keep it that way.
    """
    call = _pending_ask_user(state["messages"])
    if call is None:
        return {"messages": []}

    tools = get_clarification_tools()
    if not tools:
        # No checkpointer, so no resume: the model could not have been offered
        # the tool at all. Answer the call rather than leave it dangling —
        # some providers reject a tool_call with no result.
        return {
            "messages": [
                ToolMessage(
                    content="Not run: asking the user is unavailable in this run.",
                    tool_call_id=call.get("id") or "ask-unavailable",
                    name="ask_user",
                )
            ]
        }

    # Invoked as a real tool call so the (content, artifact) pair comes back;
    # `interrupt()` bubbles out on the first pass and returns the user's
    # answer once the run is resumed.
    answer = await tools[0].ainvoke(
        {
            "type": "tool_call",
            "name": "ask_user",
            "args": call.get("args") or {},
            "id": call.get("id") or "ask-1",
        },
        config,
    )
    return {"messages": [answer]}


def _route_after_model(state: MessagesState) -> str:
    return "clarify" if _pending_ask_user(state["messages"]) else END


workflow = StateGraph(MessagesState)
workflow.add_node("model", call_model)
workflow.add_node("clarify", clarify)
workflow.set_entry_point("model")
workflow.add_conditional_edges("model", _route_after_model, {"clarify": "clarify", END: END})
# Back to the model with the answer in hand, so it can carry on with the work.
workflow.add_edge("clarify", "model")

chatbot = workflow.compile()
