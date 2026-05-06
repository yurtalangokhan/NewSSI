"""Web search admin configuration routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from service.AuthService import verify_bearer

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/web-search",
    tags=["web-search"],
    dependencies=[Depends(verify_bearer)],
)

_DEFAULT_CONTENT_PROVIDER = {
    "id": 1,
    "name": "Onyx Web Crawler",
    "provider_type": "onyx_web_crawler",
    "is_active": True,
    "config": None,
    "has_api_key": False,
}


@router.get("/search-providers")
async def list_search_providers() -> list[dict[str, Any]]:
    return []


@router.get("/content-providers")
async def list_content_providers() -> list[dict[str, Any]]:
    return [_DEFAULT_CONTENT_PROVIDER]


@router.post("/content-providers/test")
async def test_content_provider(payload: dict[str, Any]) -> dict[str, Any]:
    provider_type = payload.get("provider_type", "onyx_web_crawler")

    if provider_type != "onyx_web_crawler":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content provider type: {provider_type}",
        )

    try:
        from service.web_search.onyx_web_crawler import OnyxWebCrawler

        crawler = OnyxWebCrawler()
        results = crawler.contents(["https://example.com"])
        if results and not results[0].scrape_successful:
            raise HTTPException(
                status_code=400,
                detail=results[0].failure_reason or "Failed to fetch test URL",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("OnyxWebCrawler test failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    return {"status": "ok"}


@router.post("/content-providers/crawl")
async def crawl_url(payload: dict[str, Any]) -> dict[str, Any]:
    """Crawl a single URL with the Onyx Web Crawler and return the result."""
    url: str | None = payload.get("url")
    if not url or not isinstance(url, str) or not url.strip():
        raise HTTPException(status_code=422, detail="A non-empty 'url' field is required.")

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="URL must start with http:// or https://")

    try:
        from service.web_search.onyx_web_crawler import OnyxWebCrawler

        crawler = OnyxWebCrawler()
        results = crawler.contents([url])
        result = results[0] if results else None
        if result is None:
            raise HTTPException(status_code=500, detail="No result returned from crawler.")

        return {
            "title": result.title,
            "content": result.full_content,
            "scrape_successful": result.scrape_successful,
            "failure_reason": result.failure_reason,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("OnyxWebCrawler crawl failed for %s: %s", url, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/content-providers/{provider_id}/activate")
async def activate_content_provider(provider_id: int) -> dict[str, Any]:
    return {"status": "ok", "id": provider_id}


@router.post("/content-providers/{provider_id}/deactivate")
async def deactivate_content_provider(provider_id: int) -> dict[str, Any]:
    return {"status": "ok", "id": provider_id}


@router.post("/content-providers/reset-default")
async def reset_default_content_provider() -> dict[str, Any]:
    return {"status": "ok"}
