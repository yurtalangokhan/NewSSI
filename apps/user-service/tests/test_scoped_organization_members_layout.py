"""Organization side panels must honor the same subtree boundary."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import ForbiddenError
from src.service.organization_scope_service import OrganizationScope
from src.service.user_organization_service import UserOrganizationService


async def test_members_of_unrelated_unit_are_denied():
    root, hidden = uuid.uuid4(), uuid.uuid4()
    service = UserOrganizationService()
    service.scope_service = SimpleNamespace(
        resolve=AsyncMock(return_value=OrganizationScope(False, [{"id": root}]))
    )
    service.org_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value={"id": hidden, "path": "/"})
    )
    service.repo = SimpleNamespace(get_organization_users=AsyncMock())
    with pytest.raises(ForbiddenError):
        await service.get_organization_users(hidden, actor_id=uuid.uuid4())
    service.repo.get_organization_users.assert_not_awaited()
