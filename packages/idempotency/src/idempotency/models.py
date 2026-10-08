import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class IdempotencyMode(StrEnum):
    EXCLUDED = "excluded"
    OPTIONAL_REPLAY = "optional_replay"
    REQUIRED_REPLAY = "required_replay"
    DOMAIN_REQUIRED = "domain_required"


class IdempotencyPolicy(BaseModel):
    method: str
    path: str
    mode: IdempotencyMode
    cache_deterministic_client_errors: bool = False
    # Tri-state missing-key override:
    #   None (default) -> fall back to the global enforce_required_keys flag
    #   True           -> always require a key for this route
    #   False          -> never require a key for this route (explicit override)
    enforce_missing_key: bool | None = None
    # For a route whose handler may safely run again for the same request:
    # a run that ended in 429 / 5xx, or raised, frees the key instead of
    # leaving it closed or "in progress", so a retry with the same key runs
    # again. A run that succeeded is still replayed, and a run still in
    # flight still refuses the key.
    rerun_after_failure: bool = False

    def matches(self, method: str, path: str) -> bool:
        if self.method.upper() != method.upper():
            return False
        normalized_policy_path = self.path.rstrip("/") or "/"
        normalized_path = path.rstrip("/") or "/"
        if normalized_policy_path == normalized_path:
            return True
        pattern = re.escape(normalized_policy_path)
        pattern = re.sub(r"\\\{[^/{}:]+:path\\\}", r".+", pattern)
        pattern = re.sub(r"\\\{[^/{}]+\\\}", r"[^/]+", pattern)
        return re.fullmatch(pattern, normalized_path) is not None


class IdempotencyPolicyConfig(BaseModel):
    default_mode: IdempotencyMode = IdempotencyMode.OPTIONAL_REPLAY
    route_policies: list[IdempotencyPolicy] = Field(default_factory=list)

    def match(self, method: str, path: str) -> IdempotencyPolicy | None:
        for policy in self.route_policies:
            if policy.matches(method, path):
                return policy
        return None

    def resolve(self, method: str, path: str) -> IdempotencyPolicy:
        matched = self.match(method, path)
        if matched is not None:
            return matched
        return IdempotencyPolicy(method=method.upper(), path=path, mode=self.default_mode)


class CachedResponse(BaseModel):
    status_code: int
    headers: dict[str, str]
    body: str
    created_at: datetime
    fingerprint: str | None = None
    principal_scope: str = "anonymous"
    # Version 1 stored the raw UTF-8 body text. Version 2 stores the body as
    # base64 (ASCII) so binary/non-UTF-8 responses round-trip losslessly.
    metadata_version: int = 1


class IdempotencyKeyOwner(BaseModel):
    principal_scope: str
    request_fingerprint: str | None = None
    completed_without_replay: bool = False


class IdempotencyOutcome(StrEnum):
    BYPASSED = "bypassed"
    KEY_MISSING = "key_missing"
    KEY_INVALID = "key_invalid"
    KEY_REQUIRED = "key_required"
    REPLAYED = "replayed"
    EXECUTED = "executed"
    COMPLETED_NO_REPLAY = "completed_no_replay"
    CONFLICT = "conflict"
    IN_FLIGHT = "in_flight"
    STORE_UNAVAILABLE = "store_unavailable"


class IdempotencyDecision(BaseModel):
    outcome: IdempotencyOutcome
    route_template: str | None = None
    status_code: int | None = None
    cacheable: bool | None = None
    lock_acquired: bool | None = None
    replayed: bool | None = None
    wait_ms: float | None = None
    error_code: str | None = None
