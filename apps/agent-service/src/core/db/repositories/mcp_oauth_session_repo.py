"""MCP OAuth-session repository — short-lived PKCE/state rows.

Rows are written by ``MCPOAuthService.begin`` and consumed by ``.complete``;
``get`` never returns an expired row and ``sweep_expired`` prunes them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.models.mcp_oauth_session import MCPOAuthSessionModel
from core.db.repositories.base import BaseRepository
from core.logger import get_logger

logger = get_logger(__name__)


class MCPOAuthSessionRepository(BaseRepository):
    """CRUD operations on the ``mcp_oauth_session`` table."""

    @staticmethod
    def _to_dict(row: MCPOAuthSessionModel) -> dict[str, Any]:
        return {
            "state": row.state,
            "provider_id": str(row.provider_id),
            "user_id": row.user_id,
            "code_verifier": row.code_verifier,
            "redirect_uri": row.redirect_uri,
            "return_path": row.return_path,
            "client_id": row.client_id,
            "client_secret_encrypted": row.client_secret_encrypted,
            "token_url": row.token_url,
            "resource": row.resource,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }

    async def create(self, **fields: Any) -> dict[str, Any]:
        async with self._session() as session:
            stmt = pg_insert(MCPOAuthSessionModel).values(**fields).returning(MCPOAuthSessionModel)
            result = await session.execute(stmt)
            row = result.scalar_one()
        return self._to_dict(row)

    async def get(self, state: str) -> dict[str, Any] | None:
        async with self._session() as session:
            stmt = select(MCPOAuthSessionModel).where(
                MCPOAuthSessionModel.state == state,
                MCPOAuthSessionModel.expires_at > func.now(),
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        return self._to_dict(row) if row is not None else None

    async def delete(self, state: str) -> None:
        async with self._session() as session:
            await session.execute(
                delete(MCPOAuthSessionModel).where(MCPOAuthSessionModel.state == state)
            )

    async def sweep_expired(self) -> int:
        async with self._session() as session:
            result = await session.execute(
                delete(MCPOAuthSessionModel).where(MCPOAuthSessionModel.expires_at < func.now())
            )
            return result.rowcount
