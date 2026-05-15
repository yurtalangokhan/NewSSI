import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.config import get_settings
from src.repository import SessionRepository, UserRepository

from .keycloak_service import get_keycloak_service

_settings = get_settings()
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def __init__(self):
        self.session_repo = SessionRepository()
        self.user_repo = UserRepository()
        self.keycloak = get_keycloak_service()

    @staticmethod
    def hash_password(password: str) -> str:
        return _pwd_context.hash(password)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        return _pwd_context.verify(plain, hashed)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _create_access_token(self, user_id: str, email: str, role: str) -> tuple[str, datetime]:
        expires = datetime.utcnow() + timedelta(hours=1)
        payload = {
            "sub": user_id,
            "email": email,
            "role": role,
            "exp": expires,
            "iat": datetime.utcnow(),
            "iss": "user-service",
            "type": "access",
        }
        secret = _settings.AUTH_SECRET or "dev-secret-change-me"
        token = jwt.encode(payload, secret, algorithm="HS256")
        return token, expires

    def _create_refresh_token(self) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(days=30)
        return token, expires

    async def basic_login(self, email: str, password: str) -> dict[str, Any]:
        if self.keycloak.is_enabled():
            raise ValueError("Keycloak auth is enabled. Use OIDC login flow.")
        user = await self.user_repo.get_by_email(email)
        if not user or not user.hashed_password:
            raise ValueError("Invalid credentials")
        if not self.verify_password(password, user.hashed_password):
            raise ValueError("Invalid credentials")
        if not user.is_active:
            raise ValueError("User account is disabled")

        return await self._build_login_response(user)

    async def _build_login_response(self, user) -> dict[str, Any]:
        access_token, expires = self._create_access_token(str(user.id), user.email, user.role.value)
        refresh_token, refresh_expires = self._create_refresh_token()

        await self.session_repo.create(
            user_id=user.id,
            token_hash=self._hash_token(access_token),
            refresh_token_hash=self._hash_token(refresh_token),
            expires_at=expires,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role.value,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "is_superuser": user.is_superuser,
            },
        }

    async def logout(self, refresh_token: str | None = None) -> dict[str, Any]:
        if refresh_token:
            await self.session_repo.delete_by_refresh_token_hash(self._hash_token(refresh_token))

        if self.keycloak.is_enabled():
            await self.keycloak.backchannel_logout(refresh_token=refresh_token)

        return {"message": "Logged out successfully"}

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        session = await self.session_repo.get_by_refresh_token_hash(self._hash_token(refresh_token))
        if not session:
            raise ValueError("Invalid refresh token")

        if session.expires_at < datetime.utcnow():
            await self.session_repo.delete_by_refresh_token_hash(self._hash_token(refresh_token))
            raise ValueError("Refresh token expired")

        user = await self.user_repo.get_by_id(session.user_id)
        if not user or not user.is_active:
            raise ValueError("User not found or inactive")

        await self.session_repo.delete_by_refresh_token_hash(self._hash_token(refresh_token))

        access_token, expires = self._create_access_token(str(user.id), user.email, user.role.value)
        new_refresh, _ = self._create_refresh_token()

        await self.session_repo.create(
            user_id=user.id,
            token_hash=self._hash_token(access_token),
            refresh_token_hash=self._hash_token(new_refresh),
            expires_at=expires,
        )

        return {
            "access_token": access_token,
            "refresh_token": new_refresh,
            "token_type": "Bearer",
            "expires_in": 3600,
        }

    async def validate_token(self, token: str) -> dict[str, Any] | None:
        try:
            secret = _settings.AUTH_SECRET or "dev-secret-change-me"
            payload = jwt.decode(token, secret, algorithms=["HS256"], audience="user-service")
            if payload.get("type") != "access":
                return None
            return payload
        except JWTError:
            return None

    def get_auth_type(self) -> dict[str, Any]:
        if self.keycloak.is_enabled():
            return {"authType": "oidc", "keycloakEnabled": True}
        return {"authType": "basic", "keycloakEnabled": False}

    async def get_oidc_authorize_url(self, redirect_uri: str = "http://localhost:3000/auth/oidc/callback") -> str:
        state = secrets.token_urlsafe(16)
        return await self.keycloak.get_oidc_authorize_url(redirect_uri, state=state)

    async def handle_oidc_callback(self, code: str, redirect_uri: str = "http://localhost:3000/auth/oidc/callback") -> dict[str, Any]:
        token_data = await self.keycloak.handle_oidc_callback(code, redirect_uri)

        from jose import jwt

        id_token = token_data.get("id_token", "")

        if id_token:
            claims = jwt.decode(id_token, options={"verify_signature": False})
            keycloak_id = claims.get("sub", "")
            email = claims.get("email", "")
            username = claims.get("preferred_username", "")
            first_name = claims.get("given_name", "")
            last_name = claims.get("family_name", "")

            realm_roles = claims.get("realm_access", {}).get("roles", [])
            role = self._resolve_role(realm_roles)

            user = await self.user_repo.upsert_by_keycloak_id(
                keycloak_id,
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                role=role,
                is_active=True,
                is_verified=True,
            )

            if _settings.KEYCLOAK_ADMIN_EMAIL and email == _settings.KEYCLOAK_ADMIN_EMAIL:
                user = await self.user_repo.update(user.id, is_superuser=True, role="admin")

            return await self._build_login_response(user)

        return token_data

    @staticmethod
    def _resolve_role(realm_roles: list[str]) -> str:
        role_map = {
            "admin": "admin",
            "super_admin": "admin",
            "superuser": "admin",
            "global_curator": "global_curator",
            "curator": "curator",
            "limited": "limited",
        }
        for role in realm_roles:
            if role in role_map:
                return role_map[role]
        return "basic"


_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
