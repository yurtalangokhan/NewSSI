# Copyright (c) 2026 Agentic AI Platform
"""HTTP adapter for delegated memory-index writes and search."""

from typing import Annotated

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Depends, Request, Response

from src.memory import controller
from src.memory.schemas import (
    MemoryFactHitBody,
    SearchFactsRequest,
    SearchFactsResponse,
    UpsertFactRequest,
)
from src.shared.auth import AuthenticatedUser, require_permission
from src.shared.response_errors import request_locale, set_error_response
from src.shared.response_models import ErrorModel, ResponseModel

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/facts", response_model=ResponseModel[None])
async def upsert_fact(
    *,
    request: Request,
    response: Response,
    body: UpsertFactRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("memory:write"))],
):
    """Index one fact and acknowledge it with a JSON response."""
    try:
        await controller.upsert_fact(user.identity, request.headers.get("x-user-id"), body.fact_id, body.content)
        return ResponseModel()
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete("/facts/{fact_id}", response_model=ResponseModel[None])
async def delete_fact(
    *,
    request: Request,
    response: Response,
    fact_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("memory:write"))],
):
    """Remove one fact's embedding for the delegated user."""
    try:
        await controller.delete_fact(user.identity, request.headers.get("x-user-id"), fact_id)
        return ResponseModel()
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete("/facts", response_model=ResponseModel[None])
async def delete_all_facts(
    *,
    request: Request,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_permission("memory:write"))],
):
    """Remove all embeddings for the delegated user."""
    try:
        await controller.delete_all_facts(user.identity, request.headers.get("x-user-id"))
        return ResponseModel()
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/search", response_model=ResponseModel[SearchFactsResponse])
async def search_facts(
    *,
    request: Request,
    response: Response,
    body: SearchFactsRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("memory:search"))],
):
    """Return relevant facts for the delegated user."""
    try:
        hits = await controller.search_facts(user.identity, request.headers.get("x-user-id"), body.query, body.limit)
        data = SearchFactsResponse(
            hits=[
                MemoryFactHitBody(
                    fact_id=hit.fact_id,
                    content=hit.content,
                    score=hit.score,
                    vector_score=hit.vector_score,
                    bm25_score=hit.bm25_score,
                )
                for hit in hits
            ]
        )
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
