"""Agent API routes."""

import logging

from fastapi import APIRouter

from schema import ServiceMetadata

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])


@router.get("/info")
async def get_service_info() -> ServiceMetadata:
    """Get service metadata including available agents and models."""
    from agents import DEFAULT_AGENT, get_all_agent_info
    from core import settings

    models = list(settings.AVAILABLE_MODELS)
    models.sort()
    return ServiceMetadata(
        agents=get_all_agent_info(),
        models=models,
        default_agent=DEFAULT_AGENT,
        default_model=settings.DEFAULT_MODEL,
    )
