"""Ownership guard for the endpoints addressed by a raw ``thread_id``.

Several routers hand back (or mutate) conversation state keyed only by a
thread id — the threads CRUD, the two history endpoints, run cancellation.
The ``thread:*`` / ``run:*`` permissions they are gated on say the caller may
work with threads, not *whose* threads, and every enduser holds them. This
module is the single place that answers "is this the caller's thread".
"""

from __future__ import annotations

from error_contract import NotFoundError
from fastapi import Request

from api.dependencies import extract_auth_token_from_request
from core.observability.logger import get_logger
from service.auth.auth_service import AuthenticatedUser
from service.users import normalize_owner_ids, thread_belongs_to_owner_ids

logger = get_logger(__name__)


async def resolve_owner_ids(request: Request | None, user: AuthenticatedUser) -> list[str]:
    """Every id that counts as "this caller" when matching thread ownership.

    A user can accumulate more than one id over their lifetime (identity
    migrations record the previous ones as ``legacy_user_ids``), so matching
    on the current id alone would lock people out of their own older threads.
    """
    from service.auth.auth_service import get_auth_service

    identity = await get_auth_service().resolve_user_identity(
        token=extract_auth_token_from_request(request) if request is not None else None,
        user_id=user.user_id,
        user=user,
    )
    return normalize_owner_ids(
        str(identity.get("primary_user_id") or user.user_id),
        identity.get("known_user_ids") or [],
    )


async def require_owned_thread(thread_id: str, request: Request | None, user: AuthenticatedUser) -> dict:
    """Return the thread only when it belongs to the caller, else 404.

    404 rather than 403 on purpose: a 403 confirms the thread id exists, which
    is itself the enumeration this guard closes.
    """
    from service.threads import get_thread_access_service

    thread = await get_thread_access_service().get_thread(thread_id)
    if not thread:
        raise NotFoundError(message_key="thread.not_found")

    owner_ids = await resolve_owner_ids(request, user)
    if not thread_belongs_to_owner_ids(thread, owner_ids):
        logger.warning(
            "User %s attempted to reach thread %s owned by someone else",
            user.user_id,
            thread_id,
        )
        raise NotFoundError(message_key="thread.not_found")
    return thread
