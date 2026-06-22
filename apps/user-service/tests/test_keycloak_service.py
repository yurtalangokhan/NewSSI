from src.service import keycloak_service
from src.service.keycloak_service import KeycloakService


def test_client_credentials_payload_omits_empty_secret(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "test-client")
    monkeypatch.delenv("KEYCLOAK_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(keycloak_service._settings, "KEYCLOAK_CLIENT_SECRET", None)

    payload = KeycloakService()._client_credentials_payload()

    assert payload == {"client_id": "test-client"}


def test_client_credentials_payload_includes_secret(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "test-client")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "  test-secret  ")

    payload = KeycloakService()._client_credentials_payload()

    assert payload == {
        "client_id": "test-client",
        "client_secret": "test-secret",
    }
