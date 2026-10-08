"""Agent metadata, invocation and history use cases."""

import json
from typing import Any

from config_manager import env
from error_contract import ApplicationError, DependencyResponseError, InternalServerError
from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.runnables import RunnableConfig

from core.observability.logger import get_logger
from schemas.agent_config_policy import sanitize_client_agent_config
from schemas.agents import ServiceMetadata
from schemas.chat import ChatHistory, ChatMessage, UserInput
from service.agents import DEFAULT_AGENT, get_agent_graph, get_all_agent_info
from service.auth.auth_service import AuthenticatedUser
from service.chat.message_conversion import langchain_to_chat_message
from service.orchestration.agent_runner_coordinator import _handle_input
from service.orchestration.assistant_agent_service import AssistantAgentService
from service.personas import get_persona_service

logger = get_logger(__name__)


async def info() -> ServiceMetadata:
    from infrastructure.llm.adapters.registry import provider_registry

    provider_registry.initialize()
    all_models = await provider_registry.get_model_names()
    all_models.sort()
    default_model = env.DEFAULT_MODEL or None
    if default_model and default_model.lower() in {"ollama", "default", "provider", "builtin"}:
        default_model = env.OLLAMA_MODEL or "llama3.1:8b"
    if (not default_model or default_model not in all_models) and all_models:
        default_model = all_models[0]
    return ServiceMetadata(
        agents=get_all_agent_info(),
        models=all_models,
        default_agent=DEFAULT_AGENT,
        default_model=default_model or "fake",
    )


async def invoke(user: AuthenticatedUser, user_input: UserInput, agent_id: str) -> ChatMessage:
    """
    Invoke an agent with user input to retrieve a final response.

    If agent_id is not provided, the default agent will be used.
    Use thread_id to persist and continue a multi-turn conversation. run_id kwarg
    is also attached to messages for recording feedback.
    Use user_id to persist and continue a conversation across multiple threads.

    Conversations are always persisted under the authenticated caller.
    """
    await get_persona_service().authorize_agent_execution(agent_id, user)
    user_id = user.user_id
    service = AssistantAgentService.get_instance()
    _, stored_config = await service.get_graph_and_config(agent_id)
    user_input.agent_config = sanitize_client_agent_config(user_input.agent_config)
    if stored_config:
        final_config = stored_config.copy()
        final_config.update(user_input.agent_config)
        user_input.agent_config = final_config
    user_input.attach_server_config(stored_config or {})
    agent = await service.get_configured_agent(agent_id, user_input.agent_config or {})
    kwargs, run_id = await _handle_input(user_input, agent, user_id)
    try:
        response_events: list[tuple[str, Any]] = await agent.ainvoke(**kwargs, stream_mode=["updates", "values"])
        response_type, response = response_events[-1]
        if response_type == "values":
            output = langchain_to_chat_message(response["messages"][-1])
        elif response_type == "updates" and "__interrupt__" in response:
            _interrupt_value = response["__interrupt__"][0].value
            output = langchain_to_chat_message(
                AIMessage(
                    content=_interrupt_value if isinstance(_interrupt_value, str) else json.dumps(_interrupt_value)
                )
            )
        else:
            raise DependencyResponseError()
        output.run_id = str(run_id)
        return output
    except ApplicationError:
        raise
    except Exception as e:
        logger.error(f"An exception occurred: {e}")
        raise InternalServerError() from e


async def history(thread_id: str) -> ChatHistory:
    """Get chat history."""
    agent = get_agent_graph(DEFAULT_AGENT)
    try:
        state_snapshot = await agent.aget_state(config=RunnableConfig(configurable={"thread_id": thread_id}))
        messages: list[AnyMessage] = state_snapshot.values["messages"]
        chat_messages: list[ChatMessage] = [langchain_to_chat_message(m) for m in messages]
        return ChatHistory(messages=chat_messages)
    except ApplicationError:
        raise
    except Exception as e:
        logger.error(f"An exception occurred: {e}")
        raise InternalServerError() from e
