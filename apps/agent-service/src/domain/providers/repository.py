"""CRUD operations for providers and user_provider_configs tables."""
from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from core.db.models.provider import ProviderModel, UserProviderConfigModel
from core.db.repositories.base import BaseRepository
from core.security.encryption import decrypt_api_key, encrypt_api_key


class ProviderRepository(BaseRepository):

    # ── URL-based providers ──────────────────────────────────────────────────

    async def list_url_providers(self, user_id: str) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.execute(
                select(ProviderModel, UserProviderConfigModel)
                .join(
                    UserProviderConfigModel,
                    UserProviderConfigModel.provider_id == ProviderModel.id,
                )
                .where(
                    UserProviderConfigModel.user_id == user_id,
                    ProviderModel.provider_kind == "url",
                )
                .order_by(UserProviderConfigModel.time_created.asc())
            )
            return [
                self._serialize_with_config(provider, config)
                for provider, config in result.all()
            ]

    async def get_url_provider(self, provider_id: str, user_id: str) -> dict[str, Any] | None:
        async with self._session() as session:
            result = await session.execute(
                select(ProviderModel, UserProviderConfigModel)
                .join(
                    UserProviderConfigModel,
                    UserProviderConfigModel.provider_id == ProviderModel.id,
                )
                .where(
                    ProviderModel.id == uuid.UUID(provider_id),
                    UserProviderConfigModel.user_id == user_id,
                    ProviderModel.provider_kind == "url",
                )
            )
            row = result.first()
            if not row:
                return None
            return self._serialize_with_config(row[0], row[1])

    async def create_url_provider(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        async with self._session() as session:
            encrypted_key = encrypt_api_key(data["api_key"]) if data.get("api_key") else None

            provider = ProviderModel(
                id=uuid.uuid4(),
                name=data["name"],
                provider_type=data["provider_type"],
                provider_kind="url",
                base_url=data["base_url"],
                config=data.get("config") or {},
            )
            session.add(provider)
            await session.flush()

            config = UserProviderConfigModel(
                id=uuid.uuid4(),
                user_id=user_id,
                provider_id=provider.id,
                api_key_encrypted=encrypted_key,
                default_model=data.get("default_model"),
            )
            session.add(config)
            try:
                await session.flush()
            except IntegrityError:
                raise ValueError(
                    f"A {data['provider_type']} provider with this URL already exists."
                )
            await session.refresh(provider)
            await session.refresh(config)
            return self._serialize_with_config(provider, config)

    async def update_url_provider(
        self, provider_id: str, user_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with self._session() as session:
            result = await session.execute(
                select(ProviderModel, UserProviderConfigModel)
                .join(
                    UserProviderConfigModel,
                    UserProviderConfigModel.provider_id == ProviderModel.id,
                )
                .where(
                    ProviderModel.id == uuid.UUID(provider_id),
                    UserProviderConfigModel.user_id == user_id,
                    ProviderModel.provider_kind == "url",
                )
            )
            row = result.first()
            if not row:
                return None
            provider, config = row
            if provider.is_builtin:
                return None

            provider.name = data.get("name", provider.name)
            provider.base_url = data.get("base_url", provider.base_url)
            if data.get("api_key"):
                config.api_key_encrypted = encrypt_api_key(data["api_key"])
            if "config" in data:
                provider.config = data["config"]
            if "default_model" in data:
                config.default_model = data["default_model"]
            await session.flush()
            await session.refresh(provider)
            await session.refresh(config)
            return self._serialize_with_config(provider, config)

    async def delete_url_provider(self, provider_id: str, user_id: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(ProviderModel, UserProviderConfigModel)
                .join(
                    UserProviderConfigModel,
                    UserProviderConfigModel.provider_id == ProviderModel.id,
                )
                .where(
                    ProviderModel.id == uuid.UUID(provider_id),
                    UserProviderConfigModel.user_id == user_id,
                    ProviderModel.provider_kind == "url",
                )
            )
            row = result.first()
            if not row:
                return False
            provider, config = row
            if provider.is_builtin:
                return False

            await session.delete(config)
            await session.flush()

            remaining_count = await session.scalar(
                select(func.count()).where(
                    UserProviderConfigModel.provider_id == provider.id
                )
            )
            if not remaining_count:
                await session.delete(provider)
            return True

    # ── API-key providers ────────────────────────────────────────────────────

    async def list_user_providers(self, user_id: str) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.execute(
                select(ProviderModel, UserProviderConfigModel)
                .join(
                    UserProviderConfigModel,
                    UserProviderConfigModel.provider_id == ProviderModel.id,
                )
                .where(
                    UserProviderConfigModel.user_id == user_id,
                    ProviderModel.provider_kind == "api_key",
                )
                .order_by(UserProviderConfigModel.time_created.asc())
            )
            return [
                self._serialize_with_config(provider, config)
                for provider, config in result.all()
            ]

    async def create_user_provider(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        api_key: str = data["api_key"]
        fingerprint = hashlib.sha256(api_key.encode()).hexdigest()[:16]

        async with self._session() as session:
            provider = ProviderModel(
                id=uuid.uuid4(),
                name=data["name"],
                provider_type=data["provider_type"],
                provider_kind="api_key",
                config=data.get("custom_config") or {},
            )
            session.add(provider)
            await session.flush()

            config = UserProviderConfigModel(
                id=uuid.uuid4(),
                user_id=user_id,
                provider_id=provider.id,
                api_key_encrypted=encrypt_api_key(api_key),
                api_key_fingerprint=fingerprint,
                api_base=data.get("api_base"),
                api_version=data.get("api_version"),
                custom_config=data.get("custom_config") or {},
                default_model=data.get("default_model"),
            )
            session.add(config)
            try:
                await session.flush()
            except IntegrityError:
                raise ValueError(
                    f"A {data['provider_type']} provider already exists."
                )
            await session.refresh(provider)
            await session.refresh(config)
            return self._serialize_with_config(provider, config)

    async def delete_user_provider(self, provider_id: str, user_id: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(ProviderModel, UserProviderConfigModel)
                .join(
                    UserProviderConfigModel,
                    UserProviderConfigModel.provider_id == ProviderModel.id,
                )
                .where(
                    ProviderModel.id == uuid.UUID(provider_id),
                    UserProviderConfigModel.user_id == user_id,
                    ProviderModel.provider_kind == "api_key",
                )
            )
            row = result.first()
            if not row:
                return False
            provider, config = row
            await session.delete(config)
            await session.flush()

            remaining_count = await session.scalar(
                select(func.count()).where(
                    UserProviderConfigModel.provider_id == provider.id
                )
            )
            if not remaining_count:
                await session.delete(provider)
            return True

    async def get_decrypted_api_key(self, provider_id: str, user_id: str) -> str | None:
        """Internal use only — retrieves decrypted key for LLM instantiation."""
        async with self._session() as session:
            result = await session.execute(
                select(UserProviderConfigModel).where(
                    UserProviderConfigModel.provider_id == uuid.UUID(provider_id),
                    UserProviderConfigModel.user_id == user_id,
                )
            )
            config = result.scalars().first()
            if not config:
                return None
            return decrypt_api_key(config.api_key_encrypted) if config.api_key_encrypted else None

    # ── Ordering & per-provider default model ────────────────────────────────

    async def reorder_providers(self, user_id: str, ordered_config_ids: list[str]) -> bool:
        # priority column was removed; keep endpoint compatibility as a no-op.
        return True

    async def update_provider_default_model(
        self, config_id: str, user_id: str, model: str | None
    ) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(UserProviderConfigModel).where(
                    UserProviderConfigModel.id == uuid.UUID(config_id),
                    UserProviderConfigModel.user_id == user_id,
                )
            )
            config = result.scalars().first()
            if not config:
                return False
            config.default_model = model
            return True

    # ── Serializer ───────────────────────────────────────────────────────────

    @staticmethod
    def _serialize_with_config(
        provider: ProviderModel,
        config: UserProviderConfigModel,
    ) -> dict[str, Any]:
        base: dict[str, Any] = {
            "id": str(provider.id),
            "name": provider.name,
            "provider_type": provider.provider_type,
            "provider_kind": provider.provider_kind,
            "is_active": provider.is_active,
            "is_builtin": provider.is_builtin,
            "config": provider.config or {},
            "user_config": {
                "id": str(config.id),
                "default_model": config.default_model,
                "is_active": config.is_active,
            },
            "time_created": provider.time_created.isoformat() if provider.time_created else None,
            "time_updated": provider.time_updated.isoformat() if provider.time_updated else None,
        }
        if provider.provider_kind == "url":
            base["base_url"] = provider.base_url
            base["has_api_key"] = config.api_key_encrypted is not None
        else:
            base["user_config"]["api_key_masked"] = "****"
            base["user_config"]["api_base"] = config.api_base
            base["user_config"]["api_version"] = config.api_version
            base["user_config"]["custom_config"] = config.custom_config or {}
        return base
