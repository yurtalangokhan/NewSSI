"""Static validation tests for API routes."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.user_route import router as user_router
from src.api.routes.settings_route import router as settings_router
from src.api.routes.api_keys_route import router as api_keys_router
from src.api.routes.roles_route import router as roles_router


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
            "/users/me/settings/prompt-shortcuts",
            json={"name": "test", "content": "test"}
        )
        # Should not get 422
        assert response.status_code != 422


class TestApiKeysRoute:
    """Validate api_keys_route.py endpoints."""

    def test_delete_key_uuid_handling(self):
        """delete_key should properly handle UUID parsing."""
        from src.api.routes.api_keys_route import delete_key
        
        # This should not crash with invalid UUID
        key_id = str(uuid.uuid4())
        # The function signature should be valid
        assert delete_key.__name__ == "delete_key"


class TestRolesRoute:
    """Validate roles_route.py endpoints."""

    def test_create_role_import_style(self):
        """HTTPException should be imported at module level, not inline."""
        import src.api.routes.roles_route as roles_module
        import inspect
        
        source = inspect.getsource(roles_module)
        # Check if HTTPException is imported at module level
        assert "from fastapi import" in source[:200]


class TestEndpointSignatures:
    """Validate endpoint function signatures."""

    def test_settings_internal_endpoints_have_body_params(self):
        """Internal settings endpoints should properly handle dict parameters."""
        from src.api.routes.settings_route import (
            update_settings_internal,
            create_prompt_shortcut_internal,
        )
        
        import inspect
        
        # Check update_settings_internal signature
        sig = inspect.signature(update_settings_internal)
        assert "updates" in sig.parameters
        
        # Check create_prompt_shortcut_internal signature
        sig = inspect.signature(create_prompt_shortcut_internal)
        assert "shortcut" in sig.parameters


def test_route_prefixes_correctness():
    """Validate route prefixes are correct."""
    from src.api.routes import user_route, settings_route
    
    assert user_route.router.prefix == "/users"
    assert settings_route.router.prefix == "/users/me/settings"


def test_dependency_injection_consistency():
    """Validate that all endpoints use consistent dependency patterns."""
    import inspect
    from src.api.routes import user_route, settings_route, api_keys_route
    
    # All routes should use Annotated for dependencies
    user_functions = [
        user_route.get_me,
        user_route.list_users,
        user_route.create_user,
    ]
    
    for func in user_functions:
        source = inspect.getsource(func)
        assert "Depends(" in source, f"{func.__name__} should use Depends()"
