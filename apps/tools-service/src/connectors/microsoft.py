"""Bounded read-only Microsoft Graph access for saved Airbyte sources."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Mapping
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx
from wcmatch import glob

_GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
_LOGIN_ROOT = "https://login.microsoftonline.com"
_TIMEOUT_SECONDS = 10.0
_MAX_LIMIT = 100
_MAX_CONTENT_BYTES = 65_536
_TENANT = re.compile(r"^[A-Za-z0-9.-]+$")


class MicrosoftConnectorError(Exception):
    """Safe Microsoft adapter error that contains no saved credentials."""


def _required(config: Mapping[str, Any], key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MicrosoftConnectorError("Microsoft connector configuration is incomplete.")
    return value.strip()


def _limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MicrosoftConnectorError("Limit must be an integer.")
    return min(max(value, 1), _MAX_LIMIT)


def _sharepoint_site(config: Mapping[str, Any]) -> str:
    if config.get("search_scope", "ALL") != "ACCESSIBLE_DRIVES":
        raise MicrosoftConnectorError("SharePoint search scope is not supported.")
    site_url = str(config.get("site_url") or "").strip()
    if not site_url:
        return f"{_GRAPH_ROOT}/sites/root"
    parsed = urlsplit(site_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".sharepoint.com")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
        or not path.startswith("/sites/")
        or len(path) <= len("/sites/")
        or ".." in PurePosixPath(path).parts
    ):
        raise MicrosoftConnectorError("SharePoint site URL is not supported.")
    return f"{_GRAPH_ROOT}/sites/{hostname}:{quote(path, safe='/')}"


def _sharepoint_stream(config: Mapping[str, Any], resource: str) -> list[str]:
    for stream in config.get("streams") or []:
        if isinstance(stream, Mapping) and stream.get("name") == resource:
            globs = stream.get("globs")
            if isinstance(globs, str):
                globs = globs.split("|")
            if (
                isinstance(globs, list)
                and globs
                and all(
                    isinstance(item, str)
                    and item
                    and not item.startswith("/")
                    and ".." not in item.split("/")
                    for item in globs
                )
            ):
                return globs
    raise MicrosoftConnectorError("SharePoint stream is not configured.")


def _matches(path: str, globs: list[str]) -> bool:
    return any(glob.globmatch(path, pattern, flags=glob.GLOBSTAR | glob.SPLIT) for pattern in globs)


def _relative_path(value: str) -> str:
    if not value or value.startswith("/") or "\\" in value:
        raise MicrosoftConnectorError("SharePoint file path is invalid.")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise MicrosoftConnectorError("SharePoint file path is invalid.")
    return value


async def _access_token(
    client: httpx.AsyncClient,
    credentials: Mapping[str, Any],
    *,
    delegated_scope: str = "https://graph.microsoft.com/.default offline_access",
) -> str:
    tenant_id = str(credentials.get("tenant_id") or "common").strip()
    if not _TENANT.fullmatch(tenant_id):
        raise MicrosoftConnectorError("Microsoft tenant ID is invalid.")
    client_id = _required(credentials, "client_id")
    client_secret = _required(credentials, "client_secret")
    auth_type = credentials.get("auth_type")
    if auth_type in {None, "Client"} and credentials.get("refresh_token"):
        data = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": _required(credentials, "refresh_token"),
            "scope": delegated_scope,
        }
    elif auth_type in {"Client", "Service"}:
        data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }
    else:
        raise MicrosoftConnectorError("Microsoft authentication variant is not supported.")
    try:
        response = await client.post(
            f"{_LOGIN_ROOT}/{tenant_id}/oauth2/v2.0/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return _required(response.json(), "access_token")
    except MicrosoftConnectorError:
        raise
    except Exception:
        raise MicrosoftConnectorError("Microsoft authentication failed.") from None


async def _graph_json(
    client: httpx.AsyncClient,
    url: str,
    token: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError
        return payload
    except Exception:
        raise MicrosoftConnectorError("Microsoft Graph read failed.") from None


def _graph_url(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "graph.microsoft.com"
        and parsed.path.startswith("/v1.0/")
        and not parsed.fragment
    )


async def _download(client: httpx.AsyncClient, url: str, token: str) -> tuple[bytes, bool]:
    for _ in range(5):
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or parsed.port not in {None, 443}
            or parsed.username
            or parsed.password
            or not (host == "graph.microsoft.com" or host.endswith(".sharepoint.com"))
        ):
            raise MicrosoftConnectorError("SharePoint download origin is not supported.")
        headers = {"Range": f"bytes=0-{_MAX_CONTENT_BYTES}"}
        if host == "graph.microsoft.com":
            headers["Authorization"] = f"Bearer {token}"
        async with client.stream("GET", url, headers=headers) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise MicrosoftConnectorError("SharePoint redirect is invalid.")
                url = urljoin(url, location)
                continue
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk[: _MAX_CONTENT_BYTES + 1 - len(content)])
                if len(content) > _MAX_CONTENT_BYTES:
                    break
            return bytes(content[:_MAX_CONTENT_BYTES]), len(content) > _MAX_CONTENT_BYTES
    raise MicrosoftConnectorError("SharePoint download redirect limit exceeded.")


async def _sharepoint(
    client: httpx.AsyncClient,
    config: Mapping[str, Any],
    resource: str,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    site_url = _sharepoint_site(config)
    globs = _sharepoint_stream(config, resource)
    folder = str(config.get("folder_path") or "").strip("/")
    folder = "" if folder == "." else folder
    if folder:
        _relative_path(folder)
    selector = None
    if query:
        try:
            selector = json.loads(query)
            if not isinstance(selector, dict) or set(selector) != {"drive_id", "path"}:
                raise ValueError
            path = _relative_path(_required(selector, "path"))
            if not _matches(path, globs):
                raise ValueError
            _required(selector, "drive_id")
        except (ValueError, TypeError):
            raise MicrosoftConnectorError(
                "SharePoint query requires an allowed drive_id and path."
            ) from None
    token = await _access_token(client, config.get("credentials") or {})
    site = await _graph_json(client, site_url, token)
    site_id = _required(site, "id")
    drives_payload = await _graph_json(
        client,
        f"{_GRAPH_ROOT}/sites/{quote(site_id, safe=',')}/drives",
        token,
        params={"$top": 10},
    )
    drives = list(drives_payload.get("value") or [])[:10]
    if selector:
        drive_id = _required(selector, "drive_id")
        if drive_id not in {_required(drive, "id") for drive in drives}:
            raise MicrosoftConnectorError("SharePoint drive is not assigned to this site.")
        path = _required(selector, "path")
        full_path = "/".join(part for part in (folder, path) if part)
        url = (
            f"{_GRAPH_ROOT}/drives/{quote(drive_id, safe='')}/root:"
            f"/{quote(full_path, safe='/')}:/content"
        )
        content, truncated = await _download(client, url, token)
        return [
            {
                "name": PurePosixPath(path).name,
                "path": path,
                "drive_id": drive_id,
                "content": content.decode("utf-8", errors="replace"),
                "content_truncated": truncated,
            }
        ]

    rows: list[dict[str, Any]] = []
    pending = []
    for drive in drives:
        drive_id = _required(drive, "id")
        suffix = f"/root:/{quote(folder, safe='/')}:/children" if folder else "/root/children"
        pending.append((f"{_GRAPH_ROOT}/drives/{quote(drive_id, safe='')}{suffix}", drive, "", 0))
    visited: set[str] = set()
    while pending and len(visited) < 40 and len(rows) < _limit(limit):
        url, drive, parent, depth = pending.pop(0)
        if url in visited:
            continue
        if not _graph_url(url):
            raise MicrosoftConnectorError("SharePoint pagination origin is invalid.")
        visited.add(url)
        payload = await _graph_json(
            client, url, token, params=None if "?" in url else {"$top": 100}
        )
        for item in (payload.get("value") or [])[:100]:
            name = str(item.get("name") or "")
            if not name or "/" in name or "\\" in name or name in {".", ".."}:
                continue
            path = "/".join(part for part in (parent, name) if part)
            if "folder" in item:
                if depth < 8 and len(pending) < 100:
                    full = "/".join(part for part in (folder, path) if part)
                    child_url = (
                        f"{_GRAPH_ROOT}/drives/{quote(_required(drive, 'id'), safe='')}"
                        f"/root:/{quote(full, safe='/')}:/children"
                    )
                    pending.append((child_url, drive, path, depth + 1))
            elif _matches(path, globs):
                rows.append(
                    {
                        "id": item.get("id"),
                        "name": name,
                        "path": path,
                        "size": item.get("size"),
                        "drive_id": drive["id"],
                        "drive_name": drive.get("name"),
                    }
                )
                if len(rows) >= _limit(limit):
                    break
        next_url = payload.get("@odata.nextLink")
        if next_url and len(pending) < 100:
            if not isinstance(next_url, str) or not _graph_url(next_url):
                raise MicrosoftConnectorError("SharePoint pagination origin is invalid.")
            pending.append((next_url, drive, parent, depth))
    return rows


async def _outlook(
    client: httpx.AsyncClient,
    config: Mapping[str, Any],
    resource: str,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    token = await _access_token(
        client,
        config,
        delegated_scope=(
            "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/User.Read"
        ),
    )
    endpoints = {
        "profile": "/me",
        "mailboxes": "/me/mailFolders",
        "messages": "/me/messages",
        "conversations": "/me/messages",
    }
    if resource == "messages_details":
        if not query or "/" in query:
            raise MicrosoftConnectorError("Outlook message ID is required.")
        endpoint = f"/me/messages/{quote(query, safe='')}"
    else:
        endpoint = endpoints.get(resource)
        if endpoint is None or query:
            raise MicrosoftConnectorError("Outlook stream or query is not supported.")
    params = None if resource in {"profile", "messages_details"} else {"$top": _limit(limit)}
    payload = await _graph_json(client, f"{_GRAPH_ROOT}{endpoint}", token, params=params)
    if resource in {"profile", "messages_details"}:
        return [payload]
    return [item for item in payload.get("value") or [] if isinstance(item, dict)][: _limit(limit)]


async def read_microsoft_connector(
    connector_type: str,
    config: Mapping[str, Any],
    resource: str,
    *,
    query: str,
    limit: int,
    client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
) -> list[dict[str, Any]]:
    """Read one saved SharePoint or Outlook stream through fixed Microsoft origins."""
    try:
        async with (
            asyncio.timeout(25),
            client_factory(timeout=_TIMEOUT_SECONDS, follow_redirects=False) as client,
        ):
            if connector_type == "source-microsoft-sharepoint":
                return await _sharepoint(client, config, resource, query, limit)
            if connector_type == "source-outlook":
                return await _outlook(client, config, resource, query, limit)
            raise MicrosoftConnectorError("Microsoft connector type is not supported.")
    except MicrosoftConnectorError:
        raise
    except Exception:
        raise MicrosoftConnectorError("Microsoft connector read failed.") from None
