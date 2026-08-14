from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .core import normalize_locale, set_locale


class I18nMiddleware:
    """Starlette / FastAPI middleware for automatic request locale detection.

    Implemented as a plain ASGI middleware rather than `BaseHTTPMiddleware`:
    the latter buffers/rewraps the response through an internal task, which is
    known to break long-lived `StreamingResponse`s (e.g. chat SSE) — the
    connection can be cut before the stream finishes even though the app
    handler completed normally. Setting a header requires only intercepting
    `http.response.start`, which plain ASGI middleware can do without
    touching the body at all.
    """

    def __init__(self, app: ASGIApp, default_locale: str = "en") -> None:
        self.app = app
        self.default_locale = default_locale

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        locale = self._extract_locale(request)
        set_locale(locale)
        scope.setdefault("state", {})["locale"] = locale

        async def send_with_locale_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Language"] = locale
            await send(message)

        await self.app(scope, receive, send_with_locale_header)

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
