"""
Agent helpers shared across route modules.

Contains logic to resolve stored assistants, create configured
agent graphs, and handle user input (including interrupt resumption).
This module is the single place that both agent_routes and run_routes
import from, avoiding circular dependencies.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from i18n import t
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler  # type: ignore[import-untyped]
from langgraph.types import Command

from agents import AgentGraph
from core import settings
from core.logger import get_logger
from models.chat import UserInput

__all__ = [
    "get_graph_and_config",
    "get_configured_agent",
    "_handle_input",
]

logger = get_logger(__name__)


# =============================================================================
# Graph / config resolution
# =============================================================================


async def get_graph_and_config(agent_id: str | int) -> tuple[str, dict]:
    """Helper to get graph_id and config, resolving stored assistants and personas."""
    from service.StoreService import get_assistant_from_store

    agent_id = str(agent_id)
    config: dict = {}
    graph_id = agent_id  # Default to agent_id as graph_id

    # Check if agent_id is an AgentDefinition UUID.
    # Dynamic agent tools read rag_config from RunnableConfig.configurable,
    # so expose the definition's runtime settings here.
    try:
        from agents.storage.repository import AgentDefinitionRepository

        definition_uuid = UUID(agent_id)
        definition = await AgentDefinitionRepository().get_by_id(definition_uuid)
        if definition:
            definition_cfg = definition.to_config() or {}
            runtime_cfg: dict[str, Any] = {}

            if definition_cfg.get("model"):
                runtime_cfg["model"] = definition_cfg["model"]
            if definition_cfg.get("system_prompt"):
                runtime_cfg["system_prompt"] = definition_cfg["system_prompt"]
            if definition_cfg.get("mcp_tools"):
                runtime_cfg["mcp_tools"] = definition_cfg["mcp_tools"]
            if definition_cfg.get("mcp_tool_configs"):
                runtime_cfg["mcp_tool_configs"] = definition_cfg["mcp_tool_configs"]
            if definition_cfg.get("rag_config"):
                runtime_cfg["rag_config"] = definition_cfg["rag_config"]
            if definition_cfg.get("memory_type"):
                runtime_cfg["memory_type"] = definition_cfg["memory_type"]

            return graph_id, runtime_cfg
    except (ValueError, AttributeError):
        pass

    # Check if agent_id is a persona ID (numeric) - for custom agents
    if agent_id.isdigit():
        from service.PersonaRepository import PersonaDB

        try:
            persona = await PersonaDB.get(int(agent_id))
            if persona and not persona.get("is_builtin"):
                # Custom persona - use base_agent, MCP tools, and RAG config
                base_agent = persona.get("base_agent")
                mcp_tools = persona.get("mcp_tools", [])
                mcp_tool_configs = persona.get("mcp_tool_configs") or {}
                rag_config = persona.get("rag_config") or {}

                if base_agent == "dynamic-agent":
                    from agents.storage.repository import AgentDefinitionRepository

                    definition = await AgentDefinitionRepository().get_by_persona_id(int(agent_id))
                    if definition:
                        definition_cfg = definition.to_config() or {}
                        runtime_cfg: dict[str, Any] = {}
                        if persona.get("user_id"):
                            runtime_cfg["owner_user_id"] = str(persona["user_id"])
                        for key in (
                            "model",
                            "system_prompt",
                            "mcp_tools",
                            "mcp_tool_configs",
                            "rag_config",
                            "memory_type",
                        ):
                            if definition_cfg.get(key):
                                runtime_cfg[key] = definition_cfg[key]
                        return str(definition.id), runtime_cfg

                if base_agent:
                    graph_id = base_agent

                if mcp_tools:
                    config["mcp_tools"] = mcp_tools
                if mcp_tool_configs:
                    config["mcp_tool_configs"] = mcp_tool_configs

                if rag_config:
                    config["rag_config"] = rag_config

                # Also include system_prompt from persona
                system_prompt = persona.get("system_prompt")
                if system_prompt:
                    config["system_prompt"] = system_prompt

                logger.info(
                    f"Loaded persona config: base_agent={graph_id}, mcp_tools={mcp_tools}, rag_config_keys={list(rag_config.keys())}"
                )
                return graph_id, config
        except Exception as e:
            logger.warning(f"Could not load persona {agent_id}: {e}")

    # Check for assistant in database
    try:
        stored = await get_assistant_from_store(agent_id)
        if stored:
            graph_id = stored.get("graph_id", agent_id)
            config = stored.get("config", {})
            return graph_id, config
    except Exception as e:
        logger.warning(f"Could not load stored assistant {agent_id}: {e}")

    return graph_id, config


async def get_configured_agent(agent_id: str | int, agent_config: dict) -> AgentGraph:
    """
    Get agent with dynamic configuration applied.
    For supervisor agents, creates a configured graph based on the config.

    Args:
        agent_id: The base agent/graph ID
        agent_config: Configuration including sub_agents or pipeline_stages

    Returns:
        Configured agent graph
    """
    from agents.agents import agents
    from agents.lazy_agent import LazyLoadingAgent

    # Resolve stored assistants to their graph_id
    graph_id, stored_config = await get_graph_and_config(agent_id)

    # Merge configs (agent_config takes precedence)
    merged_config = {**stored_config, **agent_config}

    try:
        from agents.storage.repository import AgentDefinitionRepository

        definition_uuid = UUID(graph_id)
        definition = await AgentDefinitionRepository().get_by_id(definition_uuid)
        if definition:
            from agents.dynamic_agent import (
                DynamicAgent,
                cache_agent,
                get_cached_agent,
            )

            definition_id = str(definition.id)
            cached = get_cached_agent(definition_id)
            if cached is not None:
                return cached

            dynamic_agent = DynamicAgent(definition.to_config())
            cache_agent(definition_id, dynamic_agent)
            return dynamic_agent
    except (ValueError, AttributeError):
        pass

    # Get the base agent
    agent_entry = agents.get(graph_id)
    if not agent_entry:
        raise HTTPException(status_code=404, detail=t("agent.not_found", agent_id=graph_id))

    graph_like = agent_entry.graph_like

    # Check if this is a dynamic supervisor that needs configuration
    if isinstance(graph_like, LazyLoadingAgent):
        # Handle flat supervisor (sub_agents)
        if hasattr(graph_like, "create_configured_graph") and "sub_agents" in merged_config:
            sub_agents_config = merged_config.get("sub_agents", [])
            supervisor_prompt = merged_config.get("supervisor_prompt")
            model_name = merged_config.get("model")

            if (
                sub_agents_config
                and isinstance(sub_agents_config, list)
                and len(sub_agents_config) > 0
            ):
                if isinstance(sub_agents_config[0], dict):
                    return graph_like.create_configured_graph(
                        sub_agents_config,
                        supervisor_prompt=supervisor_prompt,
                        model_name=model_name,
                    )

        # Handle pipeline supervisor (pipeline_stages)
        if hasattr(graph_like, "create_configured_graph") and "pipeline_stages" in merged_config:
            pipeline_stages = merged_config.get("pipeline_stages", [])
            model_name = merged_config.get("model")
            retry_count = merged_config.get("retry_count", 2)
            on_error = merged_config.get("on_error", "abort")

            if pipeline_stages:
                return graph_like.create_configured_graph(
                    pipeline_stages,
                    model_name=model_name,
                    retry_count=retry_count,
                    on_error=on_error,
                )

        # Handle mcp_tools for custom agents (configurable-mcp-agent pattern)
        if hasattr(graph_like, "create_configured_graph") and "mcp_tools" in merged_config:
            mcp_tools = merged_config.get("mcp_tools", [])
            system_prompt = merged_config.get("system_prompt")
            model_name = merged_config.get("model")

            if mcp_tools or system_prompt:
                return graph_like.create_configured_graph(
                    mcp_tools=mcp_tools,
                    system_prompt=system_prompt,
                    model_name=model_name,
                )

        # Return default graph
        return graph_like.get_graph()

    # For non-lazy agents, return directly
    return graph_like


# =============================================================================
# Input handling (shared by invoke / stream / run endpoints)
# =============================================================================


async def _handle_input(
    user_input: UserInput,
    agent: AgentGraph,
    api_key_user_id: str | None = None,
) -> tuple[dict[str, Any], UUID]:
    """
    Parse user input and handle any required interrupt resumption.
    Returns kwargs for agent invocation and the run_id.

    Args:
        user_input: The user input data
        agent: The agent graph to use
        api_key_user_id: User ID extracted from x-api-key header (takes priority)
    """
    run_id = uuid4()
    thread_id = user_input.thread_id or str(uuid4())

    # Ensure thread exists in store for tracking history
    try:
        from service.StoreService import add_thread, get_thread_from_store

        if not await get_thread_from_store(thread_id):
            now = datetime.now(UTC).isoformat()
            await add_thread(
                {
                    "thread_id": thread_id,
                    "created_at": now,
                    "updated_at": now,
                    "metadata": {"created_by": "auto_invoke", "user_id": user_input.user_id},
                }
            )
    except Exception as e:
        logger.warning(f"Failed to persist auto-thread: {e}")

    # Priority: 1) api_key_user_id from token, 2) user_input.user_id, 3) generate new UUID
    user_id = api_key_user_id or user_input.user_id or str(uuid4())

    # Get model from thread metadata if not provided in user_input
    selected_model = user_input.model
    if selected_model is None and thread_id:
        try:
            from service.StoreService import get_thread_from_store

            thread = await get_thread_from_store(thread_id)
            if thread:
                metadata = thread.get("metadata", {}) or {}
                selected_model = metadata.get("current_alternate_model")
        except Exception as e:
            logger.warning(f"Failed to get model from thread metadata: {e}")

    configurable: dict[str, Any] = {"thread_id": thread_id, "user_id": user_id}
    try:
        from service.UserServiceClient import get_current_access_token

        access_token = get_current_access_token()
        if access_token:
            configurable["access_token"] = access_token
    except Exception:
        pass
    if selected_model is not None:
        configurable["model"] = selected_model
    mail_attachments = getattr(user_input, "mail_attachments", [])
    if mail_attachments:
        configurable["mail_attachments"] = mail_attachments

    callbacks: list[Any] = []
    if settings.LANGFUSE_TRACING:
        langfuse_handler = CallbackHandler()
        callbacks.append(langfuse_handler)

    if user_input.agent_config:
        # Only thread_id and user_id are truly reserved (security critical).
        # 'model' is intentionally allowed — it will be placed into configurable below.
        reserved_keys = {"thread_id", "user_id"}
        if overlap := reserved_keys & user_input.agent_config.keys():
            logger.warning(f"agent_config contains reserved keys: {overlap}")
            raise HTTPException(
                status_code=422,
                detail=t("agent.reserved_keys_in_config", keys=overlap),
            )
        # Map model_version from llm_override to model key
        agent_cfg = user_input.agent_config.copy()
        if "model_version" in agent_cfg and "model" not in agent_cfg:
            agent_cfg["model"] = agent_cfg["model_version"]
        # Strip non-configurable keys sent by the frontend (temperature, model_provider, etc.)
        # but keep 'model', 'system_prompt', 'mcp_tools' and other agent-relevant keys
        non_configurable_keys = {"temperature", "model_provider", "model_version"}
        for k in non_configurable_keys:
            agent_cfg.pop(k, None)
        configurable.update(agent_cfg)

    # ------------------------------------------------------------------
    # AND-logic: long_term_memory = user toggle AND agent toggle
    # ------------------------------------------------------------------
    agent_ltm = bool(configurable.get("long_term_memory", False))
    us_data: dict = {}
    persona_data = None
    try:
        from service.UserServiceClient import get_user_settings

        us_data = await get_user_settings(user_id)
    except Exception as _ltm_err:
        logger.warning(f"LTM user_settings lookup failed: {_ltm_err}")

    if user_input.agent_id and not str(user_input.agent_id).startswith("dynamic-"):
        try:
            from core.db.repositories.persona_repo import PersonaRepository

            # Prefer the original persona_id passed via agent_config (set by ChatRoute for
            # custom personas) so we read LTM settings from the correct persona rather than
            # the underlying graph key (e.g. "chatbot").
            _pid = configurable.get("_persona_id") or user_input.agent_id
            try:
                _pid = int(_pid)
            except (ValueError, TypeError):
                pass
            persona_data = await PersonaRepository().get(_pid) if isinstance(_pid, int) else None
            if persona_data is None and isinstance(_pid, str):
                persona_data = await PersonaRepository().get_by_builtin_key(_pid)
            if persona_data and not persona_data.get("is_builtin"):
                agent_ltm = bool(persona_data.get("long_term_memory", False))
            elif "memory_type" in configurable:
                # UUID-based dynamic agents: persona lookup yields nothing; fall back to
                # memory_type forwarded from AgentDefinition via get_graph_and_config.
                agent_ltm = configurable["memory_type"] == "long_term"
        except Exception as _ltm_err:
            logger.warning(f"LTM persona lookup failed: {_ltm_err}")
    elif "memory_type" in configurable:
        agent_ltm = configurable["memory_type"] == "long_term"

    # Agent-configured LTM is authoritative for recall/save so memory-enabled
    # agents can always participate in long-term memory across new chats.
    configurable["long_term_memory"] = agent_ltm

    # Extract memory flag (independent gate for LLM extraction).
    # Reuse persona_data already fetched above — no second DB call needed.
    user_extract = bool(us_data.get("extract_memory", True))
    agent_extract = True
    if persona_data and isinstance(persona_data.get("labels"), dict):
        agent_extract = persona_data["labels"].get("extract_memory", True)

    configurable["extract_memory"] = user_extract and agent_extract

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
            from service.CheckpointBranchService import find_fork_point
            from service.StoreService import get_thread_from_store

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
            from service.CheckpointBranchService import find_fork_point_with_message
            from service.StoreService import get_thread_from_store

            edit_thread = await get_thread_from_store(thread_id) if thread_id else None
            edit_thread_metadata = (edit_thread or {}).get("metadata", {}) or {}
            edit_fork_config, raw_target_message = await find_fork_point_with_message(
                agent,
                thread_id=thread_id,
                target_message_id=user_input.edit_target_message_id,
                thread_metadata=edit_thread_metadata,
            )
            if edit_fork_config is not None and raw_target_message is not None:
                edited_kwargs: dict[str, Any] = dict(
                    getattr(raw_target_message, "additional_kwargs", {}) or {}
                )
                edited_kwargs["persona_id"] = configurable.get("_persona_id", 0)
                if configurable.get("model"):
                    edited_kwargs["model"] = configurable["model"]
                edited_message = HumanMessage(
                    content=user_input.message,
                    id=getattr(raw_target_message, "id", None),
                    additional_kwargs=edited_kwargs,
                )
                updated_config = await agent.aupdate_state(
                    edit_fork_config, {"messages": [edited_message]}
                )
                fork_configurable = updated_config["configurable"]
        except Exception as e:
            logger.warning(f"Failed to locate edit fork point, falling back: {e}")

    if fork_configurable is not None:
        configurable = {**configurable, **fork_configurable}

    config = RunnableConfig(
        configurable=configurable,
        run_id=run_id,
        callbacks=callbacks,
        recursion_limit=settings.AGENT_RECURSION_LIMIT,
    )

    # Check for interrupts that need to be resumed
    interrupted_tasks = []
    try:
        state = await agent.aget_state(config=config)
        interrupted_tasks = [
            task for task in state.tasks if hasattr(task, "interrupts") and task.interrupts
        ]
    except Exception as e:
        logger.warning(
            f"aget_state failed (no checkpointer?): {e} — treating as fresh conversation"
        )

    from service.Utils import convert_input_messages

    input: Command | dict[str, Any] | None
    if interrupted_tasks:
        input = Command(resume=user_input.message or "")
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
                input = {
                    "messages": [HumanMessage(content=new_content, additional_kwargs=extra_kwargs)]
                }
            else:
                input = {
                    "messages": [
                        HumanMessage(content=user_input.message, additional_kwargs=extra_kwargs)
                    ]
                }
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
                input = {
                    "messages": [
                        HumanMessage(content=fallback_content, additional_kwargs=extra_kwargs)
                    ]
                }
            else:
                input = {
                    "messages": [
                        HumanMessage(content=user_input.message, additional_kwargs=extra_kwargs)
                    ]
                }
    else:
        raise HTTPException(status_code=400, detail=t("agent.message_or_messages_required"))

    kwargs = {
        "input": input,
        "config": config,
    }

    return kwargs, run_id
