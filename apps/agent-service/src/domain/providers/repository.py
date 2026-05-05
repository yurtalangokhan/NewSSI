"""CRUD operations for providers and user_providers tables."""
from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.db.models.provider import ProviderModel, UserProviderModel
from core.db.repositories.base import BaseRepository
from core.security.encryption import decrypt_api_key, encrypt_api_key


class ProviderRepository(BaseRepository):

    # ── URL-based providers ──────────────────────────────────────────────────

    async def list_url_providers(self, user_id: str) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.execute(
                select(ProviderModel).where(ProviderModel.user_id == user_id)
            )
            return [self._serialize_provider(r) for r in result.scalars().all()]

    async def get_url_provider(self, provider_id: str, user_id: str) -> dict[str, Any] | None:
        async with self._session() as session:
            row = await session.get(ProviderModel, uuid.UUID(provider_id))
            if not row or row.user_id != user_id:
                return None
            return self._serialize_provider(row)

    async def create_url_provider(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        async with self._session() as session:
            encrypted_key = encrypt_api_key(data["api_key"]) if data.get("api_key") else None
            row = ProviderModel(
                id=uuid.uuid4(),
                user_id=user_id,
                name=data["name"],
                provider_type=data["provider_type"],
                base_url=data["base_url"],
                api_key_encrypted=encrypted_key,
                config=data.get("config") or {},
            )
            session.add(row)
            try:
                await session.flush()
            except IntegrityError:
                raise ValueError(
                    f"A {data['provider_type']} provider with this URL already exists."
                )
            await session.refresh(row)
            return self._serialize_provider(row)

    async def update_url_provider(self, provider_id: str, user_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        async with self._session() as session:
            row = await session.get(ProviderModel, uuid.UUID(provider_id))
            if not row or row.user_id != user_id or row.is_builtin:
                return None
            row.name = data.get("name", row.name)
            row.base_url = data.get("base_url", row.base_url)
            if data.get("api_key"):
                row.api_key_encrypted = encrypt_api_key(data["api_key"])
            if "config" in data:
                row.config = data["config"]
            await session.flush()
            await session.refresh(row)
            return self._serialize_provider(row)

    async def delete_url_provider(self, provider_id: str, user_id: str) -> bool:
        async with self._session() as session:
            row = await session.get(ProviderModel, uuid.UUID(provider_id))
            if not row or row.user_id != user_id or row.is_builtin:
                return False
            await session.delete(row)
            return True

    # ── API-key providers ────────────────────────────────────────────────────

    async def list_user_providers(self, user_id: str) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.execute(
                select(UserProviderModel).where(UserProviderModel.user_id == user_id)
            )
            return [self._serialize_user_provider(r) for r in result.scalars().all()]

    async def create_user_provider(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        api_key: str = data["api_key"]
        fingerprint = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        async with self._session() as session:
            row = UserProviderModel(
                id=uuid.uuid4(),
                user_id=user_id,
                name=data["name"],
                provider_type=data["provider_type"],
                api_key_encrypted=encrypt_api_key(api_key),
                api_key_fingerprint=fingerprint,
                api_base=data.get("api_base"),
                api_version=data.get("api_version"),
                deployment_name=data.get("deployment_name"),
                custom_config=data.get("custom_config") or {},
            )
            session.add(row)
            try:
                await session.flush()
            except IntegrityError:
                raise ValueError(
                    f"A {data['provider_type']} provider with this API key already exists."
                )
            await session.refresh(row)
            return self._serialize_user_provider(row)

    async def delete_user_provider(self, provider_id: str, user_id: str) -> bool:
        async with self._session() as session:
            row = await session.get(UserProviderModel, uuid.UUID(provider_id))
            if not row or row.user_id != user_id:
                return False
            await session.delete(row)
            return True

    async def get_decrypted_api_key(self, provider_id: str, user_id: str) -> str | None:
        """Internal use only — retrieves decrypted key for LLM instantiation."""
        async with self._session() as session:
            row = await session.get(UserProviderModel, uuid.UUID(provider_id))
            if not row or row.user_id != user_id:
                return None
            return decrypt_api_key(row.api_key_encrypted) if row.api_key_encrypted else None

    # ── Serializers ──────────────────────────────────────────────────────────

    @staticmethod
    def _serialize_provider(row: ProviderModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "user_id": row.user_id,
            "name": row.name,
            "provider_type": row.provider_type,
            "base_url": row.base_url,
            "has_api_key": row.api_key_encrypted is not None,
            "is_active": row.is_active,
            "is_builtin": row.is_builtin,
            "config": row.config or {},
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }

    @staticmethod
    def _serialize_user_provider(row: UserProviderModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "user_id": row.user_id,
            "name": row.name,
            "provider_type": row.provider_type,
            "api_key_masked": "****",
            "api_base": row.api_base,
            "api_version": row.api_version,
            "deployment_name": row.deployment_name,
            "custom_config": row.custom_config or {},
            "is_active": row.is_active,
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }
