"""Tests for API dependencies."""

from unittest.mock import patch

from starlette.requests import Request


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
        }
    )


class TestAPIDependencies:
    """Test suite for API dependencies."""

    def test_extract_user_id_from_token(self):
        """Test extracting user ID from token."""
        from service import AuthService
        from service.AuthService import extract_user_id_from_token

        with patch.object(AuthService.AuthService, "is_keycloak_enabled", return_value=False):
            result = extract_user_id_from_token("api-key:abc123")
        assert result == "abc123"

        with patch.object(AuthService.AuthService, "is_keycloak_enabled", return_value=False):
            result = extract_user_id_from_token("plain-token")
        assert result == "plain-token"

        # Test with empty token
        result = extract_user_id_from_token("")
        assert result is None

    def test_verify_bearer_no_keys(self):
        """Test verify_bearer with no API keys configured."""
        from service.AuthService import verify_bearer

        with (
            patch("api.dependencies._is_keycloak_enabled", return_value=False),
            patch("api.dependencies._get_valid_api_keys", return_value=set()),
        ):
            verify_bearer(_request(), None)

    def test_verify_bearer_with_valid_key(self):
        """Test verify_bearer with valid key."""
        from service.AuthService import verify_bearer

        class MockCredentials:
            scheme = "Bearer"
            credentials = "test-key"

        with (
            patch("api.dependencies._is_keycloak_enabled", return_value=False),
            patch("api.dependencies._get_valid_api_keys", return_value={"test-key"}),
        ):
            verify_bearer(_request(), MockCredentials())

    def test_verify_bearer_with_invalid_key(self):
        """Test verify_bearer with invalid key."""
        import pytest

        from core.exceptions import UnauthorizedError
        from service.AuthService import verify_bearer

        class MockCredentials:
            scheme = "Bearer"
            credentials = "invalid-key"

        with (
            patch("api.dependencies._is_keycloak_enabled", return_value=False),
            patch("api.dependencies._get_valid_api_keys", return_value={"test-key"}),
            pytest.raises(UnauthorizedError) as exc,
        ):
            verify_bearer(_request(), MockCredentials())

        assert exc.value.status_code == 401
