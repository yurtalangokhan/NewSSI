"""
Agent helpers shared across route modules.

Contains logic to resolve stored assistants, create configured
agent graphs, and handle user input (including interrupt resumption).
This module is the single place that both agent_routes and run_routes
import from, avoiding circular dependencies.
"""

from __future__ import annotations

from collections.abc import Mapping
import contextlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from config_manager import env
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler  # type: ignore[import-untyped]
from langgraph.types import Command
from localization import t

from agents.primitives.agent_types import AgentGraph
from core.exceptions import BadRequestError, ValidationFailedError
from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import persona_repository
from schemas.chat import UserInput

__all__ = [
    "CONFIGURABLE_ALLOWLIST",
    "_active_document",
    "_handle_input",
    "filter_configurable",
    "get_graph_and_config",
]

# Only these keys survive from a caller-supplied agent_config into
# `configurable`. Everything else -- prompts, tool lists, identity fields,
# credentials -- is server-derived or dropped: configurable.update(agent_cfg)
# previously let a caller override a persona's system_prompt/mcp_tools
# (guardrail bypass) or inject tenant_id/owner_user_id directly. Where those
# identity fields *should* come from instead (a validated token) is
# authorization work and out of scope here; this only ensures they don't
# come from the client. mcp_url is handled separately by
# core.mcp_url_policy.resolve_allowed_mcp_url, never by this allow-list.
#: _persona_id is a reference into server-controlled data (the persona row) --
#: the persona's actual content (system_prompt, tools) is resolved from
#: that record, never taken from the client -- so accepting which id to
#: look up is not the same class of risk as accepting prompt/tool content
#: directly. It was already accepted before this allow-list existed.
#: llm_instance is the live client for the provider/model the user picked. It
#: is built server-side by apply_provider_llm_override *after* the client's
#: llm_override is sanitised (no client allow-list contains it), so accepting it
#: here cannot be used to inject anything; dropping it silently sends a
#: provider-backed model such as Gemini to the Ollama fallback instead.
CONFIGURABLE_ALLOWLIST = frozenset({"model", "thread_id", "mail_attachments", "_persona_id", "llm_instance"})


#: Keys the server may add to `configurable` from the persona, agent definition
#: and project context it resolved itself. They reach a run only through
#: ``UserInput.server_config``, which a request body cannot populate, so the
#: client allow-list above never has to admit them.
SERVER_RESOLVED_CONFIGURABLE_KEYS = frozenset(
    {
        "system_prompt",
        "mcp_tools",
        "mcp_tool_configs",
        "rag_config",
        "connector_bindings",
        "binding_references",
        "memory_type",
    }
)


