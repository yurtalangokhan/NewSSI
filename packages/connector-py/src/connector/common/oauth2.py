"""OAuth2 bearer tokens for server-to-server flows.

:class:`OAuth2Token` fetches a token, caches it and refreshes it a minute
before expiry. :class:`OAuth2BearerMixin` puts it on every request of a
``RestSource``. The token request goes through the source's own httpx client,
so tests can intercept it with a mock transport and a host can route it through
a client of its own.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

import httpx

from ..errors import SourceError
from .rest_source import RETRY_STATUSES

Form = Mapping[str, Any]


class OAuth2Token:
    """Fetches and caches a bearer token from ``token_url``.

    ``form`` is the request body, or a callable building it for each request
    (a signed assertion that carries its own timestamp must be fresh every time).
    """

    attempts = 3
    retry_delay = 0.5

    def __init__(
        self,
        token_url: str,
        form: Form | Callable[[], Form],
        *,
        basic_auth: tuple[str, str] | None = None,
        token_field: str = "access_token",
        default_ttl: float = 3600.0,
    ) -> None:
        self.token_url = token_url
        self.form = form
        self.basic_auth = basic_auth
        self.token_field = token_field
        self.default_ttl = default_ttl
        self._token: str | None = None
        self._expires_at = 0.0
        self.last_response: dict[str, Any] = {}

    async def get(self, client: httpx.AsyncClient) -> str:
        if self._token and time.monotonic() < self._expires_at - 60:
            return self._token
        body = await self._request(client)
        self.last_response = body
        token = body.get(self.token_field)
        if not token:
            raise SourceError(f"token response has no '{self.token_field}'")
        self._token = str(token)
        self._expires_at = time.monotonic() + float(body.get("expires_in") or self.default_ttl)
        return self._token

    async def _request(self, client: httpx.AsyncClient) -> dict[str, Any]:
        form = self.form() if callable(self.form) else self.form
        data = {k: v for k, v in form.items() if v is not None}
        failure = "no attempt was made"
        for attempt in range(1, self.attempts + 1):
            try:
                resp = await client.post(
                    self.token_url,
                    data=data,
                    auth=self.basic_auth or httpx.USE_CLIENT_DEFAULT,
                    headers={"Accept": "application/json"},
                )
            except httpx.TransportError as exc:
                failure = str(exc) or type(exc).__name__
            else:
                if resp.status_code < 400:
                    try:
                        payload = resp.json()
                    except ValueError:
                        # A proxy's sign-in page, say. The body is not quoted: it is
                        # not ours to repeat, and asking again would not change it.
                        kind = resp.headers.get("content-type") or "no content type"
                        raise SourceError(
                            f"token request failed: {resp.status_code} with a body "
                            f"that is not JSON ({kind})"
                        ) from None
                    return payload if isinstance(payload, dict) else {}
                failure = f"{resp.status_code} {resp.text[:200]}"
                if resp.status_code not in RETRY_STATUSES:
                    break  # rejected credentials do not get better by asking again
            if attempt < self.attempts:
                await asyncio.sleep(self.retry_delay * attempt)
        raise SourceError(f"token request failed: {failure}")

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = 0.0


class OAuth2BearerMixin:
    """Bearer authentication for a ``RestSource``. List it before the source base class.

    Implement :meth:`oauth2_token`; override :meth:`static_token` when the
    configuration may carry a ready-made token instead.
    """

    _oauth: OAuth2Token | None = None

    if TYPE_CHECKING:

        def _get_client(self) -> httpx.AsyncClient: ...

    def static_token(self) -> str | None:
        """A token given in the configuration; it is used as is and never refreshed."""
        return None

    def oauth2_token(self) -> OAuth2Token:
        raise NotImplementedError

    def token_source(self) -> OAuth2Token:
        if self._oauth is None:
            self._oauth = self.oauth2_token()
        return self._oauth

    async def access_token(self) -> str:
        return self.static_token() or await self.token_source().get(self._get_client())

    async def prepare_request(self, headers: dict[str, str]) -> None:
        headers.setdefault("Authorization", f"Bearer {await self.access_token()}")
