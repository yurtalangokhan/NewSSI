import asyncio
import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

import redis.exceptions as redis_exceptions
from error_contract import render_error_message
from error_contract.idempotency import (
    IdempotencyInProgressError,
    IdempotencyKeyInvalidError,
    IdempotencyKeyRequiredError,
    IdempotencyKeyReusedError,
    IdempotencyStoreUnavailableError,
)
from fastapi import Request, Response
from localization import normalize_locale
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from idempotency.config import IdempotencyConfig
from idempotency.models import (
    CachedResponse,
    IdempotencyDecision,
    IdempotencyKeyOwner,
    IdempotencyMode,
    IdempotencyOutcome,
    IdempotencyPolicy,
)
from idempotency.redis_client import AsyncRedisPool
from idempotency.storage import (
    ClaimKeyOwnerResult,
    acquire_lock,
    claim_key_owner,
    delete_key_owner,
    get_cached_response,
    get_key_owner,
    release_lock,
    renew_lock,
    set_cached_response,
    set_key_owner,
    wait_for_lock_and_get,
)

# A rejected request must not hold the key's owner record for the full
# idempotency_ttl: that would block the correct principal from retrying
# with valid credentials for up to 24h (spec TS-13).
_UNAUTHORISED_STATUS_CODES = frozenset({401, 403})

logger = logging.getLogger(__name__)

#: Typed application error behind each middleware error code; it owns the
#: localized message rendered into the response.
_IDEMPOTENCY_ERRORS = {
    "idempotency_key_required": IdempotencyKeyRequiredError,
    "idempotency_key_invalid": IdempotencyKeyInvalidError,
    "idempotency_key_reused": IdempotencyKeyReusedError,
    "idempotency_request_in_progress": IdempotencyInProgressError,
    "idempotency_store_unavailable": IdempotencyStoreUnavailableError,
}

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

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Label for requests that matched no explicit policy. Never a real path.
_DEFAULT_ROUTE_LABEL = "<default>"


def _bare_decision(
    outcome: IdempotencyOutcome,
    route_template: str,
    **fields: object,
) -> IdempotencyDecision:
    """Build a decision before a `_RequestContext` exists."""
    return IdempotencyDecision(
        outcome=outcome,
        route_template=route_template,
        **fields,  # type: ignore[arg-type]
    )


@dataclass(frozen=True)
class _Preflight:
    """What survives the eligibility check in `_preflight`."""

    policy: IdempotencyPolicy
    idem_key: str
    key_required: bool
    # The matched policy's path, which is the route template. A request that
    # matched no explicit policy gets the default's path, which is the
    # concrete request path; callers label that case explicitly instead.
    route_template: str


class _HeaderCarrier(Protocol):
    def get(self, key: str) -> str | None: ...


def _resolve_request_id(headers: _HeaderCarrier) -> str:
    """Correlate the log record with the error contract's id.

    Mirrors ``error_contract.resolve_request_id``: prefer the caller's own
    correlation header so one id ties the middleware log to the response
    envelope, and mint one only when neither header exists. The middleware
    runs before the error contract, so when both mint, the ids differ — the
    header-supplied case is the one that must correlate.
    """
    return headers.get("x-request-id") or headers.get("x-correlation-id") or str(uuid4())


# Outcomes that resolved a request normally; everything else refused or
# degraded it. Drives the decision log's status field.
_OK_OUTCOMES = frozenset(
    {
        IdempotencyOutcome.EXECUTED,
        IdempotencyOutcome.REPLAYED,
        IdempotencyOutcome.COMPLETED_NO_REPLAY,
        IdempotencyOutcome.BYPASSED,
    }
)


