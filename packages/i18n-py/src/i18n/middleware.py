from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .core import normalize_locale, set_locale


class I18nMiddleware(BaseHTTPMiddleware):
    """Starlette / FastAPI middleware for automatic request locale detection."""

    def __init__(self, app: Callable, default_locale: str = "en") -> None:
        super().__init__(app)
        self.default_locale = default_locale

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        locale = self._extract_locale(request)
        set_locale(locale)
        request.state.locale = locale

        response = await call_next(request)
        response.headers["Content-Language"] = locale
        return response

    def _extract_locale(self, request: Request) -> str:
        # 1. Query parameter (?lang=tr or ?locale=tr)
        query_lang = request.query_params.get("lang") or request.query_params.get("locale")
        if query_lang:
            return normalize_locale(query_lang)

        # 2. Custom header (X-Language)
        header_lang = request.headers.get("x-language") or request.headers.get("X-Language")
        if header_lang:
            return normalize_locale(header_lang)

        # 3. Accept-Language header
        accept_lang = request.headers.get("accept-language") or request.headers.get(
            "Accept-Language"
        )
        if accept_lang:
            return normalize_locale(accept_lang)

        # 4. Fallback default
        return self.default_locale
