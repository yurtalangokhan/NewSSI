"""Flow component template, options, and validation endpoints.

Endpoints:
  GET  /flow-components                 - list all templates, grouped by category
  GET  /flow-components/options/{source} - resolve a dynamic options_source
  GET  /flow-components/{type}          - get one template

Auth uses `flow:read` (P3 Task 18's catalog, user-service migration 0018).
P1 Task 6 used interim `agent:list`/`agent:read` guards before the catalog
existed; re-pointed here. The dependency closures are module-level names so
tests can target them directly with `app.dependency_overrides`.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import AuthenticatedUser, require_permission
from core.exceptions import UnknownComponentError, UnknownOptionsSourceError
from domain.flows.resolvers import ResolverContext
from domain.flows.service import FlowService

router = APIRouter(prefix="/flow-components", tags=["flow-components"])

_require_list = require_permission("flow:read")
_require_read = require_permission("flow:read")


def _get_service() -> FlowService:
    return FlowService()


@router.get("")
async def list_components(
    _user: AuthenticatedUser = Depends(_require_list),
) -> dict[str, list[dict[str, Any]]]:
    """List every registered component template, grouped by category."""
    grouped = _get_service().list_components()
    return {
        category: [template.model_dump(mode="json") for template in templates]
        for category, templates in grouped.items()
    }


@router.get("/options/{source}")
async def resolve_component_options(
    source: str,
    dep: list[str] = Query(default=[]),
    user: AuthenticatedUser = Depends(_require_read),
) -> dict[str, Any]:
    """Resolve a dynamic options_source for the calling user.

    ``dep`` carries the sibling values a source declares in
    ``InputField.depends_on``, one ``name:value`` pair per entry — the chosen
    provider narrows ``llm.models``, for instance. They ride in the query
    string so the response stays cacheable by URL. A malformed entry is
    ignored rather than rejected: a dropdown must not 400 because the canvas
    sent something odd.
    """
    depends: dict[str, str] = {}
    for entry in dep:
        name, separator, value = entry.partition(":")
        if separator and name.strip():
            depends[name.strip()] = value.strip()

    try:
        result = await _get_service().resolve_options(
            source,
            ResolverContext(user_id=user.user_id, access_token=user.access_token, depends=depends),
        )
    except UnknownOptionsSourceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return {
        "source": result.source,
        "available": result.available,
        "items": [asdict(item) for item in result.items],
    }


@router.get("/{component_type}")
async def get_component(
    component_type: str,
    _user: AuthenticatedUser = Depends(_require_read),
) -> dict[str, Any]:
    """Get a single component template by type."""
    try:
        template = _get_service().get_component(component_type)
    except UnknownComponentError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return template.model_dump(mode="json")
