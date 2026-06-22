from typing import Any

from fastapi import Request, Response

from src.service.external_auth_service import get_external_auth_service

from .base import BaseController


class ExternalAuthController(BaseController):
    """Controller for external Keycloak auth flows.

    Keycloak owns authentication; user-service keeps the local application user.
    """

    def __init__(self):
        self.auth_service = get_external_auth_service()

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

    async def logout(self, request: Request, response: Response) -> dict[str, Any]:
        refresh_token = request.cookies.get("refresh_token")
        self._clear_cookies(response)
        return await self.auth_service.logout(refresh_token)

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

    async def oidc_authorize(self, redirect_uri: str | None = None) -> dict[str, Any]:
        url = await self.auth_service.get_oidc_authorize_url(redirect_uri)
        return {"authorization_url": url, "authorize_url": url}

    async def oidc_callback(
        self,
        request: Request,
        response: Response,
        code: str,
        redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        uri = redirect_uri or "http://localhost:3000/auth/oidc/callback"
        request_callback_uri = str(request.url).split("?", 1)[0]
        try:
            result = await self.auth_service.handle_oidc_callback(
                code,
                uri,
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

    async def get_me(self, request: Request, user_id: str | None = None) -> dict[str, Any]:
        try:
            return await self.auth_service.get_current_user(request)
        except ValueError as e:
            self._raise_unauthorized(str(e))

    async def sync_users_from_keycloak(self) -> dict[str, Any]:
        try:
            from src.service import get_user_service

            return await get_user_service().sync_users_from_keycloak()
        except Exception as e:
            self._raise_bad_request(f"Sync failed: {str(e)}")

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
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            samesite="lax",
            max_age=30 * 86400,
            secure=False,
        )
        if id_token:
            response.set_cookie(
                key="id_token",
                value=id_token,
                httponly=True,
                samesite="lax",
                max_age=30 * 86400,
                secure=False,
            )

    def _clear_cookies(self, response: Response):
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        response.delete_cookie("id_token")
        response.delete_cookie("fastapiusersauth")


_external_auth_controller: ExternalAuthController | None = None


def get_external_auth_controller() -> ExternalAuthController:
    global _external_auth_controller
    if _external_auth_controller is None:
        _external_auth_controller = ExternalAuthController()
    return _external_auth_controller
