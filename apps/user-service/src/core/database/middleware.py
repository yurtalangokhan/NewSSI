"""ASGI middleware owning the commit/rollback decision for the one session
shared by every repository call within a single HTTP request (Spec T5).

Pure-ASGI, matching the style of the other cross-cutting middleware in this
codebase (``metrics.MetricsMiddleware``) rather than
``BaseHTTPMiddleware``, and for the same reason: it needs the final response
status straight from the ``http.response.start`` message.
"""

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from .engine import request_scoped_session

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class RequestScopedSessionMiddleware:
    """Open at most one session per request and commit or roll it back as a
    whole.

    The session itself is opened lazily, by whichever repository call (if
    any) needs it first -- a request that never touches a repository (a
    health check, a pure auth/config lookup) never opens a real DB
    connection, and there is nothing here for this middleware to commit or
    roll back.

    A response status below 400 commits. Anything else -- a 4xx/5xx
    response, or an exception that isn't turned into a response by an inner
    exception handler -- rolls back, so a request that fails partway through
    never leaves an earlier repository call's write committed on its own.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status_code = 500

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        async with request_scoped_session() as session_scope:
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception:
                if session_scope.session is not None:
                    await session_scope.session.rollback()
                raise
            if session_scope.session is None:
                return
            if status_code < 400:
                await session_scope.session.commit()
            else:
                await session_scope.session.rollback()