def filter_configurable(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Drop every key the caller is not allowed to set in `configurable`."""
    return {k: v for k, v in (raw or {}).items() if k in CONFIGURABLE_ALLOWLIST}


def _server_resolved_configurable(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in raw.items() if k in SERVER_RESOLVED_CONFIGURABLE_KEYS and v}


def _active_document(user_input: UserInput) -> dict[str, Any] | None:
    """Project `user_input.document_context` into `configurable["active_document"]`.

    Returns None when the client sent no document_context, so callers can
    skip the key entirely instead of storing a null placeholder in
    `configurable` (which is persisted verbatim into checkpoint metadata).
    This is the only place the open document reaches the run: it is exposed
    to document tools via run config, never injected as a note into the
    HumanMessage, so the conversation history stays clean and mid-conversation
    system messages (rejected by some providers) are never needed.
    """
    if user_input.document_context is None:
        return None
    return {
        "document_id": str(user_input.document_context.document_id),
        "revision_no": user_input.document_context.revision_no,
    }


logger = get_logger(__name__)


def _looks_like_agent_definition_id(value: Any) -> bool:
    """True when ``value`` identifies a dynamic AgentDefinition agent (a UUID
    or a ``dynamic-`` prefixed id) rather than the default chat assistant.

    These agents must opt into long-term memory explicitly via
    ``memory_type``; they are never driven by the user setting alone.
    """
    if isinstance(value, str) and value.startswith("dynamic-"):
        return True
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _agent_participates_in_memory(
    *,
    agent_id: Any,
    persona_data: dict[str, Any] | None,
    configurable: dict[str, Any],
) -> bool:
    """Decide whether this agent may use long-term memory at all.

    * custom (non-builtin) persona  → its own ``long_term_memory`` toggle
    * ``memory_type`` forwarded      → ``memory_type == "long_term"``
    * builtin persona / default assistant / plain model chatbot → always
      (the user's "Depolanan Belleğe Başvur" setting is then the sole driver)
    * dynamic AgentDefinition agent that did not opt in → never
    """
    if persona_data and not persona_data.get("is_builtin"):
        return bool(persona_data.get("long_term_memory", False))
    if "memory_type" in configurable:
        return configurable["memory_type"] == "long_term"
    if persona_data and persona_data.get("is_builtin"):
        return True
    return not _looks_like_agent_definition_id(agent_id)


# =============================================================================
# Graph / config resolution
# =============================================================================


async def get_graph_and_config(agent_id: str | int) -> tuple[str, dict]:
    """Helper to get graph_id and config, resolving stored assistants and personas."""
    from service.orchestration.assistant_agent_service import AssistantAgentService

    return await AssistantAgentService.get_instance().get_graph_and_config(agent_id)


# =============================================================================
# Input handling (shared by invoke / stream / run endpoints)
# =============================================================================


async def _handle_input(
    user_input: UserInput,
    agent: AgentGraph,
    authenticated_user_id: str,
) -> tuple[dict[str, Any], UUID]:
    """
    Parse user input and handle any required interrupt resumption.
    Returns kwargs for agent invocation and the run_id.

    Args:
        user_input: The user input data
        agent: The agent graph to use
        authenticated_user_id: The acting user, taken from the authenticated
            principal. It is never read from the body or from a raw header:
            this id selects long-term memory, the SMTP identity and thread
            ownership, so letting the request name it is impersonation.
    """
    run_id = uuid4()
    thread_id = user_input.thread_id or str(uuid4())

    # Ensure thread exists in store for tracking history
    try:
        from service.runtime.store_service import add_thread, get_thread_from_store

        if not await get_thread_from_store(thread_id):
            now = datetime.now(UTC).isoformat()
            await add_thread(
                {
                    "thread_id": thread_id,
                    "created_at": now,
                    "updated_at": now,
                    "metadata": {
                        "created_by": "auto_invoke",
                        "user_id": authenticated_user_id,
                    },
                }
            )
    except Exception as e:
        logger.warning(f"Failed to persist auto-thread: {e}")

    user_id = authenticated_user_id

    # Get model from thread metadata if not provided in user_input
    selected_model = user_input.model
    if selected_model is None and thread_id:
        try:
            from service.runtime.store_service import get_thread_from_store

            thread = await get_thread_from_store(thread_id)
            if thread:
                metadata = thread.get("metadata", {}) or {}
                selected_model = metadata.get("current_alternate_model")
        except Exception as e:
            logger.warning(f"Failed to get model from thread metadata: {e}")

    configurable: dict[str, Any] = {"thread_id": thread_id, "user_id": user_id}
    # access_token is deliberately NOT placed in configurable: configurable
    # is persisted verbatim into checkpoint metadata by the checkpointer,
    # and /threads/{id}/state and /threads/{id}/history return that
    # metadata to the caller -- so a token stored here is a credential
    # disclosure, not just an internal implementation detail. Callers that
    # need the token (see agents/graphs/flow_builder.py's RAG/graph nodes)
    # read it directly via UserServiceClient.get_current_access_token(),
    # which is already the ContextVar this value came from.
    if selected_model is not None:
        configurable["model"] = selected_model
    mail_attachments = getattr(user_input, "mail_attachments", [])
    if mail_attachments:
        configurable["mail_attachments"] = mail_attachments

    callbacks: list[Any] = []
    if env.LANGFUSE_TRACING:
        langfuse_handler = CallbackHandler()
        callbacks.append(langfuse_handler)

    if user_input.agent_config:
        # Only thread_id and user_id are truly reserved (security critical).
        # 'model' is intentionally allowed — it will be placed into configurable below.
        reserved_keys = {"thread_id", "user_id"}
        if overlap := reserved_keys & user_input.agent_config.keys():
            logger.warning(f"agent_config contains reserved keys: {overlap}")
            raise ValidationFailedError(
                code="agent.reserved_keys_in_config",
                message=t("agent.reserved_keys_in_config", keys=overlap),
                details={"keys": sorted(overlap)},
            )
        # Map model_version from llm_override to model key
        agent_cfg = user_input.agent_config.copy()
        if "model_version" in agent_cfg and "model" not in agent_cfg:
            agent_cfg["model"] = agent_cfg["model_version"]
        # Only CONFIGURABLE_ALLOWLIST keys survive: this also drops
        # temperature/model_provider/model_version (never configurable) and,
        # more importantly, system_prompt/mcp_tools/tenant_id/owner_user_id/
        # access_token and anything else a caller might try to inject.
        configurable.update(filter_configurable(agent_cfg))
    configurable.update(_server_resolved_configurable(user_input.server_config))

    # ------------------------------------------------------------------
    # Memory gate — the user's personalization settings are the master switch:
    #   long_term_memory = "Depolanan Belleğe Başvur" AND agent participates
    #   extract_memory   = long_term_memory AND "Belleği Güncelle"
    #                                       AND agent-level extract label
    #
    # An agent "participates" when it is the default assistant / plain model
    # chatbot (the user setting is then the sole driver), when a custom
    # persona has its own long_term_memory toggle on, or when a dynamic
    # AgentDefinition sets memory_type == "long_term".
    # ------------------------------------------------------------------
    us_data: dict = {}
    persona_data = None
    try:
        from integrations.user_service_client import get_user_settings

        us_data = await get_user_settings(user_id)
    except Exception as _ltm_err:
        logger.warning(f"LTM user_settings lookup failed: {_ltm_err}")

    if user_input.agent_id and not str(user_input.agent_id).startswith("dynamic-"):
        try:
            # Prefer the original persona_id passed via agent_config (set by chat_route for
            # custom personas) so we read LTM settings from the correct persona rather than
            # the underlying graph key (e.g. "chatbot").
            _pid = configurable.get("_persona_id") or user_input.agent_id
            with contextlib.suppress(ValueError, TypeError):
                _pid = int(_pid)
            persona_data = await persona_repository().get(_pid) if isinstance(_pid, int) else None
            if persona_data is None and isinstance(_pid, str):
                persona_data = await persona_repository().get_by_builtin_key(_pid)
        except Exception as _ltm_err:
            logger.warning(f"LTM persona lookup failed: {_ltm_err}")

    agent_participates = _agent_participates_in_memory(
        agent_id=user_input.agent_id,
        persona_data=persona_data,
        configurable=configurable,
    )

    user_recall = bool(us_data.get("long_term_memory_enabled", False))
    user_extract = bool(us_data.get("extract_memory", True))
    agent_extract = True
    if persona_data and isinstance(persona_data.get("labels"), dict):
        agent_extract = persona_data["labels"].get("extract_memory", True)

    from memory.memory_flags import resolve_memory_flags

    long_term_memory, extract_memory = resolve_memory_flags(
        user_recall_enabled=user_recall,
        user_extract_enabled=user_extract,
        agent_participates=agent_participates,
        agent_extract_allowed=bool(agent_extract),
    )
    configurable["long_term_memory"] = long_term_memory
    configurable["extract_memory"] = extract_memory

    # A retry must generate its response without the previous (rejected)
    # response in context. Locate the checkpoint right after the retried
    # human message — before its original response — and invoke the graph
    # from there instead of the thread's tip, giving the retry a genuine
    # branch. The rejected response stays untouched in its own branch,
    # readable via get_chat_session. If no fork point resolves (legacy
    # thread predating this, or the target message no longer exists), fall
    # back to the original append-a-duplicate-message behavior further
    # below — a retry must never hard-fail over this.
    fork_configurable: dict[str, Any] | None = None
    if user_input.is_regenerate and user_input.retry_target_message_id is not None:
        try:
            from service.runtime.checkpoint_branch_service import find_fork_point
            from service.runtime.store_service import get_thread_from_store

            fork_thread = await get_thread_from_store(thread_id) if thread_id else None
            fork_thread_metadata = (fork_thread or {}).get("metadata", {}) or {}
            fork_config = await find_fork_point(
                agent,
                thread_id=thread_id,
                target_message_id=user_input.retry_target_message_id,
                thread_metadata=fork_thread_metadata,
            )
            if fork_config is not None:
                fork_configurable = fork_config["configurable"]
        except Exception as e:
            logger.warning(f"Failed to locate retry fork point, falling back: {e}")

    # Editing a previous message must fork the same way a retry does — the
    # edited message's own id is both the fork target (same as a retry) and
    # the message whose content gets replaced. aupdate_state applies the
    # add_messages reducer's same-id-replaces semantics on top of the forked
    # checkpoint, producing a new checkpoint with the edit applied and no
    # response yet; the caller then treats it exactly like a retry fork
    # (input=None) so the model regenerates without the old response — or
    # anything sent after it — in context. The old branch stays untouched.
    if user_input.is_edit and user_input.edit_target_message_id is not None and user_input.message is not None:
        try:
            from service.runtime.checkpoint_branch_service import find_fork_point_with_message
            from service.runtime.store_service import get_thread_from_store

            edit_thread = await get_thread_from_store(thread_id) if thread_id else None
            edit_thread_metadata = (edit_thread or {}).get("metadata", {}) or {}
            edit_fork_config, raw_target_message = await find_fork_point_with_message(
                agent,
                thread_id=thread_id,
                target_message_id=user_input.edit_target_message_id,
                thread_metadata=edit_thread_metadata,
            )
            if edit_fork_config is not None and raw_target_message is not None:
                edited_kwargs: dict[str, Any] = dict(getattr(raw_target_message, "additional_kwargs", {}) or {})
                edited_kwargs["persona_id"] = configurable.get("_persona_id", 0)
                if configurable.get("model"):
                    edited_kwargs["model"] = configurable["model"]
                edited_message = HumanMessage(
                    content=user_input.message,
                    id=getattr(raw_target_message, "id", None),
                    additional_kwargs=edited_kwargs,
                )
                updated_config = await agent.aupdate_state(edit_fork_config, {"messages": [edited_message]})
                fork_configurable = updated_config["configurable"]
        except Exception as e:
            logger.warning(f"Failed to locate edit fork point, falling back: {e}")

    if fork_configurable is not None:
        configurable = {**configurable, **fork_configurable}

    if (active_document := _active_document(user_input)) is not None:
        configurable["active_document"] = active_document

    config = RunnableConfig(
        configurable=configurable,
        run_id=run_id,
        callbacks=callbacks,
        recursion_limit=env.AGENT_RECURSION_LIMIT,
    )

    # Check for interrupts that need to be resumed
    interrupted_tasks = []
    try:
        state = await agent.aget_state(config=config)
        interrupted_tasks = [task for task in state.tasks if hasattr(task, "interrupts") and task.interrupts]
    except Exception as e:
        logger.warning(f"aget_state failed (no checkpointer?): {e} — treating as fresh conversation")

    from service.chat.message_conversion import convert_input_messages

    input: Command | dict[str, Any] | None
    if interrupted_tasks and fork_configurable is None:
        # A structured payload (e.g. a Human Input decision or a set of
        # ask_user answers) wins over the plain message text; both are
        # accepted by the interrupting node — a bare string reaches ask_user
        # as "the user said this instead of answering".
        #
        # A fork never resumes: retrying or editing branches from an EARLIER
        # checkpoint, so the pending interrupt belongs to the branch being
        # abandoned and must stay unresumed (design E8). The fork's own state
        # happens to carry no interrupt today, which made this work by
        # accident; the condition says it out loud instead.
        input = Command(resume=user_input.resume_payload or user_input.message or "")
    elif fork_configurable is not None:
        # State already ends at the target human message (for a retry) or at
        # its just-replaced content (for an edit, via aupdate_state above),
        # with no response yet — nothing new to add. Appending a duplicate
        # here would put the very thing we forked away from right back in
        # context.
        input = None
    elif user_input.messages:
        # Use messages provided directly
        lc_messages = convert_input_messages(user_input.messages)
        input = {"messages": lc_messages}
    elif user_input.message is not None:
        # Fetch existing messages from checkpointer and append new message
        try:
            current_state = await agent.aget_state(config=config)
            existing_messages = current_state.values.get("messages", [])
            _ = existing_messages  # available for debugging; LangGraph manages history via thread state

            # Build only the NEW HumanMessage — LangGraph appends it to the existing
            # thread state automatically, so we must NOT re-pass the full history here.
            # Re-passing history would cause file content blocks (images/text) from
            # previous messages to be fed to the LLM again on every new message.
            file_blocks: list[dict[str, Any]] = getattr(user_input, "file_content_blocks", [])
            files_meta: list[dict[str, Any]] = getattr(user_input, "files_metadata", [])
            # Store lightweight file metadata in additional_kwargs so the LangGraph
            # checkpointer persists it and get_chat_session can reconstruct file badges.
            extra_kwargs: dict[str, Any] = {"files_metadata": files_meta} if files_meta else {}
            # Stamp which agent/model produced this turn onto the message itself —
            # thread-level metadata only ever holds the most recently sent value,
            # so a retry (or an agent switch) makes it stale for earlier turns.
            # get_chat_session reads this back per message instead of relying on
            # the thread-level value alone.
            extra_kwargs["persona_id"] = configurable.get("_persona_id", 0)
            if configurable.get("model"):
                extra_kwargs["model"] = configurable["model"]
            if getattr(user_input, "is_regenerate", False):
                extra_kwargs["is_regenerate"] = True
            if file_blocks:
                new_content: list[dict[str, Any]] = (
                    [{"type": "text", "text": user_input.message}] if user_input.message else []
                )
                new_content.extend(file_blocks)
                input = {"messages": [HumanMessage(content=new_content, additional_kwargs=extra_kwargs)]}
            else:
                input = {"messages": [HumanMessage(content=user_input.message, additional_kwargs=extra_kwargs)]}
        except Exception as e:
            logger.warning(f"Failed to fetch existing messages from checkpointer: {e}")
            # Fall back to just the new message
            file_blocks = getattr(user_input, "file_content_blocks", [])
            files_meta = getattr(user_input, "files_metadata", [])
            extra_kwargs = {"files_metadata": files_meta} if files_meta else {}
            extra_kwargs["persona_id"] = configurable.get("_persona_id", 0)
            if configurable.get("model"):
                extra_kwargs["model"] = configurable["model"]
            if getattr(user_input, "is_regenerate", False):
                extra_kwargs["is_regenerate"] = True
            if file_blocks:
                fallback_content: list[dict[str, Any]] = (
                    [{"type": "text", "text": user_input.message}] if user_input.message else []
                )
                fallback_content.extend(file_blocks)
                input = {"messages": [HumanMessage(content=fallback_content, additional_kwargs=extra_kwargs)]}
            else:
                input = {"messages": [HumanMessage(content=user_input.message, additional_kwargs=extra_kwargs)]}
    else:
        raise BadRequestError(
            code="agent.message_or_messages_required",
            message=t("agent.message_or_messages_required"),
        )

    kwargs = {
        "input": input,
        "config": config,
    }

    return kwargs, run_id
