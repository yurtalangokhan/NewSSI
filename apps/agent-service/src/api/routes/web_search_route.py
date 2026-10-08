"""Web search admin configuration routes."""

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response

from api.dependencies import (
    AuthenticatedUser,
    require_permission,
    require_user,
)
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.common import StatusResponse
from schemas.web_search import (
    ContentProviderResponse,
    CrawlUrlResponse,
    SearchProviderResponse,
    WebSearchIdStatusResponse,
)
from service.web_search.web_search_service import WebSearchService, get_web_search_service

router = APIRouter(
    prefix="/api/admin/web-search",
    tags=["web-search"],
    dependencies=[Depends(require_user)],
)


def _get_service() -> WebSearchService:
    return get_web_search_service()


@router.get("/search-providers", response_model=ResponseModel[list[SearchProviderResponse]])
async def list_search_providers(
    response: Response,
    request: Request,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("web_search:manage"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=_get_service().list_search_providers())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/content-providers", response_model=ResponseModel[list[ContentProviderResponse]])
async def list_content_providers(
    response: Response,
    request: Request,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("web_search:manage"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=_get_service().list_content_providers())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/content-providers/test", response_model=ResponseModel[StatusResponse])
async def test_content_provider(
    response: Response,
    request: Request,
    payload: dict[str, Any],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("web_search:test"))],
) -> ResponseModel[Any]:
    provider_type = payload.get("provider_type", "atlas_web_crawler")
    try:
        return ResponseModel(data=await _get_service().async_test_content_provider(provider_type))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/content-providers/crawl", response_model=ResponseModel[CrawlUrlResponse])
async def crawl_url(
    response: Response,
    request: Request,
    payload: dict[str, Any],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("web_search:manage"))],
) -> ResponseModel[Any]:
    """Crawl a single URL with the built-in web crawler and return the result."""
    url: str = payload.get("url") or ""
    try:
        return ResponseModel(data=await _get_service().async_crawl_url(url))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/content-providers/reset-default", response_model=ResponseModel[StatusResponse])
async def reset_default_content_provider(
    response: Response,
    request: Request,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("web_search:manage"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=_get_service().reset_default_content_provider())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/content-providers/{provider_id}/activate", response_model=ResponseModel[WebSearchIdStatusResponse])
async def activate_content_provider(
    response: Response,
    request: Request,
    provider_id: int,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("web_search:manage"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=_get_service().activate_content_provider(provider_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/content-providers/{provider_id}/deactivate", response_model=ResponseModel[WebSearchIdStatusResponse])
async def deactivate_content_provider(
    response: Response,
    request: Request,
    provider_id: int,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("web_search:manage"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=_get_service().deactivate_content_provider(provider_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
