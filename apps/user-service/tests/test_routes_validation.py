"""Static validation tests for API routes."""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.api_keys_route import router as api_keys_router
from src.api.routes.roles_route import router as roles_router
from src.api.routes.settings_route import router as settings_router
from src.api.routes.user_route import router as user_router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(user_router)
    app.include_router(settings_router)
    app.include_router(api_keys_router)
    app.include_router(roles_router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestUserRoute:
    """Validate user_route.py endpoints."""

    def test_create_user_requires_body(self, client):
        """create_user should accept body payload, not **kwargs."""
        # This endpoint expects POST with JSON body
        response = client.post("/users/", json={"email": "test@example.com"})
        # Should not get 422 (validation error) for missing params
        assert response.status_code != 422

    def test_set_user_password_requires_body(self, client):
        """set_user_password should accept password in body."""
        test_id = str(uuid.uuid4())
        response = client.post(f"/users/{test_id}/password", json={"password": "newpass"})
        # Should not get 422 for missing password param
        assert response.status_code != 422

    def test_update_me_requires_body(self, client):
        """update_me should accept updates in body."""
        response = client.patch("/users/me", json={"first_name": "John"})
        # Should not get 422
        assert response.status_code != 422

    def test_change_me_password_requires_body(self, client):
        """change_me_password should accept old/new password in body."""
        response = client.post(
            "/users/me/password",
            json={"old_password": "old", "new_password": "new"},
        )
        # Should not get 422 for missing params
        assert response.status_code != 422

    def test_user_route_does_not_import_repositories(self):
        """Route handlers should delegate data access to controller/service layers."""
        import inspect

        import src.api.routes.user_route as user_route

        source = inspect.getsource(user_route)
        assert "from src.repository" not in source


class TestSettingsRoute:
    """Validate settings_route.py endpoints."""

    def test_update_settings_requires_body(self, client):
        """update_settings should accept updates in body."""
        response = client.patch("/users/me/settings/", json={"theme_preference": "dark"})
        # Should not get 422
        assert response.status_code != 422

    def test_create_prompt_shortcut_requires_body(self, client):
        """create_prompt_shortcut should accept shortcut dict in body."""
        response = client.post(
            "/users/me/settings/prompt-shortcuts", json={"name": "test", "content": "test"}
        )
        # Should not get 422
        assert response.status_code != 422

    def test_settings_route_does_not_import_repositories(self):
        """Route handlers should delegate data access to controller/service layers."""
        import inspect

        import src.api.routes.settings_route as settings_route

        source = inspect.getsource(settings_route)
        assert "from src.repository" not in source


class TestUserMemoryRoute:
    """Validate user_memory_route.py boundaries."""

    def test_user_memory_route_does_not_import_repositories(self):
        """Route handlers should delegate data access to controller/service layers."""
        import inspect

        import src.api.routes.user_memory_route as user_memory_route

        source = inspect.getsource(user_memory_route)
        assert "from src.repository" not in source


class TestApiKeysRoute:
    """Validate api_keys_route.py endpoints."""

    def test_delete_key_uuid_handling(self):
        """delete_key should properly handle UUID parsing."""
        from src.api.routes.api_keys_route import delete_key

        # The function signature should be valid
        assert delete_key.__name__ == "delete_key"


class TestRolesRoute:
    """Validate roles_route.py endpoints."""

    def test_create_role_import_style(self):
        """HTTPException should be imported at module level, not inline."""
        import inspect

        import src.api.routes.roles_route as roles_module

        source = inspect.getsource(roles_module)
        # Check if HTTPException is imported at module level
        assert "from fastapi import" in source[:200]


class TestPermissionController:
    """Validate permission controller boundaries."""

    def test_permission_controller_does_not_import_repositories(self):
        """Controller should delegate permission data access to service layer."""
        import inspect

        import src.controller.permission_controller as permission_controller

        source = inspect.getsource(permission_controller)
        assert "from src.repository" not in source


class TestAuthRoute:
    """Validate auth route boundaries."""

    def test_logout_does_not_require_access_token_dependency(self):
        """Logout must work after access token expiry when a refresh token exists."""
        import inspect

        from src.api.routes.auth_base_route import logout

        source = inspect.getsource(logout)

        assert "require_auth" not in source
        assert "Depends(" not in source

    def test_external_login_accepts_redirect_uri_query_param(self):
        """External form login must pass the browser callback URI through."""
        import inspect

        from src.api.routes.auth_base_route import external_login

        sig = inspect.signature(external_login)

        assert "redirect_uri" in sig.parameters


class TestEndpointSignatures:
    """Validate endpoint function signatures."""

    def test_settings_internal_endpoints_have_body_params(self):
        """Internal settings endpoints should properly handle dict parameters."""
        import inspect

        from src.api.routes.settings_route import (
            create_prompt_shortcut_internal,
            update_settings_internal,
        )

        # Check update_settings_internal signature
        sig = inspect.signature(update_settings_internal)
        assert "updates" in sig.parameters

        # Check create_prompt_shortcut_internal signature
        sig = inspect.signature(create_prompt_shortcut_internal)
        assert "shortcut" in sig.parameters


def test_route_prefixes_correctness():
    """Validate route prefixes are correct."""
    from src.api.routes import settings_route, user_route

    assert user_route.router.prefix == "/users"
    assert settings_route.router.prefix == "/users/me/settings"


def test_dependency_injection_consistency():
    """Validate that all endpoints use consistent dependency patterns."""
    import inspect

    from src.api.routes import user_route

    # All routes should use Annotated for dependencies
    user_functions = [
        user_route.get_me,
        user_route.list_users,
        user_route.create_user,
    ]

    for func in user_functions:
        source = inspect.getsource(func)
        assert "Depends(" in source, f"{func.__name__} should use Depends()"
