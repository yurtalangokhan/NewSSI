from datetime import UTC, datetime
from typing import Any

from error_contract import ForbiddenError, NotFoundError
from localization import t

from schemas.assistants import (
    AssistantCreateRequest,
    AssistantDeleteResponse,
    AssistantResponse,
    AssistantSearchRequest,
    AssistantUpdateRequest,
)
from service.orchestration.assistant_agent_service import get_assistant_agent_service


def agent_to_assistant(agent_id: str, agent_description: str) -> dict[str, Any]:
    """Convert an agent to LangGraph Assistant format."""
    now = datetime.now(UTC).isoformat()
    return {
        "assistant_id": agent_id,
        "graph_id": agent_id,
        "name": agent_id,
        "config": {},
        "metadata": {"description": agent_description, "_x_oap_is_default": True},
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }


class AssistantsApplicationService:
    """Framework-free use cases for this JSON surface."""

    def __init__(self):
        self.domain_service = get_assistant_agent_service()

    async def search_assistants(self, request: AssistantSearchRequest) -> list[AssistantResponse]:
        """
        Search for assistants. Returns all available agents as assistants.
        Compatible with @langchain/langgraph-sdk client.assistants.search()
        """
        service = self.domain_service
        all_agents = service.list_agents()
        assistants: list[dict] = []
        for agent_info in all_agents:
            if request.graph_id and agent_info.get("key") != request.graph_id:
                continue
            assistants.append(agent_to_assistant(agent_info["key"], agent_info.get("description", "")))
        stored = await service.list_assistants()
        for assistant in stored:
            if request.graph_id and assistant.get("graph_id") != request.graph_id:
                continue
            if request.metadata:
                matches = True
                for k, v in request.metadata.items():
                    if assistant.get("metadata", {}).get(k) != v:
                        matches = False
                        break
                if not matches:
                    continue
            assistants.append(assistant)
        start = request.offset
        end = min(start + request.limit, len(assistants))
        if start >= len(assistants):
            return []
        return assistants[start:end]

    async def get_assistant(self, assistant_id: str) -> AssistantResponse:
        """
        Get a specific assistant by ID.
        Compatible with @langchain/langgraph-sdk client.assistants.get()
        """
        service = self.domain_service
        stored = await service.get_assistant(assistant_id)
        if stored:
            return stored
        all_agents = service.list_agents()
        for agent_info in all_agents:
            if agent_info.get("key") == assistant_id:
                return agent_to_assistant(agent_info["key"], agent_info.get("description", ""))
        raise NotFoundError(message_key="assistant.not_found", message_params={"assistant_id": assistant_id})

    async def create_assistant(self, request: AssistantCreateRequest) -> AssistantResponse:
        """
        Create a new assistant.
        Compatible with @langchain/langgraph-sdk client.assistants.create()
        """
        service = self.domain_service
        all_agents = service.list_agents()
        agent_exists = any(a.get("key") == request.graph_id for a in all_agents)
        if not agent_exists:
            raise NotFoundError(message_key="assistant.graph_not_found", message_params={"graph_id": request.graph_id})
        return await service.create_assistant(
            graph_id=request.graph_id, name=request.name, config=request.config, metadata=request.metadata
        )

    async def update_assistant(self, assistant_id: str, request: AssistantUpdateRequest) -> AssistantResponse:
        """
        Update an assistant.
        Compatible with @langchain/langgraph-sdk client.assistants.update()
        """
        service = self.domain_service
        updates: dict = {}
        if request.name:
            updates["name"] = request.name
        if request.config:
            updates["config"] = request.config
        if request.metadata:
            updates["metadata"] = request.metadata
        updated = await service.update_assistant(assistant_id, updates)
        if updated:
            return updated
        all_agents = service.list_agents()
        for agent_info in all_agents:
            if agent_info.get("key") == assistant_id:
                raise ForbiddenError(message_key="assistant.cannot_update_system_template")
        raise NotFoundError(message_key="assistant.not_found", message_params={"assistant_id": assistant_id})

    async def delete_assistant(self, assistant_id: str) -> AssistantDeleteResponse:
        """
        Delete an assistant.
        Compatible with @langchain/langgraph-sdk client.assistants.delete()
        """
        service = self.domain_service
        deleted = await service.delete_assistant(assistant_id)
        if deleted:
            return {"status": "ok", "assistant_id": assistant_id}
        all_agents = service.list_agents()
        for agent_info in all_agents:
            if agent_info.get("key") == assistant_id:
                return {
                    "status": "ok",
                    "assistant_id": assistant_id,
                    "detail": t("assistant.system_template_not_deleted"),
                }
        raise NotFoundError(message_key="assistant.not_found", message_params={"assistant_id": assistant_id})
