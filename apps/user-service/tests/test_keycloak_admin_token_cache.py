"""Admin token refresh margins must accommodate short Keycloak token lifetimes."""

import pytest

from src.service.keycloak_service import KeycloakService


async def test_sixty_second_token_is_reused_until_refresh_margin(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("src.service.keycloak_service.time.time", lambda: now[0])
    service = KeycloakService()
    service._cache_admin_token("service-account", {"access_token": "test", "expires_in": 60})
    assert await service._get_cached_admin_token("service-account") == "test"
    now[0] += 53
    assert await service._get_cached_admin_token("service-account") == "test"
    assert await service._get_cached_admin_token("password-admin") is None
    now[0] += 1
    assert await service._get_cached_admin_token("service-account") is None


@pytest.mark.parametrize("lifetime", [0, -1, None, "invalid", float("nan"), float("inf")])
async def test_invalid_or_expired_token_lifetime_is_never_reused(lifetime):
    service = KeycloakService()
    service._cache_admin_token("service-account", {"access_token": "test", "expires_in": lifetime})
    assert await service._get_cached_admin_token("service-account") is None


async def test_long_lifetime_refresh_margin_is_capped_at_sixty_seconds(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("src.service.keycloak_service.time.time", lambda: now[0])
    service = KeycloakService()
    service._cache_admin_token("service-account", {"access_token": "test", "expires_in": 3600})
    now[0] += 3539
    assert await service._get_cached_admin_token("service-account") == "test"
    now[0] += 1
    assert await service._get_cached_admin_token("service-account") is None


async def test_runtime_change_invalidates_tokens_on_existing_instances(monkeypatch):
    monkeypatch.setattr(KeycloakService, "_runtime_settings", {})
    first, second = KeycloakService(), KeycloakService()
    for service in (first, second):
        service._cache_admin_token("service-account", {"access_token": "before", "expires_in": 60})
        assert await service._get_cached_admin_token("service-account") == "before"
    KeycloakService.set_runtime_settings({"KEYCLOAK_REALM": "changed-realm"})
    for service in (first, second):
        assert await service._get_cached_admin_token("service-account") is None
    first._cache_admin_token("service-account", {"access_token": "after", "expires_in": 60})
    assert await first._get_cached_admin_token("service-account") == "after"
    assert await second._get_cached_admin_token("service-account") == "after"
