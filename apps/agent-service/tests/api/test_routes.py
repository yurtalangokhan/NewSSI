"""Tests for API dependencies.

Authentication happens at Gateway; these cover the service-side trust contract.
"""

import pytest
from starlette.requests import Request

import api.dependencies as api_dependencies
from core.exceptions import UnauthorizedError

SECRET = "shared-gateway-secret"


def _request(headers: dict[str, str] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (key.encode(), value.encode()) for key, value in (headers or {}).items()
            ],
        }
    )


class TestAPIDependencies:
    """Test suite for API dependencies."""

    def test_verify_bearer_accepts_gateway_identity(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", str(SECRET))

        api_dependencies.verify_bearer(
            _request({"x-gateway-token": SECRET, "x-gateway-user-id": "sub-1"})
        )

    def test_verify_bearer_rejects_request_that_skipped_gateway(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", str(SECRET))

        with pytest.raises(UnauthorizedError) as exc:
            api_dependencies.verify_bearer(_request({"authorization": "Bearer real.jwt.token"}))

        assert exc.value.status_code == 401

    def test_verify_bearer_rejects_forged_identity_header(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", str(SECRET))

        with pytest.raises(UnauthorizedError):
            api_dependencies.verify_bearer(_request({"x-gateway-user-id": "victim"}))

    def test_verify_api_key_returns_gateway_subject(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", str(SECRET))

        result = api_dependencies.verify_api_key(
            _request({"x-gateway-token": SECRET, "x-gateway-user-id": "sub-1"})
        )

        assert result == "sub-1"

    def test_verify_api_key_returns_none_without_gateway(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", str(SECRET))

        assert api_dependencies.verify_api_key(_request()) is None
