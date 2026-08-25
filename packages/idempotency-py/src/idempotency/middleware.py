import asyncio
import base64
import hashlib
import json
import logging
from datetime import datetime, timezone

import redis.exceptions as redis_exceptions
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from idempotency.config import IdempotencyConfig
from idempotency.models import (
    CachedResponse,
    IdempotencyKeyOwner,
    IdempotencyMode,
    IdempotencyPolicy,
)
from idempotency.redis_client import AsyncRedisPool
from idempotency.storage import (
    ClaimKeyOwnerResult,
    acquire_lock,
    claim_key_owner,
    get_cached_response,
    get_key_owner,
    release_lock,
    renew_lock,
    set_cached_response,
    set_key_owner,
    wait_for_lock_and_get,
)

logger = logging.getLogger(__name__)

_STRIPPED_RESPONSE_HEADERS = {
    "content-encoding",
    "content-length",
    "server",
    "set-cookie",
    "transfer-encoding",
    "www-authenticate",
    "x-powered-by",
}

_IDEMPOTENCY_KEY_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)

_BODY_CACHE_METADATA_VERSION = 2


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        config: IdempotencyConfig,
        exclude_paths: set[str] | None = None,
    ):
        super().__init__(app)
        self.config = config
        self.exclude_paths = exclude_paths or set()

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if not self.config.idempotency_enabled:
            return await call_next(request)

        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await call_next(request)

        if request.url.path in self.exclude_paths:
            return await call_next(request)

        policy = self.config.policy.resolve(request.method, request.url.path)
        if policy.mode == IdempotencyMode.EXCLUDED:
            return await call_next(request)

        idem_key = request.headers.get("Idempotency-Key")
        key_required = policy.enforce_missing_key or (
            self.config.enforce_required_keys
            and policy.mode
            in {
                IdempotencyMode.REQUIRED_REPLAY,
                IdempotencyMode.DOMAIN_REQUIRED,
            }
        )
        if not idem_key:
            if key_required:
                return self._error_response(
                    status_code=400,
                    code="idempotency_key_required",
                    message="Idempotency-Key header is required for this endpoint.",
                )
            return await call_next(request)

        if not self._is_valid_key(idem_key):
            return self._error_response(
                status_code=400,
                code="idempotency_key_invalid",
                message=(
                    "Idempotency-Key must be 1-255 characters long and contain "
                    "only letters, digits, '.', '_' or '-'."
                ),
            )

        body = await request.body()
        fingerprint = self._fingerprint(request, body)
        principal_scope = self._principal_scope(request)

        try:
            redis = await AsyncRedisPool.connect(self.config)

            owner = await get_key_owner(redis, self.config.service_name, idem_key)
            owner_existed = owner is not None
            if owner is not None and self._owner_conflicts(
                owner,
                principal_scope,
                fingerprint,
            ):
                return self._key_reused_response()
            if owner is None:
                claimed = await claim_key_owner(
                    redis,
                    self.config.service_name,
                    idem_key,
                    IdempotencyKeyOwner(
                        principal_scope=principal_scope,
                        request_fingerprint=fingerprint,
                    ),
                    self.config.idempotency_ttl,
                )
                if claimed == ClaimKeyOwnerResult.CONFLICT:
                    return self._key_reused_response()
                owner_existed = claimed == ClaimKeyOwnerResult.EXISTING_COMPATIBLE
            cached = await get_cached_response(
                redis,
                self.config.service_name,
                principal_scope,
                idem_key,
            )
            if cached is not None:
                if cached.fingerprint != fingerprint:
                    return self._key_reused_response()
                return self._replay_response(cached)

            if owner_existed and policy.mode == IdempotencyMode.DOMAIN_REQUIRED:
                return self._error_response(
                    status_code=self.config.inflight_timeout_status_code,
                    code="idempotency_request_in_progress",
                    message="A request with this Idempotency-Key is still in progress.",
                )

            locked = await acquire_lock(
                redis,
                self.config.service_name,
                principal_scope,
                idem_key,
                lock_ttl=self.config.lock_ttl,
            )
            if not locked:
                cached = await wait_for_lock_and_get(
                    redis,
                    self.config.service_name,
                    principal_scope,
                    idem_key,
                    max_wait=self.config.wait_timeout,
                )
                if cached is not None:
                    if cached.fingerprint != fingerprint:
                        return self._key_reused_response()
                    return self._replay_response(cached)
                owner = await get_key_owner(redis, self.config.service_name, idem_key)
                if owner is None or self._owner_conflicts(
                    owner,
                    principal_scope,
                    fingerprint,
                ):
                    return self._key_reused_response()
                locked = await acquire_lock(
                    redis,
                    self.config.service_name,
                    principal_scope,
                    idem_key,
                    lock_ttl=self.config.lock_ttl,
                )
                if not locked:
                    return self._error_response(
                        status_code=self.config.inflight_timeout_status_code,
                        code="idempotency_request_in_progress",
                        message="A request with this Idempotency-Key is still in progress.",
                    )
                owner = await get_key_owner(redis, self.config.service_name, idem_key)
                if owner is None or self._owner_conflicts(
                    owner,
                    principal_scope,
                    fingerprint,
                ):
                    await release_lock(
                        redis,
                        self.config.service_name,
                        principal_scope,
                        idem_key,
                        lock_token=locked,
                    )
                    return self._key_reused_response()
        except redis_exceptions.RedisError as exc:
            logger.warning(
                "Idempotency store unavailable for %s %s: %s",
                request.method,
                request.url.path,
                exc,
            )
            if key_required:
                return self._error_response(
                    status_code=503,
                    code="idempotency_store_unavailable",
                    message=(
                        "The idempotency store is temporarily unavailable; "
                        "retry the request with the same Idempotency-Key."
                    ),
                )
            return await call_next(request)

        renew_task = asyncio.create_task(
            self._renew_lock_loop(
                redis,
                principal_scope,
                idem_key,
                locked,
            )
        )
        try:
            response = await call_next(request)

            if (
                response.headers.get("content-type", "")
                .startswith("text/event-stream")
            ):
                if policy.mode == IdempotencyMode.DOMAIN_REQUIRED:
                    await self._mark_completed_without_replay(
                        redis,
                        idem_key,
                        principal_scope,
                        fingerprint,
                    )
                return response

            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            cached_response_written = False
            if (
                self._is_cacheable_status(response.status_code, policy)
                and len(body) <= self.config.max_cache_body_size
            ):
                cached_resp = CachedResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    body=base64.b64encode(body).decode("ascii"),
                    created_at=datetime.now(timezone.utc),
                    fingerprint=fingerprint,
                    principal_scope=principal_scope,
                    metadata_version=_BODY_CACHE_METADATA_VERSION,
                )
                await set_cached_response(
                    redis,
                    self.config.service_name,
                    principal_scope,
                    idem_key,
                    cached_resp,
                    self.config.idempotency_ttl,
                )
                cached_response_written = True
            if (
                policy.mode == IdempotencyMode.DOMAIN_REQUIRED
                and not cached_response_written
            ):
                await self._mark_completed_without_replay(
                    redis,
                    idem_key,
                    principal_scope,
                    fingerprint,
                )
            return Response(
                content=body,
                status_code=response.status_code,
                media_type=response.media_type,
                headers=dict(response.headers),
            )
        finally:
            renew_task.cancel()
            try:
                await renew_task
            except asyncio.CancelledError:
                pass
            except redis_exceptions.RedisError:
                logger.warning(
                    "Lock renewal failed for %s %s; releasing lock.",
                    request.method,
                    request.url.path,
                )
            await release_lock(
                redis,
                self.config.service_name,
                principal_scope,
                idem_key,
                lock_token=locked,
            )

    async def _renew_lock_loop(
        self,
        redis,
        principal_scope: str,
        idem_key: str,
        token: str,
    ) -> None:
        """Keep the request lock alive while a long request runs.

        Without renewal, lock_ttl (10s default) can be shorter than the request
        (LLM calls, ingestion), letting a waiting duplicate acquire the expired
        lock and execute the side effect twice.
        """
        interval = max(1.0, self.config.lock_ttl / 3)
        try:
            while True:
                await asyncio.sleep(interval)
                renewed = await renew_lock(
                    redis,
                    self.config.service_name,
                    principal_scope,
                    idem_key,
                    token,
                    ttl_ms=int(self.config.lock_ttl * 1000),
                )
                if not renewed:
                    return
        except asyncio.CancelledError:
            raise
        except redis_exceptions.RedisError:
            logger.warning(
                "Could not renew idempotency lock for key=%s", idem_key
            )
            return

    @staticmethod
    def _owner_conflicts(
        owner: IdempotencyKeyOwner,
        principal_scope: str,
        fingerprint: str,
    ) -> bool:
        if owner.principal_scope != principal_scope:
            return True
        if owner.request_fingerprint not in {None, fingerprint}:
            return True
        return owner.completed_without_replay

    @staticmethod
    def _is_valid_key(idem_key: str) -> bool:
        if not 1 <= len(idem_key) <= 255:
            return False
        return all(char in _IDEMPOTENCY_KEY_CHARS for char in idem_key)

    def _principal_scope(self, request: Request) -> str:
        for header_name in self.config.principal_header_candidates:
            header_value = request.headers.get(header_name)
            if header_value:
                digest = hashlib.sha256(header_value.encode()).hexdigest()
                return f"{header_name.lower()}:{digest}"
        return "anonymous"

    @staticmethod
    def _fingerprint(request: Request, body: bytes) -> str:
        payload = {
            "method": request.method.upper(),
            "path": request.url.path,
            "query": request.url.query,
            "content_type": request.headers.get("content-type", ""),
            "body_sha256": hashlib.sha256(body).hexdigest(),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    def _is_cacheable_status(
        self,
        status_code: int,
        policy: IdempotencyPolicy,
    ) -> bool:
        if status_code == 429 or status_code >= 500:
            return False
        if self.config.cacheable_status_codes is not None:
            return status_code in self.config.cacheable_status_codes
        if (
            400 <= status_code <= 499
            and not policy.cache_deterministic_client_errors
        ):
            return False
        return any(
            start <= status_code <= end
            for start, end in self.config.cacheable_status_ranges
        )

    async def _mark_completed_without_replay(
        self,
        redis,
        idem_key: str,
        principal_scope: str,
        fingerprint: str,
    ) -> None:
        await set_key_owner(
            redis,
            self.config.service_name,
            idem_key,
            IdempotencyKeyOwner(
                principal_scope=principal_scope,
                request_fingerprint=fingerprint,
                completed_without_replay=True,
            ),
            self.config.idempotency_ttl,
        )

    def _replay_response(self, cached: CachedResponse) -> Response:
        if cached.metadata_version and cached.metadata_version >= 2:
            content = base64.b64decode(cached.body)
        else:
            content = cached.body.encode()
        headers = self._replay_headers(cached.headers)
        if "content-type" not in headers:
            headers["content-type"] = "application/json"
        return Response(
            content=content,
            status_code=cached.status_code,
            headers=headers,
        )

    @staticmethod
    def _replay_headers(headers: dict[str, str]) -> dict[str, str]:
        replay_headers = {
            key: value
            for key, value in headers.items()
            if key.lower() not in _STRIPPED_RESPONSE_HEADERS
        }
        replay_headers["Idempotency-Replayed"] = "true"
        return replay_headers

    @staticmethod
    def _error_response(status_code: int, code: str, message: str) -> Response:
        return Response(
            content=json.dumps(
                {
                    "error": {
                        "code": code,
                        "message": message,
                        "details": {},
                        "field_errors": [],
                        "request_id": None,
                    }
                }
            ),
            status_code=status_code,
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    @classmethod
    def _key_reused_response(cls) -> Response:
        return cls._error_response(
            status_code=409,
            code="idempotency_key_reused",
            message=(
                "Idempotency-Key was already used for a different request or "
                "principal."
            ),
        )
