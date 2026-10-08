import hashlib
import secrets
import uuid

from cryptography.fernet import Fernet, InvalidToken
from error_contract import ApiKeyNotFoundError

from src.core.security.encryption import SecretScope, get_cipher
from src.repository import ApiKeyRepository


def _get_fernet() -> Fernet:
    """The cipher for stored API key hashes.

    Scoped to USER_API_KEY_ENCRYPTION_KEY, so a leak of the system-settings key
    does not expose API keys. Key validation lives in core.security.encryption.
    """
    return get_cipher(SecretScope.USER_API_KEY)


class ApiKeyService:
    def __init__(self):
        self.repo = ApiKeyRepository()

    @staticmethod
    def _hash_key(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def _generate_key() -> tuple[str, str]:
        raw = secrets.token_urlsafe(32)
        prefix = raw[:8]
        return raw, prefix

    async def create(self, user_id: uuid.UUID, name: str) -> tuple[dict[str, str], dict[str, str]]:
        raw_key, prefix = self._generate_key()
        key_hash = self._hash_key(raw_key)

        encrypted_hash = _get_fernet().encrypt(key_hash.encode()).decode()

        key_record = await self.repo.create(
            user_id=user_id,
            key_hash=encrypted_hash,
            key_prefix=prefix,
            name=name,
        )

        record_dict = {
            "id": str(key_record.id),
            "name": key_record.name,
            "key_prefix": prefix,
            "is_active": key_record.is_active,
            "created_at": key_record.created_at.isoformat(),
        }

        return {"full_key": raw_key}, record_dict

    async def validate(self, raw_key: str) -> uuid.UUID | None:
        prefix = raw_key[:8]
        candidates = await self.repo.find_by_prefix_and_active(prefix)
        if not candidates:
            return None

        key_hash = self._hash_key(raw_key)

        for key_record in candidates:
            try:
                stored_hash = _get_fernet().decrypt(key_record.key_hash.encode()).decode()
            except (InvalidToken, UnicodeError):
                # A corrupt stored key must not prevent checking the remaining records.
                continue
            if stored_hash == key_hash:
                await self.repo.update_last_used(key_record.id)
                return key_record.user_id

        return None

    async def list_by_user(self, user_id: uuid.UUID) -> list[dict[str, str]]:
        keys = await self.repo.list_by_user(user_id)
        return [
            {
                "id": str(k.id),
                "name": k.name,
                "key_prefix": k.key_prefix,
                "is_active": k.is_active,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "created_at": k.created_at.isoformat(),
            }
            for k in keys
        ]

    async def revoke(self, key_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return await self.repo.revoke(key_id, user_id)

    async def delete(self, key_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        deleted = await self.repo.delete(key_id, user_id)
        if not deleted:
            raise ApiKeyNotFoundError()
        return True


_api_key_service: ApiKeyService | None = None


def get_api_key_service() -> ApiKeyService:
    global _api_key_service
    if _api_key_service is None:
        _api_key_service = ApiKeyService()
    return _api_key_service
