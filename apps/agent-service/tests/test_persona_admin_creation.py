import pytest
from fastapi import HTTPException

from api.routes.PersonaRoute import _require_admin
from service.AuthService import AuthenticatedUser


def test_require_admin_rejects_end_user() -> None:
    user = AuthenticatedUser(user_id="user-1", email="user@example.com", roles=["enduser"])

    with pytest.raises(HTTPException) as exc_info:
        _require_admin(user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin role required"


def test_require_admin_accepts_admin() -> None:
    user = AuthenticatedUser(user_id="admin-1", email="admin@example.com", roles=["admin"])

    assert _require_admin(user) is user
