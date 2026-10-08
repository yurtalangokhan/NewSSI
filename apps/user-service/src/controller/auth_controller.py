import base64
import binascii
from datetime import UTC, datetime
import json
from typing import Any

from fastapi import Request, Response

from src.core.observability import get_logger
from src.service import get_auth_service

from .base import BaseController

logger = get_logger(__name__)

MAX_AUTH_SET_COOKIE_HEADER_BYTES = 3900
MAX_ID_TOKEN_COOKIE_VALUE_BYTES = 3800

# Used only when the identity provider does not tell us how long a token is
# good for. Real lifetimes come from the token response (`expires_in` /
# `refresh_expires_in`) so the cookie expires with the token it carries.
DEFAULT_ACCESS_TOKEN_MAX_AGE = 3600
DEFAULT_REFRESH_TOKEN_MAX_AGE = 30 * 86400


def cookies_should_be_secure() -> bool:
    """Whether auth cookies get the Secure attribute.

    Read through a function rather than inlined so the whole cookie set moves
    together and tests can pin it without touching settings construction.
    """
    from config_manager import env

    return bool(env.COOKIE_SECURE)


class AuthController(BaseController):
    def __init__(self):
        self.auth_service = get_auth_service()

    async def get_auth_type(self) -> dict[str, Any]:
        return self.auth_service.get_auth_type()

    async def login(self, response: Response, username: str, password: str) -> dict[str, Any]:
        try:
            result = await self.auth_service.basic_login(username, password)
            self._set_cookies(
                response,
                result.get("access_token", ""),
                result.get("refresh_token", ""),
                result.get("id_token"),
                **self._set_cookie_kwargs(result),
            )
            return result
        except ValueError:
            self._raise_bad_request()

    async def external_login(
        self,
        response: Response,
        username: str,
        password: str,
        redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        try:
            result = await self.auth_service.external_keycloak_login(
                username,
                password,
                redirect_uri=redirect_uri,
            )
            self._set_cookies(
                response,
                result.get("access_token", ""),
                result.get("refresh_token") or "",
                result.get("id_token"),
                **self._set_cookie_kwargs(result),
            )
            return result
        except ValueError:
            self._raise_bad_request()

    async def logout(
        self,
        request: Request,
        response: Response,
        post_logout_redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        refresh_token = request.cookies.get("refresh_token")
        self._clear_cookies(response)
        return await self.auth_service.logout(refresh_token, post_logout_redirect_uri)

    async def refresh(self, request: Request, response: Response) -> dict[str, Any]:
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            self._raise_bad_request("auth.refresh_token_required")
        try:
            result = await self.auth_service.refresh_access_token(refresh_token)
            self._set_cookies(
                response,
                result.get("access_token", ""),
                result.get("refresh_token", ""),
                result.get("id_token"),
                **self._set_cookie_kwargs(result),
            )
            return result
        except ValueError:
            self._raise_unauthorized()

    async def oidc_authorize(
        self,
        redirect_uri: str | None = None,
        kc_idp_hint: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        url = await self.auth_service.get_oidc_authorize_url(
            redirect_uri,
            idp_hint=kc_idp_hint,
            prompt=prompt,
        )
        return {"authorization_url": url}

    async def oidc_callback(
        self,
        request: Request,
        response: Response,
        code: str,
        redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        request_callback_uri = str(request.url).split("?", 1)[0]
        try:
            result = await self.auth_service.handle_oidc_callback(
                code,
                redirect_uri,
                fallback_redirect_uri=request_callback_uri,
            )
            self._set_cookies(
                response,
                result.get("access_token", ""),
                result.get("refresh_token", ""),
                result.get("id_token"),
                **self._set_cookie_kwargs(result),
            )
            return result
        except ValueError as e:
            self._raise_bad_request("auth.oidc_callback_failed", error=str(e))

    def _set_cookies(
        self,
        response: Response,
        access_token: str,
        refresh_token: str,
        id_token: str | None = None,
        expires_in: int | None = None,
        refresh_expires_in: int | None = None,
    ):
        access_max_age = self._cookie_max_age(expires_in, DEFAULT_ACCESS_TOKEN_MAX_AGE)
        session_max_age = self._cookie_max_age(refresh_expires_in, DEFAULT_REFRESH_TOKEN_MAX_AGE)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            samesite="lax",
            max_age=access_max_age,
            secure=cookies_should_be_secure(),
        )
        if refresh_token:
            # Deliberately not path-scoped. The web app forwards this
            # Set-Cookie to the browser verbatim, so the Path is read
            # against *its* routes, and the two that need the cookie sit in
            # different trees: refresh at /api/auth/refresh, and logout at
            # /auth/logout, which needs it to revoke the Keycloak session
            # back-channel. No single prefix covers both, so narrowing would
            # buy defence-in-depth on one origin by breaking either every
            # session refresh or single-sign-out. HttpOnly + SameSite +
            # Secure are what actually contain this cookie.
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                samesite="lax",
                max_age=session_max_age,
                secure=cookies_should_be_secure(),
            )
        if id_token and self._can_set_id_token_cookie(response, id_token, session_max_age):
            response.set_cookie(
                key="id_token",
                value=id_token,
                httponly=True,
                samesite="lax",
                max_age=session_max_age,
                secure=cookies_should_be_secure(),
            )

    @staticmethod
    def _cookie_max_age(raw: Any, fallback: int) -> int:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return fallback
        return value if value > 0 else fallback

    @staticmethod
    def _set_cookie_kwargs(result: dict[str, Any]) -> dict[str, Any]:
        """Cookie lifetimes for a token payload returned by the auth service."""
        return {
            "expires_in": result.get("expires_in"),
            "refresh_expires_in": result.get("refresh_expires_in"),
        }

    def _can_set_id_token_cookie(
        self,
        response: Response,
        id_token: str,
        max_age: int = DEFAULT_REFRESH_TOKEN_MAX_AGE,
    ) -> bool:
        id_token_bytes = len(id_token.encode("utf-8"))
        if id_token_bytes > MAX_ID_TOKEN_COOKIE_VALUE_BYTES:
            logger.warning(
                "Skipping id_token cookie because it exceeds browser-safe cookie size (%s bytes)",
                id_token_bytes,
            )
            return False

        candidate_header_bytes = self._cookie_header_bytes(
            key="id_token",
            value=id_token,
            max_age=max_age,
        )
        total_header_bytes = self._set_cookie_header_bytes(response) + candidate_header_bytes
        if total_header_bytes > MAX_AUTH_SET_COOKIE_HEADER_BYTES:
            logger.warning(
                "Skipping id_token cookie because auth Set-Cookie headers exceed gateway-safe size (%s bytes)",
                total_header_bytes,
            )
            return False

        return True

    @staticmethod
    def _cookie_header_bytes(key: str, value: str, max_age: int) -> int:
        response = Response()
        response.set_cookie(
            key=key,
            value=value,
            httponly=True,
            samesite="lax",
            max_age=max_age,
            secure=cookies_should_be_secure(),
        )
        return AuthController._set_cookie_header_bytes(response)

    @staticmethod
    def _set_cookie_header_bytes(response: Response) -> int:
        return sum(len(value) for key, value in response.raw_headers if key.lower() == b"set-cookie")

    def _clear_cookies(self, response: Response):
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        response.delete_cookie("id_token")
        response.delete_cookie("fastapiusersauth")

    async def register(
        self,
        response: Response,
        username: str,
        email: str,
        password: str,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> dict[str, Any]:
        try:
            result = await self.auth_service.register(username, email, password, first_name, last_name)
            self._set_cookies(
                response,
                result.get("access_token", ""),
                result.get("refresh_token", ""),
                result.get("id_token"),
                **self._set_cookie_kwargs(result),
            )
            return result
        except ValueError:
            self._raise_bad_request()

    async def sync_users_from_keycloak(self) -> dict[str, Any]:
        """Sync users and roles from Keycloak to user-service DB."""
        try:
            from src.service import get_user_service

            user_service = get_user_service()
            result = await user_service.sync_users_from_keycloak()
            return result
        except ValueError as e:
            self._raise_bad_request("auth.sync_failed", error=str(e))

    async def get_me(self, request: Request, user_id: str | None = None) -> dict[str, Any]:
        from src.service import get_user_service

        user = await get_user_service().get_current_user(user_id)
        if not user:
            self._raise_not_found("user.not_found")
        return {**user, **self._current_token_lifetime(request)}

    @staticmethod
    def _unverified_jwt_claims(token: str) -> dict[str, Any] | None:
        """Read a JWT's payload without verifying it.

        This is only used to tell the client how long its own token is good
        for; the token itself is verified by the auth dependency before the
        request ever reaches here. Decoding by hand keeps this independent of
        which JWT library is in play and of whatever `alg` the token declares.
        """
        parts = token.split(".")
        if len(parts) < 2:
            return None

        payload = parts[1]
        padded = payload + "=" * (-len(payload) % 4)
        try:
            claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return None

        return claims if isinstance(claims, dict) else None

    @staticmethod
    def _bearer_token_from_request(request: Request) -> str | None:
        authorization = request.headers.get("authorization") or ""
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()
        return request.cookies.get("access_token")

    def _current_token_lifetime(self, request: Request) -> dict[str, Any]:
        """Expose the caller's access-token window on /me.

        The web client arms its proactive session-refresh timer from these
        fields; without them `getSecondsUntilExpiration` returns null and the
        timer never runs, so the session is only ever renewed reactively (and
        never at all on a server-rendered page load).
        """
        token = self._bearer_token_from_request(request)
        if not token:
            return {}

        claims = self._unverified_jwt_claims(token)
        if claims is None:
            return {}

        exp = claims.get("exp")
        if not isinstance(exp, int | float):
            return {}

        iat = claims.get("iat")
        if not isinstance(iat, int | float):
            # Tokens without `iat` still carry `exp`; anchor the window at now
            # so the client computes a sane countdown.
            iat = datetime.now(UTC).timestamp()

        expiry_length = int(exp - iat)
        if expiry_length <= 0:
            return {}

        return {
            "current_token_created_at": datetime.fromtimestamp(iat, UTC).isoformat(),
            "current_token_expiry_length": expiry_length,
        }


_auth_controller: AuthController | None = None


def get_auth_controller() -> AuthController:
    global _auth_controller
    if _auth_controller is None:
        _auth_controller = AuthController()
    return _auth_controller
