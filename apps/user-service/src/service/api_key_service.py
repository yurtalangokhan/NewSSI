import hashlib
import secrets
import uuid

from cryptography.fernet import Fernet

from src.config import get_settings
from src.repository import ApiKeyRepository

_settings = get_settings()

_fernet = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = _settings.require_encryption_key()
        if isinstance(key, str):
            import base64

            key_bytes = base64.urlsafe_b64decode(key + "==")
            _fernet = Fernet(key_bytes)
        else:
            _fernet = Fernet(key)
    return _fernet


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
                if stored_hash == key_hash:
                    await self.repo.update_last_used(key_record.id)
                    return key_record.user_id
            except Exception:
                continue

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

    async def revoke(self, key_id: uuid.UUID) -> bool:
        return await self.repo.revoke(key_id)

    async def delete(self, key_id: uuid.UUID) -> bool:
        return await self.repo.delete(key_id)


_api_key_service: ApiKeyService | None = None


def get_api_key_service() -> ApiKeyService:
    global _api_key_service
    if _api_key_service is None:
        _api_key_service = ApiKeyService()
    return _api_key_service
