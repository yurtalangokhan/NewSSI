"""The CORS origin/credential safety rule.

One rule, enforced at startup: wildcard origins cannot be combined with
credentialed requests. A browser will then attach cookies to a request from any
origin and hand the response to whoever asked, which turns a permissive
CORS config into a credentialed cross-origin read.

Reading and normalising the configured origin list is a *configuration*
concern, not a security one, and lives in ``config_manager.parse_allowed_origins``
— which is also what the accessor itself calls. A service validates at startup::

    from config_manager import parse_allowed_origins
    from security import validate_cors_policy

    origins = parse_allowed_origins(env.ALLOW_ORIGINS)
    validate_cors_policy(origins=origins, allow_credentials=True)
"""

from __future__ import annotations


def validate_cors_policy(*, origins: list[str], allow_credentials: bool) -> None:
    """Reject an origin/credential combination that would leak authenticated reads."""
    if allow_credentials and "*" in origins:
        raise ValueError("CORS allow_origins='*' cannot be combined with allow_credentials=True")


__all__ = ["validate_cors_policy"]
