"""An OAuth callback may only complete the session that started it.

`complete(state, code)` looked the session up by `state` alone and then stored
the resulting tokens against `session["user_id"]`. The endpoint authenticates
its caller but never compared the two, so anyone who obtained (or guessed) a
state value could finish someone else's authorization — binding their own
remote account to that user's MCP server, or completing a flow they never
started.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from service.mcp.mcp_credential_service import MCPAuthError
from service.mcp.mcp_oauth_service import MCPOAuthService

STARTER = "user-who-started"
OTHER = "someone-else"


def _service(session: dict) -> MCPOAuthService:
    svc = MCPOAuthService.__new__(MCPOAuthService)
    svc._session_repo = AsyncMock()
    svc._session_repo.get = AsyncMock(return_value=session)
    svc._provider_repo = AsyncMock()
    svc._provider_repo.get_by_id = AsyncMock(return_value={})
    return svc


@pytest.mark.asyncio
async def test_a_different_user_cannot_complete_the_session():
    svc = _service({"user_id": STARTER, "provider_id": "p1"})

    with pytest.raises(MCPAuthError):
        await svc.complete("state-1", "code-1", caller_user_id=OTHER)


@pytest.mark.asyncio
async def test_a_missing_session_is_still_rejected():
    svc = MCPOAuthService.__new__(MCPOAuthService)
    svc._session_repo = AsyncMock()
    svc._session_repo.get = AsyncMock(return_value=None)

    with pytest.raises(MCPAuthError):
        await svc.complete("state-1", "code-1", caller_user_id=STARTER)


@pytest.mark.asyncio
async def test_the_starter_gets_past_the_binding_check():
    """The check must not reject the legitimate caller: the provider lookup
    that follows it is only reached once the binding matches."""
    svc = _service({"user_id": STARTER, "provider_id": "p1"})

    with pytest.raises(Exception):
        await svc.complete("state-1", "code-1", caller_user_id=STARTER)

    svc._provider_repo.get_by_id.assert_awaited_once()
