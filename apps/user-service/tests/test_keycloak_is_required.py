"""User-service has no Keycloak-less mode: every identity comes from a Keycloak token."""

import asyncio

import pytest
from error_contract import UnauthorizedError
from starlette.requests import Request

from src.api import dependencies
from src.service.keycloak_service import KeycloakService


def _request(headers=None):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw})


@pytest.fixture
def keycloak_flag_off(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ENABLED", "false")
    monkeypatch.delenv("AUTHENTICATION_SECRET", raising=False)


def test_a_request_without_a_token_has_no_identity(keycloak_flag_off):
    assert asyncio.run(dependencies.get_current_user_id(_request())) is None


def test_a_bearer_token_without_gateway_proof_has_no_identity(keycloak_flag_off):
    assert asyncio.run(
        dependencies.get_current_user_id(
            _request({"authorization": "Bearer not.a.keycloak.token"})
        )
    ) is None


def test_require_auth_rejects_the_missing_identity(keycloak_flag_off):
    with pytest.raises(UnauthorizedError) as exc:
        asyncio.run(dependencies.require_auth(None))
    assert exc.value.status_code == 401


def test_keycloak_cannot_be_switched_off():
    assert not hasattr(KeycloakService, "is_enabled")
