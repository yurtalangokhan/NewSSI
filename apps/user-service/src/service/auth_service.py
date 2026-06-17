import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from src.config import get_settings
from src.core.database.models.user_model import normalize_user_role
from src.repository import SessionRepository, UserRepository

from .keycloak_service import get_keycloak_service
from .ldap_service import get_ldap_service

_settings = get_settings()


class AuthService:
    def __init__(self):
        self.session_repo = SessionRepository()
        self.user_repo = UserRepository()
        self.keycloak = get_keycloak_service()
        self.ldap = get_ldap_service()

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            return False

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

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
        if self.keycloak.is_enabled():
            return await self._keycloak_password_login(username, password)

        local_login = await self._local_basic_login(username, password)
        if local_login:
            return local_login

        raise ValueError("Invalid credentials")

    async def ldap_signup_signin(self, username: str, password: str) -> dict[str, Any]:
        """LDAP-authenticated signup/signin: LDAP -> DB -> Keycloak -> tokens.

        1. Authenticate user against LDAP
        2. Create or update user in local DB (no password stored)
        3. If Keycloak enabled, ensure user exists in Keycloak with password synced
        4. Get tokens from Keycloak (or issue local JWT if KC disabled)
        """
        if not self.ldap.is_enabled():
            raise ValueError("LDAP authentication is not enabled")

        ldap_attrs = await self.ldap.authenticate(username, password)
        if not ldap_attrs:
            raise ValueError("LDAP authentication failed — invalid credentials")

        user_fields = self._map_ldap_attributes(ldap_attrs)
        email = user_fields.get("email") or f"{username}@ldap.local"
        ldap_username = user_fields.get("username") or username

        user = await self.user_repo.get_by_email(email)
        if not user:
            user = await self.user_repo.get_by_username(ldap_username)

        if user:
            update_kwargs: dict[str, Any] = {}
            if user_fields.get("first_name") is not None:
                update_kwargs["first_name"] = user_fields["first_name"]
            if user_fields.get("last_name") is not None:
                update_kwargs["last_name"] = user_fields["last_name"]
            if user_fields.get("email") is not None:
                update_kwargs["email"] = user_fields["email"]
            if user_fields.get("username") is not None:
                update_kwargs["username"] = user_fields["username"]
            if update_kwargs:
                user = await self.user_repo.update(user.id, **update_kwargs)
        else:
            user = await self.user_repo.create(
                email=email,
                username=ldap_username,
                first_name=user_fields.get("first_name"),
                last_name=user_fields.get("last_name"),
                role="enduser",
                is_active=True,
                is_verified=True,
            )

        if self.keycloak.is_enabled():
            kc_user = await self.keycloak.get_user_by_email(email)
            if kc_user:
                kc_id = kc_user.get("id")
                await self.keycloak.set_password(kc_id, password, temporary=False)
                if not user.keycloak_id:
                    user = await self.user_repo.update(user.id, keycloak_id=kc_id)
            else:
                kc_id = await self.keycloak.create_user({
                    "email": email,
                    "username": ldap_username,
                    "firstName": user_fields.get("first_name") or ldap_username,
                    "lastName": user_fields.get("last_name") or "User",
                    "enabled": True,
                    "emailVerified": True,
                    "credentials": [
                        {"type": "password", "value": password, "temporary": False},
                    ],
                })
                if kc_id:
                    user = await self.user_repo.update(user.id, keycloak_id=kc_id)

            token_data = await self.keycloak.password_grant(ldap_username, password)
            return await self._build_oidc_login_response(user, token_data)

        return await self._build_login_response(user)

    def _map_ldap_attributes(self, ldap_attrs: dict[str, Any]) -> dict[str, Any]:
        return self.ldap._map_ldap_entry(ldap_attrs)

    async def search_ldap_users(
        self,
        filter_str: str = "(objectClass=person)",
        attributes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.ldap.is_enabled():
            raise ValueError("LDAP is not enabled")
        return await self.ldap.search_users(filter_str, attributes)

    async def validate_ldap_user(self, username: str) -> bool:
        if not self.ldap.is_enabled():
            raise ValueError("LDAP is not enabled")
        return await self.ldap.validate_user(username)

    async def _local_basic_login(self, username: str, password: str) -> dict[str, Any] | None:
        user = await self.user_repo.get_by_email(username)
        if not user:
            user = await self.user_repo.get_by_username(username)

        if not user or not user.hashed_password:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            raise ValueError("User account is disabled")

        return await self._build_login_response(user)

    async def _keycloak_password_login(self, username: str, password: str) -> dict[str, Any]:
        """Authenticate via Keycloak Direct Access Grant (password grant).

        Used when KEYCLOAK_ENABLED=True and user submits username/password
        through the login form (no OIDC redirect).
        """
        token_data = await self.keycloak.password_grant(username, password)

        id_token = token_data.get("id_token", "")
        if not id_token:
            raise ValueError("Authentication failed — no id_token received")

        from jose import jwt

        claims = jwt.get_unverified_claims(id_token)
        keycloak_id = claims.get("sub", "")
        user_email = claims.get("email", "")
        if not keycloak_id:
            raise ValueError("Authentication failed — no subject in token")

        user_username = claims.get("preferred_username", "")
        first_name = (claims.get("given_name") or "").strip() or None
        last_name = (claims.get("family_name") or "").strip() or None

        role_claims = self._extract_roles_from_claims(claims)
        role = self._resolve_role(role_claims)

        user = await self.user_repo.upsert_by_keycloak_id(
            keycloak_id,
            email=user_email or username,
            username=user_username or username,
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=True,
            is_verified=True,
        )

        bootstrap_admin_email = (
            _settings.KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL or _settings.KEYCLOAK_ADMIN_EMAIL
        )
        if bootstrap_admin_email and user_email == bootstrap_admin_email:
            user = await self.user_repo.update(user.id, is_superuser=True, role="admin")

        return await self._build_oidc_login_response(user, token_data)

    async def register(
        self,
        username: str,
        email: str,
        password: str,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> dict[str, Any]:
        """Register a new user with username+password.

        1. Creates user in Keycloak (if enabled) + local DB via UserService
        2. Auto-logs in and returns tokens
        """
        from src.service import get_user_service

        user_service = get_user_service()

        normalized_first_name = (first_name or "").strip()
        normalized_last_name = (last_name or "").strip()
        if not normalized_first_name or not normalized_last_name:
            raise ValueError("first_name and last_name are required")

        created_user = await user_service.create_user(
            email=email,
            username=username,
            first_name=normalized_first_name,
            last_name=normalized_last_name,
            password=password,
            role="enduser",
        )

        if self.keycloak.is_enabled():
            # In OIDC mode, always return Keycloak-issued tokens to keep all services
            # on the same token validation path.
            return await self._keycloak_password_login(username, password)

        return await self._build_login_response_from_record(created_user)

    async def _build_login_response_from_record(
        self, user: dict[str, Any], id_token: str | None = None
    ) -> dict[str, Any]:
        role = normalize_user_role(user.get("role", "enduser"))
        access_token, expires = self._create_access_token(str(user["id"]), user["email"], role)
        refresh_token, _refresh_expires = self._create_refresh_token()
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
            },
        }
        if id_token:
            payload["id_token"] = id_token

        await self.session_repo.create(
            user_id=user_id,
            token_hash=self._hash_token(access_token),
            refresh_token_hash=self._hash_token(refresh_token),
            expires_at=expires,
        )
        return payload

    async def _build_login_response(self, user, id_token: str | None = None) -> dict[str, Any]:
        role = normalize_user_role(user.role)
        access_token, expires = self._create_access_token(str(user.id), user.email, role)
        refresh_token, refresh_expires = self._create_refresh_token()

        await self.session_repo.create(
            user_id=user.id,
            token_hash=self._hash_token(access_token),
            refresh_token_hash=self._hash_token(refresh_token),
            expires_at=expires,
        )

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
            },
        }
        if id_token:
            payload["id_token"] = id_token
        return payload

    async def logout(self, refresh_token: str | None = None) -> dict[str, Any]:
        if refresh_token:
            await self.session_repo.delete_by_refresh_token_hash(self._hash_token(refresh_token))

        if self.keycloak.is_enabled():
            await self.keycloak.backchannel_logout(refresh_token=refresh_token)

        return {"message": "Logged out successfully"}

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        session = await self.session_repo.get_by_refresh_token_hash(self._hash_token(refresh_token))
        if session:
            current_time = datetime.now(UTC)
            if session.expires_at < current_time:
                await self.session_repo.delete_by_refresh_token_hash(self._hash_token(refresh_token))
                raise ValueError("Refresh token expired")

            user = await self.user_repo.get_by_id(session.user_id)
            if not user or not user.is_active:
                raise ValueError("User not found or inactive")

            await self.session_repo.delete_by_refresh_token_hash(self._hash_token(refresh_token))

            role = normalize_user_role(user.role)
            access_token, expires = self._create_access_token(str(user.id), user.email, role)
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

        if self.keycloak.is_enabled():
            return await self._keycloak_refresh_token(refresh_token)

        raise ValueError("Invalid refresh token")

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
            is_active=True,
            is_verified=True,
        )

        return await self._build_oidc_login_response(user, token_data)

    async def validate_token(self, token: str) -> dict[str, Any] | None:
        try:
            secret = _settings.AUTH_SECRET or "dev-secret-change-me"
            payload = jwt.decode(
                token, secret, algorithms=["HS256"], audience=_settings.SERVICE_NAME
            )
        except JWTError:
            try:
                # Accept legacy service tokens that were minted before the aud claim was added.
                payload = jwt.decode(
                    token, secret, algorithms=["HS256"], options={"verify_aud": False}
                )
            except JWTError:
                payload = None

        if payload:
            if payload.get("aud") not in (None, _settings.SERVICE_NAME):
                return None

            try:
                if payload.get("type") != "access":
                    return None
                return payload
            except JWTError:
                return None

        if not self.keycloak.is_enabled():
            return None

        claims = await self.keycloak.validate_token_jwks(token)
        if claims:
            keycloak_id = claims.get("sub", "")
            if keycloak_id:
                user = await self.user_repo.get_by_keycloak_id(keycloak_id)
                if not user and claims.get("email"):
                    user = await self.user_repo.upsert_by_keycloak_id(
                        keycloak_id,
                        email=claims["email"],
                        username=claims.get("preferred_username"),
                        first_name=claims.get("given_name"),
                        last_name=claims.get("family_name"),
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

        user_info = await self.keycloak.get_user_info(token)
        if not user_info:
            return None

        keycloak_id = user_info.get("sub")
        if not keycloak_id:
            return None

        user = await self.user_repo.get_by_keycloak_id(keycloak_id)
        if not user and user_info.get("email"):
            user = await self.user_repo.upsert_by_keycloak_id(
                keycloak_id,
                email=user_info["email"],
                username=user_info.get("preferred_username"),
                first_name=user_info.get("given_name"),
                last_name=user_info.get("family_name"),
                is_active=True,
                is_verified=True,
            )
        if not user or not user.is_active:
            return None

        return {
            "sub": str(user.id),
            "keycloak_sub": keycloak_id,
            "email": user.email,
            "role": normalize_user_role(user.role),
            "type": "access",
        }

    def get_auth_type(self) -> dict[str, Any]:
        base_metadata = {
            "autoRedirect": False,
            "requiresVerification": False,
            "anonymousUserEnabled": True,
            "hasUsers": True,
        }
        if self.keycloak.is_enabled():
            return {
                **base_metadata,
                "authType": "oidc",
                "keycloakEnabled": True,
                "oauthEnabled": True,
            }
        return {
            **base_metadata,
            "authType": "basic",
            "keycloakEnabled": False,
            "oauthEnabled": False,
        }

    async def get_oidc_authorize_url(
        self, redirect_uri: str = "http://localhost:3000/auth/oidc/callback"
    ) -> str:
        state = secrets.token_urlsafe(16)
        return await self.keycloak.get_oidc_authorize_url(redirect_uri, state=state)

    async def handle_oidc_callback(
        self,
        code: str,
        redirect_uri: str = "http://localhost:3000/auth/oidc/callback",
        fallback_redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        token_data = await self.keycloak.handle_oidc_callback(
            code,
            redirect_uri,
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

            bootstrap_admin_email = (
                _settings.KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL or _settings.KEYCLOAK_ADMIN_EMAIL
            )
            if bootstrap_admin_email and email == bootstrap_admin_email:
                user = await self.user_repo.update(user.id, is_superuser=True, role="admin")

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
            "admin": "admin",
            "super_admin": "admin",
            "superuser": "admin",
            "realm-admin": "admin",
        }
        for role in roles:
            normalized = role.strip().lower()
            if normalized in role_map:
                return role_map[normalized]
        return "enduser"


_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
