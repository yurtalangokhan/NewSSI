"""Safe exception and field values for logs, readiness payloads, and operators.

The redaction patterns and the transient/hint/error-code/remediation
classification are the platform field contract: every service emits the same
keys for the same failure, so dashboards and alerts do not need per-service
mappings.

Redaction lives here rather than at call sites because a call site that forgets
to sanitize is the exact failure this removes. The formatter masks on every
record, in both output formats, with no production switch.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_REDACTION_PATTERNS = (
    re.compile(r"://([^:/\s]+):([^@\s]+)@"),
    re.compile(r"(?i)\b(password|token|secret|api_key|apikey)=([^&\s]+)"),
)

# Matched against the *key name*, case-insensitively and ignoring separators, so
# `apiKey`, `api_key`, `API-KEY` and `x-api-key` all mask. `authorization` and
# `cookie` are here because a request header is the most common accidental leak.
SENSITIVE_KEY_PARTS = frozenset(
    {
        "apikey",
        "authorization",
        "cookie",
        "credential",
        "passphrase",
        "password",
        "privatekey",
        "pwd",
        "refreshtoken",
        "secret",
        "sessionid",
        "token",
    }
)

_MASK = "[redacted]"


def is_sensitive_key(key: str) -> bool:
    """Whether a field name is one whose value must never reach a destination.

    The comparison strips separators and lowercases the name, so a deny-list
    entry matches the spellings a caller is likely to use.
    """
    normalised = re.sub(r"[^a-z0-9]", "", key.casefold())
    return any(part in normalised for part in SENSITIVE_KEY_PARTS)


def mask_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Return *fields* with every sensitive value replaced by a mask.

    Non-sensitive values pass through untouched, so this is safe to call on the
    whole record payload rather than on a hand-picked subset. A masked field
    still appears in the record, which keeps the field's presence queryable
    without carrying its value.
    """
    return {key: (_MASK if is_sensitive_key(key) else value) for key, value in fields.items()}


def sanitize_text(text: str) -> str:
    """Redact credentials embedded in free text, such as a connection string."""
    for pattern in _REDACTION_PATTERNS:
        if pattern.pattern.startswith("://"):
            text = pattern.sub(r"://\1:[redacted]@", text)
        else:
            text = pattern.sub(lambda match: f"{match.group(1)}=[redacted]", text)
    return text


def sanitize_exception(exc: BaseException | None) -> dict[str, str | bool | None]:
    """Return safe exception fields for logs and readiness details."""

    if exc is None:
        return {
            "exception_type": None,
            "exception_message": None,
            "retryable": False,
            "hint": None,
        }

    return {
        "exception_type": exc.__class__.__name__,
        "exception_message": sanitize_text(str(exc)),
        "retryable": is_retryable_exception(exc),
        "hint": hint_for_exception(exc),
    }


def dependency_error_fields(exc: BaseException, *, dependency: str) -> dict[str, str | bool]:
    """Return operator-facing dependency error fields without Python internals."""

    return {
        "error_code": error_code_for_exception(exc),
        "error_summary": f"{dependency} is unavailable.",
        "remediation": remediation_for_exception(exc),
        "retryable": is_retryable_exception(exc),
    }


def is_retryable_exception(exc: BaseException) -> bool:
    """Whether a startup retry should attempt this exception again."""
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


def hint_for_exception(exc: BaseException) -> str | None:
    """Operator hint for the most common startup failure shapes."""
    if isinstance(exc, ConnectionError):
        return "Check that the dependency host and port are reachable."
    if isinstance(exc, TimeoutError):
        return "Check dependency readiness and network latency."
    return None


def error_code_for_exception(exc: BaseException) -> str:
    """Stable error code for the exception, for alerts and dashboards."""
    if isinstance(exc, ConnectionError):
        return "dependency.connection_failed"
    if isinstance(exc, TimeoutError):
        return "dependency.timeout"
    return "dependency.unavailable"


def remediation_for_exception(exc: BaseException) -> str:
    """What the operator should check first for this exception."""
    if isinstance(exc, TimeoutError):
        return "Check that the dependency is healthy and responds within the startup timeout."
    return "Check that the dependency is running and reachable from the service."
