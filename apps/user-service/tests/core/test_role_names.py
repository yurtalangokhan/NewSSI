"""Identity models live in Keycloak; only the role display rule remains local."""

import importlib.util

import pytest

from src.core.permissions.roles import DEFAULT_ROLE_NAME, display_role_name


@pytest.mark.parametrize(
    "module",
    ["src.core.database.models.user_model", "src.core.database.models.coarse_role_model"],
)
def test_legacy_identity_model_modules_are_gone(module):
    assert importlib.util.find_spec(module) is None


def test_a_user_without_realm_roles_displays_the_default_role():
    assert DEFAULT_ROLE_NAME == "enduser"
    assert display_role_name("") == "enduser"
    assert display_role_name(None) == "enduser"


def test_keycloak_role_names_are_displayed_verbatim():
    assert display_role_name("auditor") == "auditor"
    assert display_role_name("UserRole.auditor") == "UserRole.auditor"
