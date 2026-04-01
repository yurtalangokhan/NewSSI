"""
Agent helpers shared across route modules.

Contains logic to resolve stored assistants, create configured
agent graphs, and handle user input (including interrupt resumption).
This module is the single place that both agent_routes and run_routes
import from, avoiding circular dependencies.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler  # type: ignore[import-untyped]
from langgraph.types import Command

from agents import AgentGraph
from core import settings
from schema import UserInput

__all__ = [
    "get_graph_and_config",
    "get_configured_agent",
    "_handle_input",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Graph / config resolution
# =============================================================================


async def get_graph_and_config(agent_id: str) -> tuple[str, dict]:
    """Helper to get graph_id and config, resolving stored assistants."""
    from .store import get_assistant_from_store

    config: dict = {}
    graph_id = agent_id  # Default to agent_id as graph_id

    try:
        stored = await get_assistant_from_store(agent_id)
        if stored:
            graph_id = stored.get("graph_id", agent_id)
            config = stored.get("config", {})
            return graph_id, config
    except Exception as e:
        logger.warning(f"Could not load stored assistant {agent_id}: {e}")

    return graph_id, config


async def get_configured_agent(agent_id: str, agent_config: dict) -> AgentGraph:
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

    # Get the base agent
    agent_entry = agents.get(graph_id)
    if not agent_entry:
        raise HTTPException(status_code=404, detail=f"Agent {graph_id} not found")

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
        from .store import add_thread, get_thread_from_store

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

    if api_key_user_id:
        logger.info(f"Using user_id from Supabase token: {user_id}")
    elif user_input.user_id:
        logger.info(f"Using user_id from request body: {user_id}")
    else:
        logger.info(f"Generated new user_id: {user_id}")

    configurable: dict[str, Any] = {"thread_id": thread_id, "user_id": user_id}
    if user_input.model is not None:
        configurable["model"] = user_input.model

    callbacks: list[Any] = []
    if settings.LANGFUSE_TRACING:
        langfuse_handler = CallbackHandler()
        callbacks.append(langfuse_handler)

    if user_input.agent_config:
        reserved_keys = {"thread_id", "user_id", "model"}
        if overlap := reserved_keys & user_input.agent_config.keys():
            raise HTTPException(
                status_code=422,
                detail=f"agent_config contains reserved keys: {overlap}",
            )
        configurable.update(user_input.agent_config)

    config = RunnableConfig(
        configurable=configurable,
        run_id=run_id,
        callbacks=callbacks,
    )

    # Check for interrupts that need to be resumed
    state = await agent.aget_state(config=config)
    interrupted_tasks = [
        task for task in state.tasks if hasattr(task, "interrupts") and task.interrupts
    ]

    from langchain_core.messages import BaseMessage

    from service.utils import convert_input_messages

    input: Command | dict[str, Any]
    if interrupted_tasks:
        input = Command(resume=user_input.message or "")
    elif user_input.messages:
        # Use messages provided directly
        lc_messages = convert_input_messages(user_input.messages)
        input = {"messages": lc_messages}
    elif user_input.message is not None:
        # Fetch existing messages from checkpointer and append new message
        try:
            current_state = await agent.aget_state(config=config)
            existing_messages = current_state.values.get("messages", [])
            logger.info(f"Found {len(existing_messages)} existing messages in checkpointer")

            # Convert existing messages to HumanMessage/AIMessage if needed
            history_messages: list[BaseMessage] = []
            for msg in existing_messages:
                if isinstance(msg, BaseMessage):
                    history_messages.append(msg)
                elif isinstance(msg, dict):
                    # Handle dict format from checkpoint
                    msg_type = msg.get("type", "human")
                    msg_content = msg.get("content", "")
                    if msg_type == "human":
                        history_messages.append(HumanMessage(content=msg_content))
                    elif msg_type in ("ai", "assistant"):
                        from langchain_core.messages import AIMessage

                        history_messages.append(AIMessage(content=msg_content))

            # Append new message
            history_messages.append(HumanMessage(content=user_input.message))
            input = {"messages": history_messages}
            logger.info(f"Total messages including history: {len(history_messages)}")
        except Exception as e:
            logger.warning(f"Failed to fetch existing messages from checkpointer: {e}")
            # Fall back to just the new message
            input = {"messages": [HumanMessage(content=user_input.message)]}
    else:
        raise HTTPException(
            status_code=400, detail="One of 'message' or 'messages' must be provided."
        )

    kwargs = {
        "input": input,
        "config": config,
    }

    return kwargs, run_id
