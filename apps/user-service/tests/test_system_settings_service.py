from unittest.mock import AsyncMock, Mock

import pytest

from src.schema.system_settings import KeycloakConfigUpdate
from src.service.system_settings_service import SystemSettingsService


def _mock_repo(value=None):
    repo = Mock()
    repo.get_value = AsyncMock(return_value=value or {})
    repo.set_value = AsyncMock(side_effect=lambda _key, saved: saved)
    return repo


def _mock_keycloak():
    keycloak = Mock()
    keycloak.is_enabled.return_value = True
    keycloak.get_realm.return_value = "agenticai"
    keycloak.get_base_url.return_value = "http://keycloak:8080"
    keycloak.get_issuer_url.return_value = "http://keycloak:8080/realms/agenticai"
    keycloak.has_admin_access.return_value = True
    keycloak.get_client_id.return_value = "agenticai-web"
    keycloak.get_login_client_id.return_value = "agenticai-web"
    keycloak.get_client_secret.return_value = None
    keycloak.set_runtime_settings = Mock()
    keycloak.is_external_keycloak.return_value = True
    keycloak.get_external_keycloak_alias.return_value = "external-keycloak"
    keycloak.get_external_issuer_url.return_value = "https://sso.example.com/realms/external"
    keycloak.get_realm_configuration = AsyncMock(
        return_value={
            "accessTokenLifespan": 300,
            "ssoSessionIdleTimeout": 1800,
            "ssoSessionMaxLifespan": 36000,
        }
    )
    keycloak.get_external_identity_provider_status = AsyncMock(
        return_value={
            "enabled": True,
            "alias": "external-keycloak",
            "exists": True,
            "reachable": True,
            "provider": {"enabled": True},
            "mapper": {"exists": True, "name": "assign-enduser-role", "role": "enduser"},
        }
    )
    return keycloak


@pytest.mark.asyncio
async def test_keycloak_settings_masks_external_client_secret(monkeypatch):
    monkeypatch.setenv("EXTERNAL_KEYCLOAK", "true")
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_DISPLAY_NAME", "External SSO")
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_CLIENT_ID", "external-client")
    monkeypatch.setenv("EXTERNAL_KEYCLOAK_CLIENT_SECRET", "very-secret")

    service = SystemSettingsService()
    service.repo = _mock_repo()
    service.keycloak = _mock_keycloak()

    settings = await service.get_keycloak_settings()

    external = settings["external_keycloak"]
    assert external["client_secret_configured"] is True
    assert "client_secret" not in external
    assert external["identity_provider"]["exists"] is True


@pytest.mark.asyncio
async def test_update_keycloak_settings_persists_and_applies_runtime_settings():
    service = SystemSettingsService()
    service.repo = _mock_repo()
    service.keycloak = _mock_keycloak()

    await service.update_keycloak_settings(
        KeycloakConfigUpdate(
            keycloak_enabled=True,
            keycloak_base_url="http://keycloak:8080",
            external_keycloak=True,
            external_keycloak_client_secret="very-secret",
        )
    )

    saved = service.repo.set_value.await_args.args[1]
    assert saved["KEYCLOAK_ENABLED"] is True
    assert saved["KEYCLOAK_BASE_URL"] == "http://keycloak:8080"
    assert "EXTERNAL_KEYCLOAK_CLIENT_SECRET" not in saved
    assert "EXTERNAL_KEYCLOAK_CLIENT_SECRET_ENCRYPTED" in saved
    service.keycloak.set_runtime_settings.assert_called()
