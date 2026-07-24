import logging
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from idempotency.config import IdempotencyConfig
from idempotency.models import CachedResponse
from idempotency.redis_client import AsyncRedisPool
from idempotency.storage import (
    acquire_lock,
    get_cached_response,
    release_lock,
    set_cached_response,
    wait_for_lock_and_get,
)

logger = logging.getLogger(__name__)


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

        idem_key = request.headers.get("Idempotency-Key")
        if not idem_key:
            return await call_next(request)

        redis = await AsyncRedisPool.connect(self.config)

        cached = await get_cached_response(
            redis, self.config.service_name, idem_key,
        )
        if cached is not None:
            return Response(
                content=cached.body,
                status_code=cached.status_code,
                media_type=cached.headers.get("content-type", "application/json"),
                headers={
                    k: v
                    for k, v in cached.headers.items()
                    if k.lower()
                    not in ("content-encoding", "transfer-encoding", "content-length")
                },
            )

        locked = await acquire_lock(redis, self.config.service_name, idem_key)
        if not locked:
            cached = await wait_for_lock_and_get(
                redis, self.config.service_name, idem_key,
            )
            if cached is not None:
                return Response(
                    content=cached.body,
                    status_code=cached.status_code,
                    media_type=cached.headers.get("content-type", "application/json"),
                    headers=cached.headers,
                )
            locked = await acquire_lock(
                redis, self.config.service_name, idem_key,
            )
            if not locked:
                return Response(
                    content='{"error":"concurrency limit exceeded"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": "5"},
                )

        try:
            response = await call_next(request)

            if (
                response.headers.get("content-type", "")
                .startswith("text/event-stream")
            ):
                return response

            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            cached_resp = CachedResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=body.decode(),
                created_at=datetime.utcnow(),
            )
            await set_cached_response(
                redis,
                self.config.service_name,
                idem_key,
                cached_resp,
                self.config.idempotency_ttl,
            )

            return Response(
                content=body,
                status_code=response.status_code,
                media_type=response.media_type,
                headers=dict(response.headers),
            )
        finally:
            await release_lock(redis, self.config.service_name, idem_key)
