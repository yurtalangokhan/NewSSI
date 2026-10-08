import json
from typing import Any
import uuid

from cryptography.fernet import InvalidToken, MultiFernet

from src.core.database.models import UserConnectorConfigModel
from src.core.observability import get_logger
from src.core.security.encryption import SecretScope, get_cipher
from src.repository import UserConnectorConfigRepository

logger = get_logger(__name__)


def _cipher() -> MultiFernet:
    """The cipher for stored connector configurations.

    Scoped to CONNECTOR_CONFIG_ENCRYPTION_KEY, so a leak of the API-key or
    system-settings key does not expose source credentials.
    """
    return get_cipher(SecretScope.CONNECTOR_CONFIG)


class UserConnectorConfigService:
    """Per-user connector configurations, sealed at rest.

    Only :meth:`get` returns the decrypted document. Everything a mutating
    route answers with is metadata: those responses are replay-cached by the
    idempotency middleware and must never carry a credential.
    """

    def __init__(self):
        self.repo = UserConnectorConfigRepository()

    @staticmethod
    def _encrypt(config: dict[str, Any]) -> str:
        return _cipher().encrypt(json.dumps(config).encode()).decode()

    @staticmethod
    def _decrypt(token: str) -> dict[str, Any]:
        return json.loads(_cipher().decrypt(token.encode()))

    @staticmethod
    def _meta(row: UserConnectorConfigModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "user_id": str(row.user_id),
            "connector_name": row.connector_name,
            "name": row.name,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def list_for_user(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        return [self._meta(row) for row in await self.repo.list_by_user(user_id)]

    async def create(
        self,
        user_id: uuid.UUID,
        connector_name: str,
        name: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        row = await self.repo.create(
            user_id=user_id,
            connector_name=connector_name,
            name=name,
            config_encrypted=self._encrypt(config),
        )
        return self._meta(row)

    async def get(self, config_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any] | None:
        """Metadata plus the decrypted ``config``, or ``None`` when not owned by ``user_id``."""
        row = await self.repo.get(config_id, user_id)
        if row is None:
            return None
        try:
            config = self._decrypt(row.config_encrypted)
        except (InvalidToken, ValueError):
            # Wrong or rotated key: report it as unreadable rather than as a 500
            # that names nothing. The ciphertext is never logged.
            logger.error("Connector config %s cannot be decrypted with the configured key", row.id)
            raise
        return {**self._meta(row), "config": config}

    async def update(
        self,
        config_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        name: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        row = await self.repo.update(
            config_id,
            user_id,
            name=name,
            config_encrypted=self._encrypt(config) if config is not None else None,
        )
        return self._meta(row) if row else None

    async def delete(self, config_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return await self.repo.delete(config_id, user_id)


_user_connector_config_service: UserConnectorConfigService | None = None


def get_user_connector_config_service() -> UserConnectorConfigService:
    global _user_connector_config_service
    if _user_connector_config_service is None:
        _user_connector_config_service = UserConnectorConfigService()
    return _user_connector_config_service
