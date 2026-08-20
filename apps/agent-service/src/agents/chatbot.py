from __future__ import annotations

from pydantic import ValidationError

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.store.base import BaseStore

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
    """Run a bounded tool-calling loop restricted to the document output tools.

    Returns every new message produced (tool-call AIMessages, ToolMessages,
    and the final answer) so the caller can persist them all onto the graph
    state — matching how react-based agents expose tool steps natively.
    """
    document_tools = get_document_tools()
    if not document_tools:
        response = await model.ainvoke(messages)
        return [response]

    bound_model, tools_enabled = bind_document_tools(model, document_tools)
    if not tools_enabled:
        response = await model.ainvoke(messages)
        return [response]

    tools_by_name = {tool.name: tool for tool in document_tools}
    conversation = [SystemMessage(content=DOCUMENT_TOOL_PROMPT), *messages]
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

        for index, call in enumerate(tool_calls):
            tool_name = call.get("name", "tool")
            tool = tools_by_name.get(tool_name)
            if tool is None:
                content = f"Error: unknown tool '{tool_name}'."
            else:
                content = await _run_tool_call(tool, call, config)

            tool_message = ToolMessage(
                content=content,
                # Models occasionally omit the id; a synthetic one keeps the
                # call/result pairing valid instead of raising.
                tool_call_id=call.get("id") or f"call-{len(new_messages)}-{index}",
                name=tool_name,
            )
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
    response = new_messages[-1]
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


workflow = StateGraph(MessagesState)
workflow.add_node("model", call_model)
workflow.set_entry_point("model")
workflow.add_edge("model", END)

chatbot = workflow.compile()
