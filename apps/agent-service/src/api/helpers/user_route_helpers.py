"""Pure helpers for user routes.

Extracted from ``user_route`` to keep the route file focused on endpoint
definitions.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from localization import t

from api.dependencies import extract_auth_token_from_request
from service.auth.auth_service import AuthenticatedUser, get_auth_service


async def resolve_project_identity(
    request: Request,
    user: AuthenticatedUser,
    service: Any,
) -> tuple[str, list[str]]:
    """Resolve effective user ID and owner IDs for user project operations."""
    identity = await get_auth_service().resolve_user_identity(
        token=extract_auth_token_from_request(request),
        user_id=user.user_id,
        user=user,
    )
    primary_user_id = str(identity.get("primary_user_id") or user.user_id)
    effective_user_id = await service.resolve_projects_user_id(primary_user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail=t("auth.not_authenticated"))

    owner_ids: list[str] = []
    for candidate in [effective_user_id, *(identity.get("known_user_ids") or []), user.user_id]:
        if not candidate:
            continue
        candidate_id = str(candidate)
        if candidate_id not in owner_ids:
            owner_ids.append(candidate_id)

    return effective_user_id, owner_ids
