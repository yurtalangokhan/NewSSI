"""Web search admin configuration routes."""

from typing import Any

from fastapi import APIRouter, Depends

from controller import WebSearchController, get_web_search_controller
from api.dependencies import require_user

router = APIRouter(
    prefix="/api/admin/web-search",
    tags=["web-search"],
    dependencies=[Depends(require_user)],
)


def _get_controller() -> WebSearchController:
    return get_web_search_controller()


@router.get("/search-providers")
async def list_search_providers() -> list[dict[str, Any]]:
    return _get_controller().list_search_providers()


@router.get("/content-providers")
async def list_content_providers() -> list[dict[str, Any]]:
    return _get_controller().list_content_providers()


@router.post("/content-providers/test")
async def test_content_provider(payload: dict[str, Any]) -> dict[str, Any]:
    provider_type = payload.get("provider_type", "onyx_web_crawler")
    return _get_controller().test_content_provider(provider_type)


@router.post("/content-providers/crawl")
async def crawl_url(payload: dict[str, Any]) -> dict[str, Any]:
    """Crawl a single URL with the built-in web crawler and return the result."""
    url: str = payload.get("url") or ""
    return _get_controller().crawl_url(url)


@router.post("/content-providers/reset-default")
async def reset_default_content_provider() -> dict[str, Any]:
    return _get_controller().reset_default_content_provider()


@router.post("/content-providers/{provider_id}/activate")
async def activate_content_provider(provider_id: int) -> dict[str, Any]:
    return _get_controller().activate_content_provider(provider_id)


@router.post("/content-providers/{provider_id}/deactivate")
async def deactivate_content_provider(provider_id: int) -> dict[str, Any]:
    return _get_controller().deactivate_content_provider(provider_id)
