"""Pure helper functions for Keycloak service configuration handling.

These are stateless string/URL/list helpers used by ``KeycloakService``. They
are extracted into their own module to keep the service focused on Keycloak
orchestration and to make the pure logic independently testable.
"""

import fnmatch
from typing import Any
from urllib.parse import urlparse


def csv_values(raw: str | None) -> list[str]:
    return [value.strip() for value in (raw or "").split(",") if value.strip()]


def merge_unique_values(existing: list[Any], configured: list[str]) -> list[str]:
    merged: list[str] = []
    for value in [*existing, *configured]:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if item and item not in merged:
            merged.append(item)
    return merged


def value_matches_pattern(value: str, patterns: list[str]) -> bool:
    return any(pattern in ("*", "+") or fnmatch.fnmatchcase(value, pattern) for pattern in patterns)


def origin_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def post_logout_redirect_values(raw: Any) -> list[str]:
    values = raw if isinstance(raw, list) else str(raw or "").split("##")
    return [value.strip() for value in values if isinstance(value, str) and value.strip()]


def merge_post_logout_redirect_uris(existing: Any, configured: str) -> str:
    return "##".join(
        merge_unique_values(
            post_logout_redirect_values(existing),
            post_logout_redirect_values(configured),
        )
    )
