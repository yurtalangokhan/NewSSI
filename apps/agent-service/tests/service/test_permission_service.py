"""
Tests for agent-service PermissionService.

Tests permission delegation to user-service and fail-closed errors.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from error_contract import DependencyResponseError, DependencyUnavailableError

from core.http.api_versioning import USER_SERVICE_API_PREFIX
from service.auth.permission_service import PermissionService, get_permission_service
from tests.envelope import envelope


@pytest.fixture
def mock_http_client():
    """Stands in for the shared outbound transport's request call."""
    client = MagicMock()
    client.post = AsyncMock()
    client.get = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def permission_service(mock_http_client, patch_outbound_request, monkeypatch):
    """PermissionService whose outbound calls hit the mock transport."""
    monkeypatch.setenv("INTERNAL_USER_SERVICE_URL", "http://user-service")
    patch_outbound_request(get=mock_http_client.get, post=mock_http_client.post)
    return PermissionService()


@pytest.fixture(autouse=True)
def _closed_user_service_circuit():
    """Start each test with a closed user-service breaker.

    The breaker is process-wide, so a sibling suite that tripped it (anything
    that made user-service fail repeatedly) would deny the permission call
    before the mocked transport below is ever consulted — a failure that
    depends on which file ran earlier, not on this file's own behaviour.
    """
    from security import get_circuit_breaker
    from security.resilience import CircuitState

    get_circuit_breaker("user-service").state = CircuitState.CLOSED


@pytest.mark.asyncio
class TestPermissionService:
    """Test suite for PermissionService."""

    async def test_check_agent_access_allowed(self, permission_service, mock_http_client):
        """Test successful permission check."""
        user_id = str(uuid.uuid4())
        agent_id = "123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = envelope({
            "allowed": True,
            "permission_level": "execute",
            "source": "user",
        })
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
        assert call_args[0][0] == (
            f"{permission_service.user_service_url}{USER_SERVICE_API_PREFIX}/permissions/check"
        )
        assert call_args[1]["json"]["user_id"] == user_id
        assert call_args[1]["json"]["resource_type"] == "agent"
        assert call_args[1]["json"]["resource_id"] == agent_id

    async def test_check_agent_access_denied(self, permission_service, mock_http_client):
        """Test denied permission check."""
        user_id = str(uuid.uuid4())
        agent_id = "456"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = envelope({
            "allowed": False,
            "permission_level": None,
            "source": None,
        })
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response

        result = await permission_service.check_agent_access(
            user_id=user_id, agent_id=agent_id, required_permission="write"
        )

        assert result["allowed"] is False
        assert result["permission_level"] is None

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (httpx.HTTPError("offline"), DependencyUnavailableError),
            (ValueError("bad JSON"), DependencyResponseError),
        ],
    )
    async def test_check_agent_access_failure_propagates(
        self, permission_service, mock_http_client, error, expected
    ):
        mock_http_client.post.side_effect = error
        with pytest.raises(expected):
            await permission_service.check_agent_access("subject", "42")

    async def test_get_user_accessible_agents(self, permission_service, mock_http_client):
        """Test retrieving accessible agent list."""
        user_id = str(uuid.uuid4())

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = envelope({
            "resources": [
                {"resource_id": "agent-1", "permission_level": "read"},
                {"resource_id": "agent-2", "permission_level": "execute"},
                {"resource_id": "agent-3", "permission_level": "write"},
            ]
        })
        mock_response.raise_for_status = MagicMock()
        mock_http_client.get.return_value = mock_response

        result = await permission_service.get_user_accessible_agents(user_id)

        assert mock_http_client.get.call_args.kwargs["params"] == {
            "resource_type": "agent",
            "required_permission": "execute",
        }
        assert len(result) == 3
        assert "agent-1" in result
        assert "agent-2" in result
        assert "agent-3" in result

    async def test_get_user_accessible_agents_failure_propagates(
        self, permission_service, mock_http_client
    ):
        mock_http_client.get.side_effect = httpx.HTTPError("Service down")
        with pytest.raises(DependencyUnavailableError):
            await permission_service.get_user_accessible_agents("subject")

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
        mock_response.status_code = 200
        mock_response.json.return_value = envelope({"allowed": True})
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

    async def test_close_does_not_close_the_shared_client(
        self, permission_service, mock_http_client
    ):
        """``close()`` must not tear down a client other callers share.

        It used to close a per-instance client. The transport is process-wide
        now, so closing it here would break every other user-service caller.
        """
        await permission_service.close()

        mock_http_client.aclose.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api/v1", "/platform/v7"])
async def test_permission_requests_use_configured_api_prefix(
    monkeypatch, prefix, outbound_transport
):
    monkeypatch.setattr(
        "service.auth.permission_service.USER_SERVICE_API_PREFIX", prefix, raising=False
    )
    seen = []

    def respond(request):
        seen.append(str(request.url))
        if request.method == "POST":
            return httpx.Response(200, json=envelope({"allowed": True}))
        return httpx.Response(200, json=envelope({"resources": [{"resource_id": "42"}]}))

    service = PermissionService()
    service.user_service_url = "https://users.example.test"
    client = outbound_transport(respond)
    assert (await service.check_agent_access("subject", 42))["allowed"] is True
    assert await service.get_user_accessible_agents("subject") == ["42"]
    await client.aclose()
    assert seen == [
        f"https://users.example.test{prefix}/permissions/check",
        (f"https://users.example.test{prefix}/permissions/users/subject/accessible-resources"
        "?resource_type=agent&required_permission=execute"),
    ]
