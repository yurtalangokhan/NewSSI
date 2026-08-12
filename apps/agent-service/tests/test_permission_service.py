"""
Tests for agent-service PermissionService.

Tests permission delegation to user-service with legacy fallback.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from service.permission_service import PermissionService, get_permission_service


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for user-service requests."""
    client = MagicMock()
    client.post = AsyncMock()
    client.get = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def permission_service(mock_http_client):
    """PermissionService with mocked HTTP client."""
    service = PermissionService()
    service._http_client = mock_http_client
    return service


@pytest.mark.asyncio
class TestPermissionService:
    """Test suite for PermissionService."""

    async def test_check_agent_access_allowed(self, permission_service, mock_http_client):
        """Test successful permission check."""
        user_id = str(uuid.uuid4())
        agent_id = "123"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "allowed": True,
            "permission_level": "execute",
            "source": "user",
        }
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response

        result = await permission_service.check_agent_access(
            user_id=user_id, agent_id=agent_id, required_permission="execute"
        )

        assert result["allowed"] is True
        assert result["permission_level"] == "execute"
        assert result["source"] == "user"

        mock_http_client.post.assert_called_once()
        call_args = mock_http_client.post.call_args
        assert "/api/permissions/check" in call_args[0][0]
        assert call_args[1]["json"]["user_id"] == user_id
        assert call_args[1]["json"]["resource_type"] == "agent"
        assert call_args[1]["json"]["resource_id"] == agent_id

    async def test_check_agent_access_denied(self, permission_service, mock_http_client):
        """Test denied permission check."""
        user_id = str(uuid.uuid4())
        agent_id = "456"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "allowed": False,
            "permission_level": None,
            "source": None,
        }
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response

        result = await permission_service.check_agent_access(
            user_id=user_id, agent_id=agent_id, required_permission="write"
        )

        assert result["allowed"] is False
        assert result["permission_level"] is None

    async def test_check_agent_access_http_error_fallback(
        self, permission_service, mock_http_client
    ):
        """Test fallback to legacy system on HTTP error."""
        user_id = str(uuid.uuid4())
        agent_id = "789"

        # Simulate HTTP error
        mock_http_client.post.side_effect = httpx.HTTPError("Connection failed")

        with patch.object(
            permission_service, "_check_legacy_access", new=AsyncMock()
        ) as mock_legacy:
            mock_legacy.return_value = {
                "allowed": True,
                "permission_level": "execute",
                "source": "legacy",
            }

            result = await permission_service.check_agent_access(user_id=user_id, agent_id=agent_id)

            assert result["allowed"] is True
            assert result["source"] == "legacy"
            mock_legacy.assert_called_once_with(user_id, agent_id)

    async def test_check_agent_access_unexpected_error_failsafe(
        self, permission_service, mock_http_client
    ):
        """Test fail-safe behavior on unexpected errors."""
        user_id = str(uuid.uuid4())
        agent_id = "999"

        # Simulate unexpected exception
        mock_http_client.post.side_effect = Exception("Unexpected error")

        result = await permission_service.check_agent_access(user_id=user_id, agent_id=agent_id)

        # Fail-safe: allow access
        assert result["allowed"] is True
        assert result["source"] == "fallback"

    async def test_get_user_accessible_agents(self, permission_service, mock_http_client):
        """Test retrieving accessible agent list."""
        user_id = str(uuid.uuid4())

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "resources": [
                {"resource_id": "agent-1", "permission_level": "read"},
                {"resource_id": "agent-2", "permission_level": "execute"},
                {"resource_id": "agent-3", "permission_level": "write"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_http_client.get.return_value = mock_response

        result = await permission_service.get_user_accessible_agents(user_id)

        assert len(result) == 3
        assert "agent-1" in result
        assert "agent-2" in result
        assert "agent-3" in result

    async def test_get_user_accessible_agents_fallback_to_legacy(
        self, permission_service, mock_http_client
    ):
        """Test fallback to legacy agent groups on error."""
        user_id = str(uuid.uuid4())

        mock_http_client.get.side_effect = httpx.HTTPError("Service down")

        with patch.object(
            permission_service, "_get_legacy_accessible_agents", new=AsyncMock()
        ) as mock_legacy:
            mock_legacy.return_value = ["legacy-agent-1", "legacy-agent-2"]

            result = await permission_service.get_user_accessible_agents(user_id)

            assert len(result) == 2
            assert "legacy-agent-1" in result
            mock_legacy.assert_called_once_with(user_id)

    async def test_check_bulk_access(self, permission_service):
        """Test bulk permission checking."""
        user_id = str(uuid.uuid4())
        agent_ids = ["agent-1", "agent-2", "agent-3"]

        with patch.object(permission_service, "check_agent_access", new=AsyncMock()) as mock_check:
            mock_check.side_effect = [
                {"allowed": True},
                {"allowed": False},
                {"allowed": True},
            ]

            result = await permission_service.check_bulk_access(user_id, agent_ids)

            assert result["agent-1"] is True
            assert result["agent-2"] is False
            assert result["agent-3"] is True
            assert mock_check.call_count == 3

    async def test_internal_service_token_header(self, permission_service, mock_http_client):
        """Test that internal service token is included when configured."""
        permission_service.internal_token = "test-token-123"

        user_id = str(uuid.uuid4())
        agent_id = "123"

        mock_response = MagicMock()
        mock_response.json.return_value = {"allowed": True}
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response

        await permission_service.check_agent_access(user_id, agent_id)

        call_args = mock_http_client.post.call_args
        headers = call_args[1]["headers"]
        assert headers["X-Internal-Service-Token"] == "test-token-123"

    async def test_permission_service_singleton(self):
        """Test that get_permission_service returns singleton."""
        service1 = get_permission_service()
        service2 = get_permission_service()

        assert service1 is service2

    async def test_close_http_client(self, permission_service, mock_http_client):
        """Test HTTP client cleanup."""
        await permission_service.close()

        mock_http_client.aclose.assert_called_once()
        assert permission_service._http_client is None

    @pytest.mark.asyncio
    async def test_legacy_access_check_with_agent_groups(self, permission_service):
        """Test legacy permission checking via agent_groups."""
        user_id = str(uuid.uuid4())
        agent_id = 123

        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "name": "Test Group",
                    "user_ids": [str(user_id), "other-user"],
                    "persona_ids": [123, 456],
                }
            ]
        )

        with patch("service.permission_service.AgentGroupRepository", return_value=mock_repo):
            result = await permission_service._check_legacy_access(user_id, agent_id)

            assert result["allowed"] is True
            assert result["source"] == "legacy"

    @pytest.mark.asyncio
    async def test_legacy_access_check_denied(self, permission_service):
        """Test legacy permission check denies when no match."""
        user_id = str(uuid.uuid4())
        agent_id = 999

        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "name": "Test Group",
                    "user_ids": ["different-user"],
                    "persona_ids": [123, 456],
                }
            ]
        )

        with patch("service.permission_service.AgentGroupRepository", return_value=mock_repo):
            result = await permission_service._check_legacy_access(user_id, agent_id)

            assert result["allowed"] is False
            assert result["source"] == "legacy"
