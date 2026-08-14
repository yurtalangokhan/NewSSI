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
    enforce_missing_key: bool = False

    def matches(self, method: str, path: str) -> bool:
        if self.method.upper() != method.upper():
            return False
        if self.path == path:
            return True
        pattern = re.sub(r"\{[^/]+\}", r"[^/]+", self.path)
        return re.fullmatch(pattern, path) is not None


class IdempotencyPolicyConfig(BaseModel):
    default_mode: IdempotencyMode = IdempotencyMode.OPTIONAL_REPLAY
    route_policies: list[IdempotencyPolicy] = Field(default_factory=list)

    def resolve(self, method: str, path: str) -> IdempotencyPolicy:
        for policy in self.route_policies:
            if policy.matches(method, path):
                return policy
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
