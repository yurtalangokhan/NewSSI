import logging
from typing import Any

from fastapi import Request, Response

from src.service import get_auth_service

from .base import BaseController

logger = logging.getLogger(__name__)

MAX_ID_TOKEN_COOKIE_VALUE_BYTES = 3800


class AuthController(BaseController):
    def __init__(self):
        self.auth_service = get_auth_service()

    async def get_auth_type(self) -> dict[str, Any]:
        return self.auth_service.get_auth_type()

    async def login(
        self, request: Request, response: Response, username: str, password: str
    ) -> dict[str, Any]:
        try:
            result = await self.auth_service.basic_login(username, password)
            self._set_cookies(
                response,
                result.get("access_token", ""),
                result.get("refresh_token", ""),
                result.get("id_token"),
            )
            return result
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def external_login(
        self,
        request: Request,
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
            )
            return result
        except ValueError as e:
            self._raise_bad_request(str(e))

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
            self._raise_bad_request("Refresh token required")
        try:
            result = await self.auth_service.refresh_access_token(refresh_token)
            self._set_cookies(
                response,
                result.get("access_token", ""),
                result.get("refresh_token", ""),
                result.get("id_token"),
            )
            return result
        except ValueError as e:
            self._raise_unauthorized(str(e))

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
        # Return both formats for compatibility:
        # - authorization_url: JSON response field
        # - authorize_url: legacy field name
        return {"authorization_url": url, "authorize_url": url}

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
            )
            return result
        except Exception as e:
            self._raise_bad_request(f"OIDC callback failed: {e}")

    def _set_cookies(
        self,
        response: Response,
        access_token: str,
        refresh_token: str,
        id_token: str | None = None,
    ):
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            samesite="lax",
            max_age=3600,
            secure=False,
        )
        if refresh_token:
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                samesite="lax",
                max_age=30 * 86400,
                secure=False,
            )
        if id_token and len(id_token.encode("utf-8")) <= MAX_ID_TOKEN_COOKIE_VALUE_BYTES:
            response.set_cookie(
                key="id_token",
                value=id_token,
                httponly=True,
                samesite="lax",
                max_age=30 * 86400,
                secure=False,
            )
        elif id_token:
            logger.warning(
                "Skipping id_token cookie because it exceeds browser-safe cookie size "
                "(%s bytes)",
                len(id_token.encode("utf-8")),
            )

    def _clear_cookies(self, response: Response):
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        response.delete_cookie("id_token")
        response.delete_cookie("fastapiusersauth")

    async def register(
        self,
        request: Request,
        response: Response,
        username: str,
        email: str,
        password: str,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> dict[str, Any]:
        try:
            result = await self.auth_service.register(
                username, email, password, first_name, last_name
            )
            self._set_cookies(
                response,
                result.get("access_token", ""),
                result.get("refresh_token", ""),
                result.get("id_token"),
            )
            return result
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def ldap_login(
        self, request: Request, response: Response, username: str, password: str
    ) -> dict[str, Any]:
        try:
            result = await self.auth_service.ldap_signup_signin(username, password)
            self._set_cookies(
                response,
                result.get("access_token", ""),
                result.get("refresh_token", ""),
                result.get("id_token"),
            )
            return result
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def search_ldap_users(
        self, filter_str: str = "(objectClass=person)", attributes: list[str] | None = None
    ) -> list[dict[str, Any]]:
        try:
            return await self.auth_service.search_ldap_users(filter_str, attributes)
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def validate_ldap_user(self, username: str) -> dict[str, Any]:
        try:
            exists = await self.auth_service.validate_ldap_user(username)
            return {"username": username, "exists": exists}
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def sync_users_from_keycloak(self) -> dict[str, Any]:
        """Sync users and roles from Keycloak to user-service DB."""
        try:
            from src.service import get_user_service

            user_service = get_user_service()
            result = await user_service.sync_users_from_keycloak()
            return result
        except Exception as e:
            self._raise_bad_request(f"Sync failed: {str(e)}")

    async def get_me(self, request: Request, user_id: str | None = None) -> dict[str, Any]:
        from src.service import get_user_service

        user = await get_user_service().get_current_user(user_id)
        if not user:
            self._raise_not_found("User not found")
        return user


_auth_controller: AuthController | None = None


def get_auth_controller() -> AuthController:
    global _auth_controller
    if _auth_controller is None:
        _auth_controller = AuthController()
    return _auth_controller
