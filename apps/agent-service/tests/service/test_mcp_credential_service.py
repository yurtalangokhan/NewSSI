"""Unit tests for MCPCredentialService (plan task 3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch):
    """Give the encryption module a real, disposable Fernet key per test."""
    from cryptography.fernet import Fernet

    import core.security.encryption as enc

    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    enc._fernet = None
    yield
    enc._fernet = None


def _service(auth_repo):
    from service.MCPCredentialService import MCPCredentialService

    return MCPCredentialService(auth_repo=auth_repo)


@pytest.mark.asyncio
async def test_store_and_get_user_credentials_roundtrip():
    store: dict = {}
    repo = AsyncMock()
    repo.upsert.side_effect = lambda pid, uid, **f: store.update(f) or dict(store)
    repo.get.side_effect = lambda pid, uid: dict(store) if store else None
    svc = _service(repo)

    await svc.store_user_credentials("p1", "u1", {"api_key": "SECRET-VALUE"})

    assert store["credentials_encrypted"] != "SECRET-VALUE"
    assert await svc.get_credentials("p1", "u1") == {"api_key": "SECRET-VALUE"}


@pytest.mark.asyncio
async def test_resolve_headers_none_auth_returns_empty():
    svc = _service(AsyncMock())
    assert await svc.resolve_headers({"auth_type": "NONE"}, user_id="u1") == {}


@pytest.mark.asyncio
async def test_resolve_headers_admin_api_token_is_bearer():
    repo = AsyncMock()
    svc = _service(repo)
    svc.get_credentials = AsyncMock(return_value={"api_key": "K"})

    headers = await svc.resolve_headers(
        {"id": "p1", "auth_type": "API_TOKEN", "auth_performer": "ADMIN"}, user_id="u1"
    )

    assert headers == {"Authorization": "Bearer K"}


@pytest.mark.asyncio
async def test_resolve_headers_per_user_template_missing_field_raises():
    from service.MCPCredentialService import MCPAuthError

    svc = _service(AsyncMock())
    svc.get_credentials = AsyncMock(return_value={})
    provider = {
        "id": "p1",
        "auth_type": "API_TOKEN",
        "auth_performer": "PER_USER",
        "auth_template": {
            "headers": {"X-Api-Key": "{api_key}"},
            "required_fields": ["api_key"],
        },
    }

    with pytest.raises(MCPAuthError) as ei:
        await svc.resolve_headers(provider, user_id="u1")
    assert "credentials" in str(ei.value)


@pytest.mark.asyncio
async def test_resolve_headers_per_user_template_applies_substitution():
    svc = _service(AsyncMock())
    svc.get_credentials = AsyncMock(return_value={"api_key": "abc123"})
    provider = {
        "id": "p1",
        "auth_type": "API_TOKEN",
        "auth_performer": "PER_USER",
        "auth_template": {
            "headers": {"Authorization": "Bearer {api_key}"},
            "required_fields": ["api_key"],
        },
    }

    headers = await svc.resolve_headers(provider, user_id="u1")
    assert headers == {"Authorization": "Bearer abc123"}


@pytest.mark.asyncio
async def test_resolve_headers_oauth_refreshes_when_expiring(monkeypatch):
    svc = _service(AsyncMock())
    svc.get_oauth_tokens = AsyncMock(
        return_value={
            "access_token": "old-token",
            "refresh_token": "refresh-1",
            "expires_at": datetime.now(UTC) - timedelta(seconds=5),
        }
    )
    svc.store_oauth_tokens = AsyncMock()
    refreshed = {}

    async def fake_refresh(provider_row, user_id, refresh_token):
        refreshed["called"] = refresh_token
        return ("new-token", "refresh-2", datetime.now(UTC) + timedelta(hours=1), ["s"])

    svc._refresh_oauth_token = fake_refresh
    provider = {
        "id": "p1",
        "auth_type": "OAUTH",
        "auth_performer": "PER_USER",
        "oauth_metadata": {"token_endpoint": "https://as.example/token"},
    }

    headers = await svc.resolve_headers(provider, user_id="u1")

    assert refreshed["called"] == "refresh-1"
    assert headers == {"Authorization": "Bearer new-token"}
    svc.store_oauth_tokens.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_headers_oauth_without_tokens_raises():
    from service.MCPCredentialService import MCPAuthError

    svc = _service(AsyncMock())
    svc.get_oauth_tokens = AsyncMock(return_value=None)
    provider = {"id": "p1", "auth_type": "OAUTH", "auth_performer": "PER_USER"}

    with pytest.raises(MCPAuthError) as ei:
        await svc.resolve_headers(provider, user_id="u1")
    assert "oauth" in str(ei.value)


def test_masked_credentials_keeps_client_id_visible():
    svc = _service(AsyncMock())
    masked = svc.masked_credentials({"client_id": "public-id", "client_secret": "supersecret"})
    assert masked["client_id"] == "public-id"
    assert masked["client_secret"].endswith("cret")
    assert masked["client_secret"] != "supersecret"
