import secrets
from typing import Any

from config_manager import env
from error_contract import DependencyResponseError, ForbiddenError
from jose import JWTError, jwt

from src.core.permissions.roles import display_role_name
from src.repository import UserRepository

from .keycloak_service import get_keycloak_service

_settings = env


def _coerce_positive_int(raw: Any, fallback: int | None) -> int | None:
    """Return `raw` as a positive int, or `fallback` when it is unusable.

    Keycloak omits `refresh_expires_in` for offline tokens and reports `0`
    when the refresh token does not expire, so both cases fall back.
    """
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


class AuthService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.keycloak = get_keycloak_service()

    async def basic_login(self, username: str, password: str) -> dict[str, Any]:
        token_data = await self.keycloak.password_grant(username, password)
        return await self._upsert_user_from_token_data(token_data, fallback_username=username)

    async def external_keycloak_login(
        self,
        username: str,
        password: str,
        redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        token_data = await self.keycloak.external_broker_password_login(
            username,
            password,
            redirect_uri=redirect_uri,
        )
        return await self._upsert_user_from_token_data(token_data, fallback_username=username)

    # Signature is the auth-service interface; Keycloak owns registration, so
    # the arguments are intentionally unused by this rejecting implementation.
    async def register(
        self,
        username: str,  # noqa: ARG002
        email: str,  # noqa: ARG002
        password: str,  # noqa: ARG002
        first_name: str | None = None,  # noqa: ARG002
        last_name: str | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        raise ForbiddenError(
            message_key="errors.user_service.auth.registration_managed_by_keycloak",
            message_params={},
        )

    async def _build_oidc_login_response(
        self,
        user,
        token_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Return OIDC token payload without persisting local sessions.

        Keycloak is the source of truth for session lifecycle. user-service only
        reads user identity and returns the tokens issued by Keycloak.
        """
        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")
        id_token = token_data.get("id_token")
        expires_in = _coerce_positive_int(token_data.get("expires_in"), 3600)
        # Keycloak reports the refresh token's own lifetime (SSO session idle,
        # or the offline-session lifespan). It is what the refresh_token cookie
        # should live for - a cookie that outlives the token it carries just
        # produces refresh attempts that Keycloak is guaranteed to reject.
        refresh_expires_in = _coerce_positive_int(token_data.get("refresh_expires_in"), None)

        payload: dict[str, Any] = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_in": expires_in,
            "refresh_expires_in": refresh_expires_in,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": display_role_name(user.role),
                "is_active": user.is_active,
                "is_verified": user.is_verified,
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
            raise DependencyResponseError(message_key="errors.user_service.auth.no_id_token", message_params={})

        claims = jwt.get_unverified_claims(id_token)
        keycloak_id = str(claims.get("sub") or "")
        if not keycloak_id:
            raise DependencyResponseError(message_key="errors.user_service.auth.no_subject_in_token", message_params={})

        user_email = str(claims.get("email") or fallback_username or "").strip()
        user_username = str(claims.get("preferred_username") or fallback_username or user_email).strip()
        first_name = (claims.get("given_name") or "").strip() or None
        last_name = (claims.get("family_name") or "").strip() or None
        is_external_user = await self._is_external_keycloak_user(keycloak_id)
        role_update = await self._default_role_update_for_new_user(keycloak_id)

        user = await self.user_repo.upsert_by_keycloak_id(
            keycloak_id,
            email=user_email or user_username,
            username=user_username,
            first_name=first_name,
            last_name=last_name,
            groups=self._extract_groups_from_claims(claims),
            is_active=True,
            is_verified=True,
            is_external_keycloak_user=is_external_user,
            **role_update,
        )

        return await self._build_oidc_login_response(user, token_data)

    async def logout(
        self,
        refresh_token: str | None = None,
        post_logout_redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        if post_logout_redirect_uri:
            await self.keycloak.ensure_login_client_redirect_uri(
                self.keycloak.get_oidc_redirect_uri(),
                post_logout_redirect_uri=post_logout_redirect_uri,
            )
        await self.keycloak.backchannel_logout(refresh_token=refresh_token)

        return {"message": "Logged out successfully"}

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        return await self._keycloak_refresh_token(refresh_token)

    async def _keycloak_refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh tokens via Keycloak's refresh_token grant."""
        token_data = await self.keycloak.refresh_token_grant(refresh_token)

        claims = self._extract_claims(token_data.get("id_token"))
        if claims is None:
            claims = self._extract_claims(token_data.get("access_token"))

        if claims is None:
            raise DependencyResponseError(message_key="errors.user_service.auth.refresh_no_id_token", message_params={})

        user_email = str(claims.get("email") or "")
        keycloak_id = str(claims.get("sub") or "")
        if not keycloak_id:
            raise DependencyResponseError(
                message_key="errors.user_service.auth.refresh_no_subject_in_token",
                message_params={},
            )

        user_username = str(claims.get("preferred_username") or "")
        first_name = (claims.get("given_name") or "").strip() or None
        last_name = (claims.get("family_name") or "").strip() or None

        user = await self.user_repo.upsert_by_keycloak_id(
            keycloak_id,
            email=user_email,
            username=(user_username or keycloak_id),
            first_name=first_name,
            last_name=last_name,
            groups=self._extract_groups_from_claims(claims),
            is_active=True,
            is_verified=True,
            is_external_keycloak_user=await self._is_external_keycloak_user(keycloak_id),
        )

        return await self._build_oidc_login_response(user, token_data)

    @staticmethod
    def _extract_claims(token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        try:
            claims = jwt.get_unverified_claims(token)
        except JWTError:
            return None
        return claims if isinstance(claims, dict) else None

    def get_auth_type(self) -> dict[str, Any]:
        external_keycloak = self._external_keycloak_enabled()
        return {
            "authType": "oidc",
            "keycloakEnabled": True,
            "oauthEnabled": True,
            "externalKeycloak": external_keycloak,
            "external_keycloak": external_keycloak,
            "externalKeycloakAlias": self.keycloak.get_external_keycloak_alias() if external_keycloak else None,
        }

    async def get_oidc_authorize_url(
        self,
        redirect_uri: str | None = None,
        idp_hint: str | None = None,
        prompt: str | None = None,
    ) -> str:
        state = secrets.token_urlsafe(16)
        callback_uri = redirect_uri or self.keycloak.get_oidc_redirect_uri()
        await self.keycloak.ensure_login_client_redirect_uri(callback_uri)
        return await self.keycloak.get_oidc_authorize_url(
            callback_uri,
            state=state,
            idp_hint=idp_hint,
            prompt=prompt,
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

            is_external_user = await self._is_external_keycloak_user(keycloak_id)
            role_update = await self._default_role_update_for_new_user(keycloak_id)

            user = await self.user_repo.upsert_by_keycloak_id(
                keycloak_id,
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                groups=self._extract_groups_from_claims(claims),
                is_active=True,
                is_verified=True,
                is_external_keycloak_user=is_external_user,
                **role_update,
            )

            return await self._build_oidc_login_response(user, token_data)

        return token_data

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

    async def _default_role_update_for_new_user(self, keycloak_id: str) -> dict[str, str]:
        existing_user = await self.user_repo.get_by_id(keycloak_id)
        return {} if existing_user else {"role": "enduser"}

    async def _is_external_keycloak_user(self, keycloak_id: str) -> bool:
        if not self._external_keycloak_enabled():
            return False
        user_has_federated_identity = getattr(self.keycloak, "user_has_federated_identity", None)
        if not callable(user_has_federated_identity):
            return False
        return bool(
            await user_has_federated_identity(
                keycloak_id,
                self.keycloak.get_external_keycloak_alias(),
            )
        )


_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
