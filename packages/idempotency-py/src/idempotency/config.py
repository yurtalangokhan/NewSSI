from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from idempotency.models import IdempotencyPolicyConfig

if TYPE_CHECKING:
    from fastapi import Request


@dataclass
class IdempotencyConfig:
    redis_host: str
    redis_port: int
    redis_db: int
    redis_password: str
    idempotency_ttl: int = 86_400
    idempotency_enabled: bool = True
    service_name: str = "unknown"
    enforce_required_keys: bool = True
    lock_ttl: int = 10
    wait_timeout: float = 10.0
    inflight_timeout_status_code: int = 409
    max_idempotency_key_length: int = 255
    max_cache_body_size: int = 1_048_576
    cacheable_status_codes: set[int] | None = None
    cacheable_status_ranges: list[tuple[int, int]] = field(
        default_factory=lambda: [(200, 299)]
    )
    principal_header_candidates: tuple[str, ...] = (
        "X-User-Id",
        "X-Authenticated-User-Id",
        "X-Internal-Service-Token",
    )
    policy: IdempotencyPolicyConfig = field(default_factory=IdempotencyPolicyConfig)
    principal_extractor: Callable[[Request], Awaitable[str | None]] | None = None
