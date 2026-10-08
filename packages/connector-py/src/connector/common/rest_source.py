"""Shared plumbing for REST-API-backed sources.

Concrete SaaS sources (Jira, Confluence, GitLab, Microsoft Graph, ...) differ in
auth, pagination and stream shape, but all need the same client lifecycle,
retry on ``429``/``5xx`` (and the ``403`` some APIs use for a spent quota) and
JSON decoding. That lives here so each connector only implements what is
specific to its API.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import random
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, ClassVar, TypeVar
from urllib.parse import parse_qsl

import httpx
from pydantic import BaseModel

from ..base import BaseSource
from ..models import CheckResult
from ..redaction import redact_secrets

logger = logging.getLogger("connector.rest")

ConfigT = TypeVar("ConfigT", bound=BaseModel)

RETRY_STATUSES = {429, 500, 502, 503, 504}


class RestSource(BaseSource[ConfigT]):
    """Base for sources that talk to an HTTP JSON API.

    Subclasses implement :meth:`base_url`, optionally :meth:`auth_headers`
    (static headers) or :meth:`prepare_request` (per-request, e.g. OAuth tokens),
    and set ``check_path`` for the default :meth:`check`.
    """

    check_path: ClassVar[str] = "/"
    max_retries: ClassVar[int] = 3
    retry_delay: ClassVar[float] = 0.5
    rate_limit_retries: ClassVar[int] = 5
    """Attempts for a 429, whose penalties outlast a transient 5xx by far."""
    rate_limit_delay: ClassVar[float] = 2.0
    """First wait after a 429 without Retry-After; doubles per attempt, 60 s at most."""
    rate_limit_reset_max: ClassVar[float] = 3600.0
    """Longest wait for an ``x-ratelimit-reset`` stamp (GitHub's primary limit resets hourly)."""
    default_timeout: ClassVar[float] = 30.0
    follow_redirects: ClassVar[bool] = True
    """Whether the client this source builds follows 3xx answers. A redirect carries
    the source's headers along; a source whose address and headers are whatever
    a user typed in turns this off."""

    def __init__(self, config: ConfigT, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config)
        self._client = client
        self._owns_client = client is None

    # ---- hooks ---------------------------------------------------------------

    def base_url(self) -> str:
        raise NotImplementedError

    def auth_headers(self) -> dict[str, str]:
        return {}

    async def prepare_request(self, headers: dict[str, str]) -> None:
        """Mutate ``headers`` right before a request (token refresh etc.)."""

    def timeout(self) -> float:
        return float(getattr(self.config, "timeout_seconds", self.default_timeout))

    def verify_ssl(self) -> bool:
        return bool(getattr(self.config, "verify_ssl", True))

    # ---- client ---------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url().rstrip("/"),
                headers={"Accept": "application/json", **self.auth_headers()},
                timeout=self.timeout(),
                verify=self.verify_ssl(),
                follow_redirects=self.follow_redirects,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | str | None = None,
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Send with retry on transient failures. Raises on final HTTP error."""
        hdrs = dict(headers or {})
        if self._client is not None and not self._owns_client:
            # Injected clients (tests) may lack auth; make sure it is present.
            hdrs = {**self.auth_headers(), **hdrs}
        await self.prepare_request(hdrs)
        last: Exception | None = None
        attempt = 0
        while True:
            attempt += 1
            retry_after: float | None = None
            rate_limited = False
            try:
                resp = await self._get_client().request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=hdrs,
                    content=content,
                    data=data,
                )
            except httpx.TransportError as exc:
                last = exc
            else:
                rate_limited = _is_rate_limited(resp)
                if resp.status_code not in RETRY_STATUSES and not rate_limited:
                    resp.raise_for_status()
                    return resp
                last = httpx.HTTPStatusError(
                    f"{resp.status_code} from {url}: {resp.text[:200]}",
                    request=resp.request,
                    response=resp,
                )
                retry_after = _retry_after(resp)
                if retry_after is None and rate_limited:
                    retry_after = _reset_wait(resp, self.rate_limit_reset_max)
            attempts = self.rate_limit_retries if rate_limited else self.max_retries
            if attempt >= attempts:
                break
            # Without query strings: that is where keys and tokens travel.
            logger.warning(
                "%s %s failed (attempt %d): %s",
                method,
                url.partition("?")[0],
                attempt,
                redact_secrets(str(last)),
            )
            if retry_after:
                delay = retry_after
            elif rate_limited:
                # No Retry-After: the penalty is unknown and tends to be long (tens of
                # seconds). Grow the wait; jitter keeps parallel syncs apart.
                delay = min(self.rate_limit_delay * 2 ** (attempt - 1), 60.0) * random.uniform(
                    0.8, 1.2
                )
            else:
                delay = self.retry_delay * attempt
            await asyncio.sleep(delay)
        assert last is not None
        raise last

    async def get_json(self, url: str, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        resp = await self.request("GET", url, params=params, **kw)
        return resp.json() if resp.content else None

    async def post_json(self, url: str, json: Any, **kw: Any) -> Any:
        resp = await self.request("POST", url, json=json, **kw)
        return resp.json() if resp.content else None

    # ---- default check ---------------------------------------------------------

    async def check(self) -> CheckResult:
        try:
            await self.request("GET", self.check_path)
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)


def split_query(url: str, params: Mapping[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """Merge a query string embedded in ``url`` with ``params``.

    httpx replaces the URL's own query when ``params`` is passed, so an address
    like ``/tasks?project=1`` would silently lose ``project``. ``params`` wins on
    clashes.
    """
    if not params or "?" not in url:
        return url, dict(params or {})
    base, _, query = url.partition("?")
    merged: dict[str, Any] = dict(parse_qsl(query, keep_blank_values=True))
    merged.update(params)
    return base, merged


def basic_auth_header(username: str, password: str) -> dict[str, str]:
    """``Authorization: Basic ...`` for ``username:password``."""
    raw = f"{username}:{password}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def _is_rate_limited(resp: httpx.Response) -> bool:
    """``429``, or the ``403`` GitHub-style APIs answer when the quota is spent."""
    if resp.status_code == 429:
        return True
    if resp.status_code != 403:
        return False
    return resp.headers.get("x-ratelimit-remaining") == "0" or "Retry-After" in resp.headers


def _reset_wait(resp: httpx.Response, cap: float) -> float | None:
    """Seconds until the quota window reopens per ``x-ratelimit-reset`` (epoch seconds)."""
    value = resp.headers.get("x-ratelimit-reset")
    if not value:
        return None
    try:
        reset_at = float(value)
    except ValueError:
        return None
    return min(max(reset_at - datetime.now(UTC).timestamp(), 1.0), cap)


def _retry_after(resp: httpx.Response) -> float | None:
    """Seconds to wait per ``Retry-After`` (delay-seconds or an HTTP-date), 60 s at most."""
    value = resp.headers.get("Retry-After")
    if not value:
        return None
    try:
        return min(float(value), 60.0)
    except ValueError:
        pass
    try:
        at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return min(max((at - datetime.now(UTC)).total_seconds(), 0.0), 60.0)


def iso_or_none(value: Any) -> str | None:
    """A timestamp as ISO-8601 in UTC, or ``None`` when ``value`` is not one."""
    parsed = parse_iso(value)
    return parsed.isoformat() if parsed else None


def parse_iso(value: Any) -> datetime | None:
    """Parse ISO-8601 (with ``Z``) into an aware UTC datetime; ``None`` on failure."""
    if not isinstance(value, str) or not value:
        return None
    if value.replace(".", "", 1).isdigit():  # epoch or id, not a compact ISO date
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
