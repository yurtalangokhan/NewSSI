"""MCP provider-auth repository — typed CRUD for the ``mcp_provider_auth`` table.

Stores admin/shared (``user_id IS NULL``) and per-user credentials plus OAuth
tokens. Secret columns hold ciphertext; encryption/decryption is done in the
service layer.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.models.mcp_provider_auth import MCPProviderAuthModel
from core.db.repositories.base import BaseRepository
from core.logger import get_logger

logger = get_logger(__name__)

_MUTABLE_FIELDS = {
    "credentials_encrypted",
    "oauth_access_token_encrypted",
    "oauth_refresh_token_encrypted",
    "oauth_expires_at",
    "oauth_scopes",
}


class MCPProviderAuthRepository(BaseRepository):
    """CRUD operations on the ``mcp_provider_auth`` table."""

    @staticmethod
    def _to_dict(row: MCPProviderAuthModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "provider_id": str(row.provider_id),
            "user_id": row.user_id,
            "credentials_encrypted": row.credentials_encrypted,
            "oauth_access_token_encrypted": row.oauth_access_token_encrypted,
            "oauth_refresh_token_encrypted": row.oauth_refresh_token_encrypted,
            "oauth_expires_at": (
                row.oauth_expires_at.isoformat() if row.oauth_expires_at else None
            ),
            "oauth_scopes": row.oauth_scopes or [],
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }

    @staticmethod
    def _user_predicate(user_id: str | None):
        if user_id is None:
            return MCPProviderAuthModel.user_id.is_(None)
        return MCPProviderAuthModel.user_id == user_id

    async def get(self, provider_id: str, user_id: str | None) -> dict[str, Any] | None:
        async with self._session() as session:
            stmt = select(MCPProviderAuthModel).where(
                MCPProviderAuthModel.provider_id == provider_id,
                self._user_predicate(user_id),
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        return self._to_dict(row) if row is not None else None

    async def list_for_provider(self, provider_id: str) -> list[dict[str, Any]]:
        async with self._session() as session:
            stmt = select(MCPProviderAuthModel).where(
                MCPProviderAuthModel.provider_id == provider_id
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def upsert(self, provider_id: str, user_id: str | None, **fields: Any) -> dict[str, Any]:
        """Insert or update the credential row for ``(provider_id, user_id)``."""
        updates = {k: v for k, v in fields.items() if k in _MUTABLE_FIELDS}
        now = datetime.now(UTC)
        async with self._session() as session:
            existing = await session.execute(
                select(MCPProviderAuthModel).where(
                    MCPProviderAuthModel.provider_id == provider_id,
                    self._user_predicate(user_id),
                )
            )
            current = existing.scalar_one_or_none()
            if current is None:
                stmt = (
                    pg_insert(MCPProviderAuthModel)
                    .values(
                        id=_uuid.uuid4(),
                        provider_id=provider_id,
                        user_id=user_id,
                        time_created=now,
                        time_updated=now,
                        **updates,
                    )
                    .returning(MCPProviderAuthModel)
                )
            else:
                stmt = (
                    update(MCPProviderAuthModel)
                    .where(MCPProviderAuthModel.id == current.id)
                    .values(time_updated=now, **updates)
                    .returning(MCPProviderAuthModel)
                )
            result = await session.execute(stmt)
            row = result.scalar_one()
        return self._to_dict(row)

    async def delete(self, provider_id: str, user_id: str | None) -> bool:
        async with self._session() as session:
            stmt = delete(MCPProviderAuthModel).where(
                MCPProviderAuthModel.provider_id == provider_id,
                self._user_predicate(user_id),
            )
            result = await session.execute(stmt)
            return result.rowcount > 0
