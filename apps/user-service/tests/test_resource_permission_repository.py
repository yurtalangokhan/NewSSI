"""Focused tests for resource-permission serialization."""

import uuid
from datetime import UTC, datetime

from src.repository.resource_permission_repository import ResourcePermissionRepository


class _UnloadedPermission:
    id = uuid.uuid4()
    resource_type = "agent"
    resource_id = "agent-1"
    resource_name = "Agent"
    organization_id = uuid.uuid4()
    user_id = None
    permission_level = "read"
    is_inherited = False
    granted_by = uuid.uuid4()
    granted_at = datetime.now(UTC)
    expires_at = None

    @property
    def organization(self):
        raise AssertionError("serialization attempted to load organization")

    @property
    def user(self):
        raise AssertionError("serialization attempted to load user")


def test_to_dict_can_skip_unloaded_relationships() -> None:
    """Mutation snapshots serialize without triggering relationship I/O."""
    result = ResourcePermissionRepository()._to_dict(
        _UnloadedPermission(),  # type: ignore[arg-type]
        include_relationships=False,
    )

    assert result["resource_id"] == "agent-1"
    assert result["organization"] is None
    assert result["user"] is None
