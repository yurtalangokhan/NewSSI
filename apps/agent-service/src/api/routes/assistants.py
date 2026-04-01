"""Assistant API routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies import extract_user_id_from_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["assistants"])


@router.post("/assistants")
async def create_assistant(
    graph_id: str,
    name: str | None = None,
    config: dict | None = None,
    metadata: dict | None = None,
    user_id: str = Depends(extract_user_id_from_token),
) -> dict[str, Any]:
    """Create a new assistant."""
    from domain.assistants.service import AssistantService

    service = AssistantService()
    return await service.create_assistant(graph_id, name=name, config=config, metadata=metadata)


@router.get("/assistants/{assistant_id}")
async def get_assistant(
    assistant_id: str,
    user_id: str = Depends(extract_user_id_from_token),
) -> dict[str, Any] | None:
    """Get an assistant by ID."""
    from domain.assistants.service import AssistantService

    service = AssistantService()
    return await service.get_assistant(assistant_id)


@router.get("/assistants")
async def list_assistants(
    user_id: str = Depends(extract_user_id_from_token),
) -> list[dict[str, Any]]:
    """List all assistants."""
    from domain.assistants.service import AssistantService

    service = AssistantService()
    return await service.list_assistants()


@router.patch("/assistants/{assistant_id}")
async def update_assistant(
    assistant_id: str,
    updates: dict[str, Any],
    user_id: str = Depends(extract_user_id_from_token),
) -> dict[str, Any] | None:
    """Update an assistant."""
    from domain.assistants.service import AssistantService

    service = AssistantService()
    return await service.update_assistant(assistant_id, updates)


@router.delete("/assistants/{assistant_id}")
async def delete_assistant(
    assistant_id: str,
    user_id: str = Depends(extract_user_id_from_token),
) -> bool:
    """Delete an assistant."""
    from domain.assistants.service import AssistantService

    service = AssistantService()
    return await service.delete_assistant(assistant_id)
