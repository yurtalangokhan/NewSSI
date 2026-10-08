"""Authentication headers and the user's time zone, shared by the Atlassian sources
(Confluence, Jira).

Cloud sites use HTTP basic auth with ``e-mail : API token``; Data Center uses a
personal access token as a bearer token.

JQL and CQL read date literals in the *API user's profile time zone*, not in UTC:
a cursor rendered in UTC for a user west of Greenwich skips what changed in the
last hours, east of it the same records come back every run. The sources ask the
profile endpoint once per run and render the literal in that zone.
"""

from __future__ import annotations

import logging
from datetime import UTC, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .rest_source import RestSource, basic_auth_header

logger = logging.getLogger("connector.atlassian")


def atlassian_auth_headers(auth_type: str, email: str | None, token: str | None) -> dict[str, str]:
    if not token:
        return {}
    if auth_type == "bearer":
        return {"Authorization": f"Bearer {token}"}
    return basic_auth_header(email or "", token)


def zone_or_utc(name: str | None) -> tzinfo:
    """The IANA zone ``name``, UTC when it is empty or unknown."""
    if not name:
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("unknown time zone %r; rendering query dates in UTC", name)
        return UTC


async def user_time_zone(
    source: RestSource[Any], profile_path: str, configured: str | None
) -> tzinfo:
    """The zone to render query date literals in: ``configured`` when set, else the
    ``timeZone`` of the API user's profile, else UTC. A profile that cannot be read
    (a token without that scope) is not an error: the query is rendered in UTC."""
    if configured:
        return zone_or_utc(configured)
    try:
        profile = await source.get_json(profile_path)
    except Exception as exc:  # noqa: BLE001 - the profile is optional
        logger.warning("could not read the API user's profile (%s); using UTC", type(exc).__name__)
        return UTC
    name = profile.get("timeZone") if isinstance(profile, dict) else None
    return zone_or_utc(name)
