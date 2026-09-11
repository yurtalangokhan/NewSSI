from __future__ import annotations

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.store.base import BaseStore
from pydantic import ValidationError

from agents.clarification import is_clarification_tool
from agents.clarification.prompt import ASK_USER_PROMPT
from agents.clarification.tool import get_clarification_tools
from agents.document_tools import (
    DOCUMENT_TOOL_PROMPT,
    bind_document_tools,
    get_document_tools,
    recover_document_tool_args,
)
from core import settings
from core.llm import get_model_from_config
from core.logger import get_logger
from memory.long_term import (
    build_event_emitters,
    build_memory_context,
    extract_and_save_memories,
    recall_memories,
    tag_response_with_ltm_recall,
)
from service.CheckpointerService import get_checkpointer

logger = get_logger(__name__)

# Bounded so a model that keeps emitting tool_calls can't loop forever.
_MAX_DOCUMENT_TOOL_ITERATIONS = 4


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

    return (
        f"Error: {tool_name} was not run — {'; '.join(details) or exc}. "
        "Call it again with every required argument; the full document body "
        "belongs in `content` as Markdown."
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
    if tool_name == "create_document":
        args = recover_document_tool_args(args)
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
        logger.error("Tool %s failed: %s", tool_name, exc, exc_info=True)
        return f"Error: {tool_name} failed: {exc}"


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
    conversation = [SystemMessage(content=system_prompt), *messages]
    new_messages: list = []

    for _ in range(_MAX_DOCUMENT_TOOL_ITERATIONS):
        try:
            ai_message = await bound_model.ainvoke(conversation)
        except Exception as exc:
            exc_str = str(exc).lower()
            if (
                "does not support tools" in exc_str
                or "tools are not supported" in exc_str
                or "not support tool" in exc_str
                or "tool_choice" in exc_str
                or "tool" in exc_str
            ):
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
                    "Not run: ask_user must be called alone. Call this again "
                    "after the user has answered.",
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
    try:
        new_messages.append(await model.ainvoke(conversation))
    except Exception as exc:
        logger.error("Fallback answer after tool loop failed: %s", exc, exc_info=True)
        new_messages.append(
            AIMessage(
                content=(
                    "I couldn't finish creating the document. Please try again, "
                    "or ask for the content directly in the chat."
                )
            )
        )

    return new_messages


async def call_model(
    state: MessagesState, config: RunnableConfig, *, store: BaseStore
) -> MessagesState:
    messages = state["messages"]
    configurable = config.get("configurable", {})
    model = get_model_from_config(configurable, settings.DEFAULT_MODEL)

    # Long-term memory: recall user facts if enabled
    long_term_memory = configurable.get("long_term_memory", False)
    user_id = configurable.get("user_id")
    memories: dict = {}
    on_recall, on_save = build_event_emitters(configurable)

    logger.debug(
        "long_term_memory=%s, user_id=%s, store=%s, store_type=%s",
        long_term_memory,
        user_id,
        store is not None,
        type(store).__name__ if store else "None",
    )

    if long_term_memory and user_id:
        try:
            memories = await recall_memories(store, user_id, on_recall=on_recall)
            logger.debug("Recalled memories: %s", memories)
            memory_context = build_memory_context(memories)
            if memory_context:
                messages = [SystemMessage(content=memory_context)] + list(messages)
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
        messages = [SystemMessage(content=system_prompt.strip())] + list(messages)

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
            extract_mem = configurable.get("extract_memory", True)
            await extract_and_save_memories(
                store,
                user_id,
                list(state["messages"]) + new_messages,
                model,
                memories,
                on_save=on_save,
                extract_memory=extract_mem,
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
    answered = {
        m.tool_call_id
        for m in messages
        if isinstance(m, ToolMessage) and getattr(m, "tool_call_id", None)
    }
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
