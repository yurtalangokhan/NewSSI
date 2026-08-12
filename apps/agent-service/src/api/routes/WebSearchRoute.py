"""Web search admin configuration routes."""

from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies import (
    AuthenticatedUser,
    require_permission,
    require_user,
)
from controller import WebSearchController, get_web_search_controller

router = APIRouter(
    prefix="/api/admin/web-search",
    tags=["web-search"],
    dependencies=[Depends(require_user)],
)


def _get_controller() -> WebSearchController:
    return get_web_search_controller()


@router.get("/search-providers")
async def list_search_providers(
    _user: AuthenticatedUser = Depends(require_permission("web_search:manage")),
) -> list[dict[str, Any]]:
    return _get_controller().list_search_providers()


@router.get("/content-providers")
async def list_content_providers(
    _user: AuthenticatedUser = Depends(require_permission("web_search:manage")),
) -> list[dict[str, Any]]:
    return _get_controller().list_content_providers()


@router.post("/content-providers/test")
async def test_content_provider(
    payload: dict[str, Any],
    _user: AuthenticatedUser = Depends(require_permission("web_search:test")),
) -> dict[str, Any]:
    provider_type = payload.get("provider_type", "atlas_web_crawler")
    return _get_controller().test_content_provider(provider_type)


@router.post("/content-providers/crawl")
async def crawl_url(
    payload: dict[str, Any],
    _user: AuthenticatedUser = Depends(require_permission("web_search:manage")),
) -> dict[str, Any]:
    """Crawl a single URL with the built-in web crawler and return the result."""
    url: str = payload.get("url") or ""
    return _get_controller().crawl_url(url)


@router.post("/content-providers/reset-default")
async def reset_default_content_provider(
    _user: AuthenticatedUser = Depends(require_permission("web_search:manage")),
) -> dict[str, Any]:
    return _get_controller().reset_default_content_provider()


@router.post("/content-providers/{provider_id}/activate")
async def activate_content_provider(
    provider_id: int,
    _user: AuthenticatedUser = Depends(require_permission("web_search:manage")),
) -> dict[str, Any]:
    return _get_controller().activate_content_provider(provider_id)


@router.post("/content-providers/{provider_id}/deactivate")
async def deactivate_content_provider(
    provider_id: int,
    _user: AuthenticatedUser = Depends(require_permission("web_search:manage")),
) -> dict[str, Any]:
    return _get_controller().deactivate_content_provider(provider_id)
