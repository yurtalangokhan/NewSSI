import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from src.config import get_settings
from src.core.database.models.user_model import normalize_user_role
from src.repository import UserRepository

from .keycloak_service import get_keycloak_service

_settings = get_settings()


class AuthService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.keycloak = get_keycloak_service()

    def _create_access_token(self, user_id: str, email: str, role: str) -> tuple[str, datetime]:
        expires = datetime.now(UTC) + timedelta(hours=1)
        payload = {
            "sub": user_id,
            "aud": _settings.SERVICE_NAME,
            "email": email,
            "role": role,
            "exp": expires,
            "iat": datetime.now(UTC),
            "iss": "user-service",
            "type": "access",
            "jti": secrets.token_urlsafe(12),
        }
        secret = _settings.AUTH_SECRET or "dev-secret-change-me"
        token = jwt.encode(payload, secret, algorithm="HS256")
        return token, expires

    def _create_refresh_token(self) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(UTC) + timedelta(days=30)
        return token, expires

    async def basic_login(self, username: str, password: str) -> dict[str, Any]:
        if not self.keycloak.is_enabled():
            raise ValueError("Username/password login is disabled; use Keycloak login")

        token_data = await self.keycloak.password_grant(username, password)
        return await self._upsert_user_from_token_data(token_data, fallback_username=username)

    async def external_keycloak_login(
        self,
        username: str,
        password: str,
        redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        if not self.keycloak.is_enabled():
            raise ValueError("External Keycloak login is disabled")

        token_data = await self.keycloak.external_broker_password_login(
            username,
            password,
            redirect_uri=redirect_uri,
        )
        return await self._upsert_user_from_token_data(token_data, fallback_username=username)

    async def register(
        self,
        username: str,
        email: str,
        password: str,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> dict[str, Any]:
        raise ValueError("User registration is managed by Keycloak")

    async def _build_login_response_from_record(
        self, user: dict[str, Any], id_token: str | None = None
    ) -> dict[str, Any]:
        role = normalize_user_role(user.get("role", "enduser"))
        access_token, _expires = self._create_access_token(str(user["id"]), user["email"], role)
        refresh_token, _ = self._create_refresh_token()
        user_id = uuid.UUID(str(user["id"]))

        payload: dict[str, Any] = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "user": {
                "id": str(user_id),
                "email": user["email"],
                "username": user.get("username"),
                "first_name": user.get("first_name"),
                "last_name": user.get("last_name"),
                "role": role,
                "is_active": user.get("is_active"),
                "is_verified": user.get("is_verified"),
                "is_superuser": user.get("is_superuser"),
                "groups": user.get("groups", []) or [],
            },
        }
        if id_token:
            payload["id_token"] = id_token

        return payload

    async def _build_login_response(self, user, id_token: str | None = None) -> dict[str, Any]:
        role = normalize_user_role(user.role)
        access_token, _expires = self._create_access_token(str(user.id), user.email, role)
        refresh_token, _ = self._create_refresh_token()

        payload: dict[str, Any] = {
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
                "role": role,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "is_superuser": user.is_superuser,
                "groups": getattr(user, "groups", []) or [],
            },
        }
        if id_token:
            payload["id_token"] = id_token
        return payload

    async def _build_oidc_login_response(
        self,
        user,
        token_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Return OIDC token payload without persisting local sessions.

        Keycloak is the source of truth for session lifecycle. user-service only
        mirrors user identity and returns the tokens issued by Keycloak.
        """
        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")
        id_token = token_data.get("id_token")
        expires_in = int(token_data.get("expires_in", 3600))

        payload: dict[str, Any] = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_in": expires_in,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": normalize_user_role(user.role),
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "is_superuser": user.is_superuser,
                "groups": getattr(user, "groups", []) or [],
            },
        }
        if id_token:
            payload["id_token"] = id_token
        return payload

    async def _upsert_user_from_token_data(
        self,
        token_data: dict[str, Any],
        fallback_username: str | None = None,
    ) -> dict[str, Any]:
        id_token = token_data.get("id_token", "")
        if not id_token:
            raise ValueError("Authentication failed — no id_token received")

        claims = jwt.get_unverified_claims(id_token)
        keycloak_id = str(claims.get("sub") or "")
        if not keycloak_id:
            raise ValueError("Authentication failed — no subject in token")

        user_email = str(claims.get("email") or fallback_username or "").strip()
        user_username = str(
            claims.get("preferred_username") or fallback_username or user_email
        ).strip()
        first_name = (claims.get("given_name") or "").strip() or None
        last_name = (claims.get("family_name") or "").strip() or None
        role_claims = self._extract_roles_from_claims(claims)
        role = self._resolve_role(role_claims)
        is_external_user = await self._is_external_keycloak_user(keycloak_id)
        if is_external_user:
            role = "enduser"

        user = await self.user_repo.upsert_by_keycloak_id(
            keycloak_id,
            email=user_email or user_username,
            username=user_username,
            first_name=first_name,
            last_name=last_name,
            role=role,
            groups=self._extract_groups_from_claims(claims),
            is_active=True,
            is_verified=True,
            is_external_keycloak_user=is_external_user,
        )

        bootstrap_admin_email = (
            _settings.KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL or _settings.KEYCLOAK_ADMIN_EMAIL
        )
        if bootstrap_admin_email and user_email == bootstrap_admin_email:
            user = await self.user_repo.update(user.id, is_superuser=True, role="system-admin")

        return await self._build_oidc_login_response(user, token_data)

    async def _upsert_external_user_from_claims(self, claims: dict[str, Any]):
        external_subject = str(claims.get("sub") or "").strip()
        if not external_subject:
            raise ValueError("External authentication failed — no subject in token")

        user_email = str(claims.get("email") or "").strip().lower()
        user_username = str(
            claims.get("preferred_username") or user_email or external_subject
        ).strip()
        if not user_email:
            user_email = f"{user_username}@external-keycloak.local"

        first_name = (claims.get("given_name") or "").strip() or None
        last_name = (claims.get("family_name") or "").strip() or None
        groups = self._extract_groups_from_claims(claims)

        sp_user = await self.keycloak.ensure_sp_user_for_external_identity(
            external_subject=external_subject,
            username=user_username,
            email=user_email,
            first_name=first_name,
            last_name=last_name,
        )
        keycloak_id = str(sp_user.get("id") or "")
        if not keycloak_id:
            raise ValueError("External authentication failed — SP user was not created")

        return await self.user_repo.upsert_by_keycloak_id(
            keycloak_id,
            email=user_email,
            username=user_username,
            first_name=first_name,
            last_name=last_name,
            role="enduser",
            groups=groups,
            is_active=True,
            is_verified=True,
            is_external_keycloak_user=True,
        )

    async def logout(
        self,
        refresh_token: str | None = None,
        post_logout_redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        if self.keycloak.is_enabled():
            if post_logout_redirect_uri:
                await self.keycloak.ensure_login_client_redirect_uri(
                    self.keycloak.get_oidc_redirect_uri(),
                    post_logout_redirect_uri=post_logout_redirect_uri,
                )
            await self.keycloak.backchannel_logout(refresh_token=refresh_token)

        return {"message": "Logged out successfully"}

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        if self.keycloak.is_enabled():
            return await self._keycloak_refresh_token(refresh_token)

        raise ValueError("Refresh token management is handled by Keycloak")

    async def _keycloak_refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh tokens via Keycloak's refresh_token grant."""
        token_data = await self.keycloak.refresh_token_grant(refresh_token)

        id_token = token_data.get("id_token", "")
        if not id_token:
            raise ValueError("Token refresh failed — no id_token received")

        from jose import jwt

        claims = jwt.get_unverified_claims(id_token)
        keycloak_id = claims.get("sub", "")
        if not keycloak_id:
            raise ValueError("Token refresh failed — no subject in token")

        user_email = claims.get("email", "")
        user_username = claims.get("preferred_username", "")
        first_name = (claims.get("given_name") or "").strip() or None
        last_name = (claims.get("family_name") or "").strip() or None

        user = await self.user_repo.upsert_by_keycloak_id(
            keycloak_id,
            email=user_email,
            username=user_username,
            first_name=first_name,
            last_name=last_name,
            groups=self._extract_groups_from_claims(claims),
            is_active=True,
            is_verified=True,
            is_external_keycloak_user=await self._is_external_keycloak_user(keycloak_id),
        )

        return await self._build_oidc_login_response(user, token_data)

    async def validate_token(self, token: str) -> dict[str, Any] | None:
        # 1. Try local HS256 decode (legacy user-service tokens)
        try:
            secret = _settings.AUTH_SECRET or "dev-secret-change-me"
            payload = jwt.decode(
                token, secret, algorithms=["HS256"], audience=_settings.SERVICE_NAME
            )
        except JWTError:
            try:
                payload = jwt.decode(
                    token, secret, algorithms=["HS256"], options={"verify_aud": False}
                )
            except JWTError:
                payload = None

        if payload:
            if payload.get("aud") not in (None, _settings.SERVICE_NAME):
                return None
            if payload.get("type") != "access":
                return None
            return payload

        if not self.keycloak.is_enabled():
            return None

        # 2. Try JWKS validation against internal Keycloak (fast path for
        #    internal-KC-issued tokens — no network call to userinfo).
        jwks_claims = await self.keycloak.validate_token_jwks(token)
        if jwks_claims:
            keycloak_id = jwks_claims.get("sub")
            if keycloak_id:
                user = await self.user_repo.get_by_keycloak_id(keycloak_id)
                if not user:
                    user = await self.user_repo.upsert_by_keycloak_id(
                        keycloak_id,
                        email=jwks_claims.get("email", ""),
                        username=jwks_claims.get("preferred_username"),
                        first_name=jwks_claims.get("given_name"),
                        last_name=jwks_claims.get("family_name"),
                        role="enduser",
                        is_active=True,
                        is_verified=True,
                    )
                if user and user.is_active:
                    return {
                        "sub": str(user.id),
                        "keycloak_sub": keycloak_id,
                        "email": user.email,
                        "role": normalize_user_role(user.role),
                        "type": "access",
                    }

        # 3. Try userinfo introspection against internal Keycloak
        user_info = await self.keycloak.get_user_info(token)
        if user_info:
            keycloak_id = user_info.get("sub")
            if keycloak_id:
                user = await self.user_repo.get_by_keycloak_id(keycloak_id)
                if not user and user_info.get("email"):
                    user = await self.user_repo.upsert_by_keycloak_id(
                        keycloak_id,
                        email=user_info["email"],
                        username=user_info.get("preferred_username"),
                        first_name=user_info.get("given_name"),
                        last_name=user_info.get("family_name"),
                        role="enduser",
                        is_active=True,
                        is_verified=True,
                    )
                if user and user.is_active:
                    return {
                        "sub": str(user.id),
                        "keycloak_sub": keycloak_id,
                        "email": user.email,
                        "role": normalize_user_role(user.role),
                        "type": "access",
                    }

        # 4. External Keycloak fallback — userinfo against external IdP
        if self._external_keycloak_enabled():
            external_user_info = await self.keycloak.get_external_user_info(token)
            if external_user_info:
                user = await self._upsert_external_user_from_claims(external_user_info)
                return {
                    "sub": str(user.id),
                    "keycloak_sub": user.keycloak_id,
                    "external_keycloak_sub": external_user_info.get("sub"),
                    "email": user.email,
                    "role": normalize_user_role(user.role),
                    "type": "access",
                }

        return None

    def get_auth_type(self) -> dict[str, Any]:
        if self.keycloak.is_enabled():
            external_keycloak = self._external_keycloak_enabled()
            return {
                "authType": "oidc",
                "keycloakEnabled": True,
                "oauthEnabled": True,
                "externalKeycloak": external_keycloak,
                "external_keycloak": external_keycloak,
                "externalKeycloakAlias": self.keycloak.get_external_keycloak_alias()
                if external_keycloak
                else None,
            }
        return {"authType": "basic", "keycloakEnabled": False}

    async def get_oidc_authorize_url(
        self,
        redirect_uri: str | None = None,
        idp_hint: str | None = None,
    ) -> str:
        state = secrets.token_urlsafe(16)
        callback_uri = redirect_uri or self.keycloak.get_oidc_redirect_uri()
        await self.keycloak.ensure_login_client_redirect_uri(callback_uri)
        return await self.keycloak.get_oidc_authorize_url(
            callback_uri,
            state=state,
            idp_hint=idp_hint,
        )

    async def handle_oidc_callback(
        self,
        code: str,
        redirect_uri: str | None = None,
        fallback_redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        callback_redirect_uri = redirect_uri or self.keycloak.get_oidc_redirect_uri()
        token_data = await self.keycloak.handle_oidc_callback(
            code,
            callback_redirect_uri,
            fallback_redirect_uri=fallback_redirect_uri,
        )

        from jose import jwt

        id_token = token_data.get("id_token", "")

        if id_token:
            claims = jwt.get_unverified_claims(id_token)
            keycloak_id = claims.get("sub", "")
            email = claims.get("email", "")
            username = claims.get("preferred_username", "")
            first_name = (claims.get("given_name") or "").strip() or None
            last_name = (claims.get("family_name") or "").strip() or None

            role_claims = self._extract_roles_from_claims(claims)
            role = self._resolve_role(role_claims)
            is_external_user = await self._is_external_keycloak_user(keycloak_id)
            if is_external_user:
                role = "enduser"

            user = await self.user_repo.upsert_by_keycloak_id(
                keycloak_id,
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                role=role,
                groups=self._extract_groups_from_claims(claims),
                is_active=True,
                is_verified=True,
                is_external_keycloak_user=is_external_user,
            )

            bootstrap_admin_email = (
                _settings.KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL or _settings.KEYCLOAK_ADMIN_EMAIL
            )
            if bootstrap_admin_email and email == bootstrap_admin_email:
                user = await self.user_repo.update(user.id, is_superuser=True, role="system-admin")
            elif is_external_user:
                await self.keycloak.set_realm_role(keycloak_id, "enduser")

            return await self._build_oidc_login_response(user, token_data)

        return token_data

    @staticmethod
    def _extract_roles_from_claims(claims: dict[str, Any]) -> list[str]:
        roles: list[str] = []

        realm_access = claims.get("realm_access")
        if isinstance(realm_access, dict):
            realm_roles = realm_access.get("roles", [])
            if isinstance(realm_roles, list):
                roles.extend(str(role) for role in realm_roles if role is not None)

        resource_access = claims.get("resource_access")
        if isinstance(resource_access, dict):
            for client_mapping in resource_access.values():
                if not isinstance(client_mapping, dict):
                    continue
                client_roles = client_mapping.get("roles", [])
                if isinstance(client_roles, list):
                    roles.extend(str(role) for role in client_roles if role is not None)

        return roles

    @staticmethod
    def _resolve_role(roles: list[str]) -> str:
        role_map = {
            "admin": "system-admin",
            "super_admin": "system-admin",
            "superuser": "system-admin",
            "realm-admin": "system-admin",
        }
        for role in roles:
            normalized = role.strip().lower()
            if normalized in role_map:
                return role_map[normalized]
        return "enduser"

    @staticmethod
    def _extract_groups_from_claims(claims: dict[str, Any]) -> list[str]:
        raw_groups = claims.get("groups", claims.get("group", []))
        if isinstance(raw_groups, str):
            raw_groups = [raw_groups]
        if not isinstance(raw_groups, list):
            return []
        return [str(group) for group in raw_groups if group is not None and str(group).strip()]

    def _external_keycloak_enabled(self) -> bool:
        is_external_keycloak = getattr(self.keycloak, "is_external_keycloak", None)
        return bool(is_external_keycloak()) if callable(is_external_keycloak) else False

    async def _is_external_keycloak_user(self, keycloak_id: str) -> bool:
        if not self._external_keycloak_enabled():
            return False
        user_has_federated_identity = getattr(self.keycloak, "user_has_federated_identity", None)
        if not callable(user_has_federated_identity):
            return False
        try:
            return bool(
                await user_has_federated_identity(
                    keycloak_id,
                    self.keycloak.get_external_keycloak_alias(),
                )
            )
        except Exception:
            return False


_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