@dataclass(frozen=True)
class _RequestContext:
    """The per-request facts every later phase needs.

    Passing one object keeps the phase helpers' signatures readable and stops
    the same five values from being threaded through each call.
    """

    request: Request
    policy: IdempotencyPolicy
    idem_key: str
    fingerprint: str
    principal_scope: str
    key_required: bool
    route_template: str
    request_id: str

    def decision(
        self,
        outcome: IdempotencyOutcome,
        **fields: object,
    ) -> IdempotencyDecision:
        """Build a decision tagged with the matched route template.

        The template comes from the policy, not from `request.url.path`, which
        the router has already resolved to a concrete path. Using the path
        would make one metric series per key.
        """
        return IdempotencyDecision(
            outcome=outcome,
            route_template=self.route_template,
            **fields,  # type: ignore[arg-type]
        )


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
        preflight = self._preflight(request)
        if isinstance(preflight, Response):
            return preflight
        if preflight is None:
            return await call_next(request)

        body = await request.body()
        ctx = _RequestContext(
            request=request,
            policy=preflight.policy,
            idem_key=preflight.idem_key,
            fingerprint=self._fingerprint(request, body),
            principal_scope=await self._principal_scope(request),
            key_required=preflight.key_required,
            route_template=preflight.route_template,
            request_id=_resolve_request_id(request.headers),
        )

        try:
            redis = await AsyncRedisPool.connect(self.config)
            lock = await self._acquire_slot(redis, ctx)
            if isinstance(lock, Response):
                return lock
        except redis_exceptions.RedisError:
            return await self._store_unavailable(ctx, call_next)

        return await self._execute(redis, ctx, call_next, lock)

    def _record(
        self,
        decision: IdempotencyDecision,
        *,
        request_id: str | None = None,
    ) -> None:
        """Log the decision, then hand it to the configured recorder.

        Every decision gets one info record so replay rates and conflict spikes
        are visible without debug logging; `store_unavailable` is excluded
        because its own warning already carries the failure detail. A recorder
        that raises must not turn a completed request into a 500, so failures
        are swallowed after being logged. The recorder is synchronous and
        local, so it is not awaited.
        """
        if decision.outcome is not IdempotencyOutcome.STORE_UNAVAILABLE:
            logger.info(
                "Idempotency decision outcome=%s route=%s",
                decision.outcome,
                decision.route_template,
                extra={
                    "event": "idempotency.decision",
                    "status": "ok"
                    if decision.outcome in _OK_OUTCOMES
                    else "rejected",
                    "outcome": decision.outcome,
                    "request_id": request_id,
                },
            )
        recorder = self.config.decision_recorder
        if recorder is None:
            return
        try:
            recorder(decision)
        except Exception:
            logger.warning(
                "Idempotency decision recorder failed for outcome=%s",
                decision.outcome,
                exc_info=True,
                extra={
                    "event": "idempotency.recorder_failed",
                    "status": "degraded",
                    "error_code": "idempotency_recorder_failed",
                    "request_id": request_id,
                },
            )

    @staticmethod
    def _route_label(
        request: Request,
        policy: IdempotencyPolicy | None = None,
    ) -> str:
        """The metric label for a route.

        A matched policy's path is the route template the service registered,
        so it is a bounded, stable label shared with `http_requests_total`.
        Without a match there is no template, and the request path is
        unbounded, so the label falls back to a constant rather than leaking
        one series per key.
        """
        if policy is None:
            return _DEFAULT_ROUTE_LABEL
        return policy.path

    def _key_is_required(self, policy: IdempotencyPolicy) -> bool:
        if policy.enforce_missing_key is not None:
            return policy.enforce_missing_key
        return self.config.enforce_required_keys and policy.mode in {
            IdempotencyMode.REQUIRED_REPLAY,
            IdempotencyMode.DOMAIN_REQUIRED,
        }

    def _preflight(
        self,
        request: Request,
    ) -> _Preflight | Response | None:
        """Decide whether the middleware participates at all.

        Returns None when it steps aside, a Response when the request is
        rejected before Redis is touched, and otherwise the resolved policy
        and key that every later phase needs.
        """
        if not self.config.idempotency_enabled:
            return None
        if request.method not in _MUTATING_METHODS:
            return None
        if request.url.path in self.exclude_paths:
            return None

        policy = self.config.policy.resolve(request.method, request.url.path)
        if policy.mode == IdempotencyMode.EXCLUDED:
            return None

        key_required = self._key_is_required(policy)
        idem_key = request.headers.get("Idempotency-Key")
        if not idem_key:
            if key_required:
                self._record(
                    _bare_decision(
                        IdempotencyOutcome.KEY_REQUIRED,
                        self._route_label(request),
                        status_code=400,
                        error_code="idempotency_key_required",
                    ),
                    request_id=_resolve_request_id(request.headers),
                )
                return self._error_response(
                    request=request,
                    status_code=400,
                    code="idempotency_key_required",
                    message="Idempotency-Key header is required for this endpoint.",
                )
            self._record(
                _bare_decision(
                    IdempotencyOutcome.BYPASSED,
                    self._route_label(request),
                ),
                request_id=_resolve_request_id(request.headers),
            )
            return None

        if not self._is_valid_key(idem_key):
            self._record(
                _bare_decision(
                    IdempotencyOutcome.KEY_INVALID,
                    self._route_label(request),
                    status_code=400,
                    error_code="idempotency_key_invalid",
                ),
                request_id=_resolve_request_id(request.headers),
            )
            return self._error_response(
                request=request,
                status_code=400,
                code="idempotency_key_invalid",
                message=(
                    "Idempotency-Key must be 1-255 characters long and contain "
                    "only letters, digits, '.', '_' or '-'."
                ),
            )
        return _Preflight(
            policy=policy,
            idem_key=idem_key,
            key_required=key_required,
            route_template=self._route_label(request, policy),
        )

    async def _acquire_slot(
        self,
        redis,
        ctx: _RequestContext,
    ) -> str | Response:
        """Claim the key, then take the execution lock.

        Returns the owned lock token, or the response to send when this request
        must not execute. Each terminal branch records its own outcome, so the
        decision is logged exactly once per request.
        """
        owner_existed = await self._claim_ownership(redis, ctx)
        if isinstance(owner_existed, Response):
            return self._recorded(
                ctx,
                IdempotencyOutcome.CONFLICT,
                owner_existed,
                lock_acquired=False,
            )

        replay = await self._replay_if_cached(redis, ctx)
        if replay is not None:
            response, outcome = replay
            return self._recorded(
                ctx,
                outcome,
                response,
                replayed=outcome is IdempotencyOutcome.REPLAYED,
                lock_acquired=False,
            )

        if owner_existed and ctx.policy.mode == IdempotencyMode.DOMAIN_REQUIRED:
            return self._recorded(
                ctx,
                IdempotencyOutcome.IN_FLIGHT,
                self._in_flight_response(ctx.request),
                lock_acquired=False,
            )

        lock = await acquire_lock(
            redis,
            self.config.service_name,
            ctx.principal_scope,
            ctx.idem_key,
            lock_ttl=self.config.lock_ttl,
        )
        if lock:
            return lock
        return await self._retry_after_wait(redis, ctx)

    def _recorded(
        self,
        ctx: _RequestContext,
        outcome: IdempotencyOutcome,
        response: Response,
        **fields: object,
    ) -> Response:
        """Record a terminal decision and return its response unchanged."""
        self._record(
            ctx.decision(
                outcome,
                status_code=response.status_code,
                **fields,
            ),
            request_id=ctx.request_id,
        )
        return response

    async def _claim_ownership(
        self,
        redis,
        ctx: _RequestContext,
    ) -> bool | Response:
        """Bind the key to this principal and fingerprint.

        Returns whether a compatible owner already existed, which is the signal
        DOMAIN_REQUIRED uses to refuse a second execution.
        """
        owner = await get_key_owner(redis, self.config.service_name, ctx.idem_key)
        if owner is not None:
            if self._owner_conflicts(owner, ctx.principal_scope, ctx.fingerprint):
                return self._key_reused_response(ctx.request)
            return True

        claimed = await claim_key_owner(
            redis,
            self.config.service_name,
            ctx.idem_key,
            IdempotencyKeyOwner(
                principal_scope=ctx.principal_scope,
                request_fingerprint=ctx.fingerprint,
            ),
            self.config.idempotency_ttl,
        )
        if claimed == ClaimKeyOwnerResult.CONFLICT:
            return self._key_reused_response(ctx.request)
        return claimed == ClaimKeyOwnerResult.EXISTING_COMPATIBLE

    async def _replay_if_cached(
        self,
        redis,
        ctx: _RequestContext,
    ) -> tuple[Response, IdempotencyOutcome] | None:
        """Replay a completed response, or reject a fingerprint mismatch.

        Returns the response paired with its outcome so the caller never has
        to infer the decision from a status code.
        """
        cached = await get_cached_response(
            redis,
            self.config.service_name,
            ctx.principal_scope,
            ctx.idem_key,
        )
        if cached is None:
            return None
        return self._replay_or_reject(cached, ctx.fingerprint, ctx.request)

    async def _retry_after_wait(
        self,
        redis,
        ctx: _RequestContext,
    ) -> str | Response:
        """A duplicate holds the lock. Wait for the original to publish its
        response, and only take the lock if it never does."""
        started = time.perf_counter()
        cached = await wait_for_lock_and_get(
            redis,
            self.config.service_name,
            ctx.principal_scope,
            ctx.idem_key,
            max_wait=self.config.wait_timeout,
        )
        wait_ms = (time.perf_counter() - started) * 1000.0
        if cached is not None:
            response, outcome = self._replay_or_reject(cached, ctx.fingerprint, ctx.request)
            return self._recorded(
                ctx,
                outcome,
                response,
                wait_ms=round(wait_ms, 3),
                replayed=outcome is IdempotencyOutcome.REPLAYED,
            )

        if not await self._owner_still_compatible(redis, ctx):
            return self._recorded(
                ctx,
                IdempotencyOutcome.CONFLICT,
                self._key_reused_response(ctx.request),
                wait_ms=round(wait_ms, 3),
                lock_acquired=False,
            )

        lock = await acquire_lock(
            redis,
            self.config.service_name,
            ctx.principal_scope,
            ctx.idem_key,
            lock_ttl=self.config.lock_ttl,
        )
        if not lock:
            return self._recorded(
                ctx,
                IdempotencyOutcome.IN_FLIGHT,
                self._in_flight_response(ctx.request),
                wait_ms=round(wait_ms, 3),
                lock_acquired=False,
            )
        return await self._settle_after_reacquire(redis, ctx, lock, wait_ms)

    async def _settle_after_reacquire(
        self,
        redis,
        ctx: _RequestContext,
        lock: str,
        wait_ms: float = 0.0,
    ) -> str | Response:
        if not await self._owner_still_compatible(redis, ctx):
            await release_lock(
                redis,
                self.config.service_name,
                ctx.principal_scope,
                ctx.idem_key,
                lock_token=lock,
            )
            return self._recorded(
                ctx,
                IdempotencyOutcome.CONFLICT,
                self._key_reused_response(ctx.request),
                wait_ms=round(wait_ms, 3),
                lock_acquired=False,
            )

        # Holding the lock again does not mean the work is still pending. The
        # previous holder may have finished and cached its response between our
        # last cache read and this acquisition, so read once more before
        # executing (TBD-1).
        cached = await get_cached_response(
            redis,
            self.config.service_name,
            ctx.principal_scope,
            ctx.idem_key,
        )
        if cached is None:
            return lock
        await release_lock(
            redis,
            self.config.service_name,
            ctx.principal_scope,
            ctx.idem_key,
            lock_token=lock,
        )
        response, outcome = self._replay_or_reject(cached, ctx.fingerprint, ctx.request)
        return self._recorded(
            ctx,
            outcome,
            response,
            wait_ms=round(wait_ms, 3),
            replayed=outcome is IdempotencyOutcome.REPLAYED,
            lock_acquired=False,
        )

    async def _owner_still_compatible(
        self,
        redis,
        ctx: _RequestContext,
    ) -> bool:
        owner = await get_key_owner(redis, self.config.service_name, ctx.idem_key)
        if owner is None:
            return False
        return not self._owner_conflicts(
            owner,
            ctx.principal_scope,
            ctx.fingerprint,
        )

    def _replay_or_reject(
        self,
        cached: CachedResponse,
        fingerprint: str,
        request: Request | None = None,
    ) -> tuple[Response, IdempotencyOutcome]:
        if cached.fingerprint != fingerprint:
            return self._key_reused_response(request), IdempotencyOutcome.CONFLICT
        return self._replay_response(cached), IdempotencyOutcome.REPLAYED

    def _in_flight_response(self, request: Request | None = None) -> Response:
        return self._error_response(
            request=request,
            status_code=self.config.inflight_timeout_status_code,
            code="idempotency_request_in_progress",
            message="A request with this Idempotency-Key is still in progress.",
        )

    async def _store_unavailable(
        self,
        ctx: _RequestContext,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        logger.warning(
            "Idempotency store unavailable for %s %s",
            ctx.request.method,
            ctx.request.url.path,
            extra={
                "event": "idempotency.store_unavailable",
                "dependency": "redis",
                "operation": "idempotency",
                "error_code": "dependency.connection_failed",
                "status": "failed" if ctx.key_required else "degraded",
                "request_id": ctx.request_id,
            },
        )
        self._record(
            ctx.decision(
                IdempotencyOutcome.STORE_UNAVAILABLE,
                status_code=503 if ctx.key_required else None,
                error_code=(
                    "idempotency_store_unavailable" if ctx.key_required else None
                ),
            )
        )
        if ctx.key_required:
            return self._error_response(
                request=ctx.request,
                status_code=503,
                code="idempotency_store_unavailable",
                message=(
                    "The idempotency store is temporarily unavailable; "
                    "retry the request with the same Idempotency-Key."
                ),
            )
        return await call_next(ctx.request)

    async def _execute(
        self,
        redis,
        ctx: _RequestContext,
        call_next: RequestResponseEndpoint,
        lock: str,
    ) -> Response:
        renew_task = asyncio.create_task(
            self._renew_lock_loop(
                redis,
                ctx.principal_scope,
                ctx.idem_key,
                lock,
                request_id=ctx.request_id,
            )
        )
        try:
            try:
                response = await call_next(ctx.request)
            except Exception:
                if ctx.policy.rerun_after_failure:
                    await self._free_key_after_failure(redis, ctx)
                raise

            # policy.rerun_after_failure: a run that failed transiently frees its
            # key instead of closing it, so a retry with the same key runs again.
            rerun_allowed = ctx.policy.rerun_after_failure and self._is_transient_status(
                response.status_code
            )
            if rerun_allowed:
                await self._free_key_after_failure(redis, ctx)
            elif response.status_code in _UNAUTHORISED_STATUS_CODES:
                await delete_key_owner(redis, self.config.service_name, ctx.idem_key)

            if self._is_event_stream(response):
                await self._record_completion(
                    redis,
                    ctx,
                    response,
                    cacheable=False,
                    rerun_allowed=rerun_allowed,
                )
                return response

            return await self._finalize(redis, ctx, response, rerun_allowed=rerun_allowed)
        finally:
            await self._stop_renewal(renew_task, ctx.request)
            await self._release_quietly(redis, ctx, lock)

    @staticmethod
    def _is_transient_status(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    async def _free_key_after_failure(self, redis, ctx: _RequestContext) -> None:
        """Let a retry with the same key run again (policy.rerun_after_failure).

        A Redis failure here must not replace the outcome of the request: the
        key then stays as the failed run left it and expires with its TTL.
        """
        try:
            await delete_key_owner(redis, self.config.service_name, ctx.idem_key)
        except redis_exceptions.RedisError:
            logger.warning(
                "Could not free idempotency key after a failed %s %s; "
                "a retry with the same key is refused until it expires.",
                ctx.request.method,
                ctx.request.url.path,
            )

    async def _record_completion(
        self,
        redis,
        ctx: _RequestContext,
        response: Response,
        cacheable: bool,
        rerun_allowed: bool = False,
    ) -> None:
        """Record how a request that held the lock finished.

        A stream cannot be replayed and an uncacheable body must not be
        replayed either, so `domain_required` marks those completed to stop a
        duplicate re-running the side effect -- unless the run failed
        transiently under `rerun_after_failure`, which leaves the key free.
        Every other outcome is an ordinary execution.
        """
        completed_without_replay = (
            ctx.policy.mode == IdempotencyMode.DOMAIN_REQUIRED
            and not cacheable
            and not rerun_allowed
        )
        if completed_without_replay:
            await self._mark_completed_without_replay(
                redis,
                ctx.idem_key,
                ctx.principal_scope,
                ctx.fingerprint,
            )
        self._record(
            ctx.decision(
                (
                    IdempotencyOutcome.COMPLETED_NO_REPLAY
                    if completed_without_replay
                    else IdempotencyOutcome.EXECUTED
                ),
                status_code=response.status_code,
                cacheable=cacheable,
                lock_acquired=True,
                replayed=False,
            ),
            request_id=ctx.request_id,
        )

    async def _finalize(
        self,
        redis,
        ctx: _RequestContext,
        response: Response,
        rerun_allowed: bool = False,
    ) -> Response:
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        cacheable = self._is_cacheable_status(response.status_code, ctx.policy)
        cached_response_written = (
            cacheable and len(body) <= self.config.max_cache_body_size
        )
        if cached_response_written:
            await set_cached_response(
                redis,
                self.config.service_name,
                ctx.principal_scope,
                ctx.idem_key,
                CachedResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    body=base64.b64encode(body).decode("ascii"),
                    created_at=datetime.now(timezone.utc),
                    fingerprint=ctx.fingerprint,
                    principal_scope=ctx.principal_scope,
                    metadata_version=_BODY_CACHE_METADATA_VERSION,
                ),
                self.config.idempotency_ttl,
            )

        await self._record_completion(
            redis,
            ctx,
            response,
            cacheable=cached_response_written,
            rerun_allowed=rerun_allowed,
        )
        return Response(
            content=body,
            status_code=response.status_code,
            media_type=response.media_type,
            headers=dict(response.headers),
        )

    @staticmethod
    def _is_event_stream(response: Response) -> bool:
        return response.headers.get("content-type", "").startswith(
            "text/event-stream"
        )

    async def _stop_renewal(
        self,
        renew_task: asyncio.Task,
        request: Request,
    ) -> None:
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
                extra={
                    "event": "idempotency.lock_renew_failed",
                    "status": "degraded",
                    "error_code": "dependency.connection_failed",
                    "request_id": _resolve_request_id(request.headers),
                },
            )

    async def _release_quietly(
        self,
        redis,
        ctx: _RequestContext,
        lock: str,
    ) -> None:
        # A Redis failure here must not replace an already-computed,
        # successful response with a 500: the request already completed, and
        # the lock will simply expire via its own TTL instead of being
        # released early (spec TS-13).
        try:
            await release_lock(
                redis,
                self.config.service_name,
                ctx.principal_scope,
                ctx.idem_key,
                lock_token=lock,
            )
        except redis_exceptions.RedisError:
            logger.warning(
                "Lock release failed for %s %s; it will expire via its TTL.",
                ctx.request.method,
                ctx.request.url.path,
                extra={
                    "event": "idempotency.lock_release_failed",
                    "status": "degraded",
                    "error_code": "dependency.connection_failed",
                    "request_id": ctx.request_id,
                },
            )
    async def _renew_lock_loop(
        self,
        redis,
        principal_scope: str,
        idem_key: str,
        token: str,
        request_id: str,
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
                "Could not renew idempotency lock for key=%s", idem_key,
                extra={
                    "event": "idempotency.lock_renew_gave_up",
                    "status": "degraded",
                    "error_code": "dependency.connection_failed",
                    "request_id": request_id,
                },
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

    async def _principal_scope(self, request: Request) -> str:
        if self.config.principal_extractor is not None:
            try:
                identity = await self.config.principal_extractor(request)
            except Exception:
                logger.warning(
                    "principal_extractor failed for %s %s; falling back to anonymous",
                    request.method,
                    request.url.path,
                    extra={
                        "event": "idempotency.principal_extractor_failed",
                        "status": "degraded",
                        "error_code": "idempotency_principal_extractor_failed",
                        "request_id": _resolve_request_id(request.headers),
                    },
                )
                identity = None
            if identity:
                digest = hashlib.sha256(identity.encode()).hexdigest()
                return f"user:{digest}"
            return "anonymous"

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
        if self._is_transient_status(status_code):
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
    def _error_response(
        status_code: int, code: str, message: str, *, request: Request | None = None
    ) -> Response:
        locale = normalize_locale(
            (
                request.query_params.get("lang")
                or request.query_params.get("locale")
                or request.headers.get("x-language")
                or request.headers.get("accept-language")
                or "en"
            )
            if request is not None
            else "en"
        )
        error = _IDEMPOTENCY_ERRORS[code](status_code=status_code)
        message = render_error_message(error, locale=locale)
        request_id = (
            request.headers.get("x-request-id") or request.headers.get("x-correlation-id")
            if request is not None
            else None
        )
        return Response(
            content=json.dumps(
                {
                    "error": {
                        "code": code,
                        "message": message,
                        "details": {},
                        "field_errors": [],
                        "request_id": request_id,
                    }
                }
            ),
            status_code=status_code,
            media_type="application/json",
            headers={"Cache-Control": "no-store", "Content-Language": locale},
        )

    @classmethod
    def _key_reused_response(cls, request: Request | None = None) -> Response:
        return cls._error_response(
            request=request,
            status_code=409,
            code="idempotency_key_reused",
            message=(
                "Idempotency-Key was already used for a different request or "
                "principal."
            ),
        )
