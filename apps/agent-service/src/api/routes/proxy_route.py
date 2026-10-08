# ruff: noqa: FAST001 -- Explicit response models publish the shared response contract.
"""
Proxy routes for external services.

Endpoints:
  GET /mcp/tools    — list MCP tools from the MCP server
  GET /mcp/tools-builtin — list tools from built-in tools-service
  POST /mcp/execute — execute a tool on the MCP server
  GET /ollama/models — list available Ollama models
  GET /rag/collections — list RAG collections from rag-service
"""

from typing import Annotated

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Body, Depends, Request, Response

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.proxy import (
    ProxyExecuteToolResponse,
    ProxyOllamaModelsResponse,
    ProxyRagCollectionsResponse,
    ProxyToolsResponse,
)
from service.proxy import proxy_application_service as application_service

router = APIRouter(prefix="/api/proxy", tags=["proxy"], dependencies=[Depends(require_user)])


@router.get("/mcp/tools", response_model=ResponseModel[ProxyToolsResponse])
async def get_mcp_tools(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:read"))],
) -> ResponseModel[ProxyToolsResponse]:
    try:
        return ResponseModel[ProxyToolsResponse](data=await application_service.get_mcp_tools())
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/ollama/models", response_model=ResponseModel[ProxyOllamaModelsResponse])
async def get_ollama_models(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
) -> ResponseModel[ProxyOllamaModelsResponse]:
    try:
        return ResponseModel[ProxyOllamaModelsResponse](data=await application_service.get_ollama_models())
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/rag/collections", response_model=ResponseModel[ProxyRagCollectionsResponse])
async def get_rag_collections(
    request: Request,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_permission("collection:list"))],
) -> ResponseModel[ProxyRagCollectionsResponse]:
    try:
        return ResponseModel[ProxyRagCollectionsResponse](
            data=await application_service.get_rag_collections(access_token=user.access_token)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/mcp/tools-builtin", response_model=ResponseModel[ProxyToolsResponse])
async def get_builtin_mcp_tools(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:read"))],
) -> ResponseModel[ProxyToolsResponse]:
    try:
        return ResponseModel[ProxyToolsResponse](data=await application_service.get_builtin_mcp_tools())
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/mcp/execute", response_model=ResponseModel[ProxyExecuteToolResponse])
async def execute_mcp_tool(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("tool:execute"))],
    tool_name: Annotated[str, Body(description="Name of the tool to execute")],
    arguments: Annotated[dict | None, Body(description="Arguments to pass to the tool")] = None,
) -> ResponseModel[ProxyExecuteToolResponse]:
    try:
        return ResponseModel[ProxyExecuteToolResponse](
            data=await application_service.execute_mcp_tool(tool_name=tool_name, arguments=arguments)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
