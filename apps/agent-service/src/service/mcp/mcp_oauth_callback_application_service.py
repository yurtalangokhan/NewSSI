"""MCPOAuthCallback application use cases."""

from __future__ import annotations

from collections.abc import Callable

from error_contract import BadRequestError

from core.observability.logger import get_logger
from service.auth.auth_service import AuthenticatedUser
from service.mcp.mcp_credential_service import MCPAuthError
from service.mcp.mcp_oauth_service import MCPOAuthService

logger = get_logger(__name__)


class MCPOAuthCallbackApplicationService:
    """Framework-free application use cases for this JSON surface."""

    def __init__(self, oauth_service: Callable[[], MCPOAuthService]):
        self._oauth_service_factory = oauth_service

    @property
    def oauth_service(self) -> MCPOAuthService:
        return self._oauth_service_factory()

    async def mcp_oauth_callback(
        self, user: AuthenticatedUser, code: str | None = None, state: str | None = None
    ) -> dict[str, str]:
        if not code or not state:
            raise BadRequestError(message_key="mcp.oauth_callback_invalid")
        try:
            return await self.oauth_service.complete(state, code, caller_user_id=user.user_id)
        except MCPAuthError as exc:
            raise BadRequestError(message_key="mcp.oauth_failed") from exc
