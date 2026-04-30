"""Controller for user settings and LLM provider endpoints."""

from typing import Any

from controller.auth_controller import AuthController, get_auth_controller
from controller.base import BaseController
from core.env import env


class UserController(BaseController):
    """Owns user preferences and model/provider endpoints."""

    def __init__(self, auth_controller: AuthController | None = None):
        self._auth_controller = auth_controller or get_auth_controller()

    async def get_user_assistant_preferences(self) -> dict[str, Any]:
        return {}

    async def get_recent_files(self) -> list[Any]:
        return []

    async def update_pinned_assistants(self, ordered_assistant_ids: list[int]) -> dict[str, Any]:
        return {"success": True, "pinned_assistants": ordered_assistant_ids}

    async def get_pinned_assistants(self) -> dict[str, list[int]]:
        return {"pinned_assistants": []}

    async def get_llm_provider(self) -> dict[str, Any]:
        return await self._auth_controller.get_llm_providers()

    async def get_llm_built_in_options(self) -> list[dict[str, Any]]:
        return await self._auth_controller.get_llm_built_in_options()

    async def test_llm_default(self) -> dict[str, bool]:
        return {"success": True}

    async def get_default_assistant(self) -> None:
        return None

    async def get_user_projects(self) -> list[Any]:
        return []

    async def get_notifications(self) -> list[Any]:
        return []

    async def get_input_prompts(self) -> list[Any]:
        return []

    async def get_connector_status(self) -> list[Any]:
        return []

    async def get_federated_oauth_status(self) -> dict[str, bool]:
        return {"enabled": False}

    async def get_federated(self) -> list[Any]:
        return []

    async def get_valid_tags(self) -> list[Any]:
        return []

    async def get_document_sets(self) -> list[Any]:
        return []

    async def get_admin_llm_provider(self) -> dict[str, Any]:
        llm_provider = await self.get_llm_provider()
        providers = llm_provider.get("providers", [])

        admin_providers = []
        for provider in providers:
            admin_providers.append(
                {
                    "id": provider.get("id"),
                    "name": provider.get("name"),
                    "provider": provider.get("provider"),
                    "provider_display_name": provider.get("provider_display_name"),
                    "api_key": None,
                    "api_base": None,
                    "api_version": None,
                    "custom_config": {},
                    "is_public": True,
                    "is_auto_mode": False,
                    "groups": [],
                    "personas": [],
                    "deployment_name": None,
                    "model_configurations": provider.get("model_configurations", []),
                }
            )

        default_model = env.DEFAULT_MODEL or llm_provider.get("default_text")
        return {
            "providers": admin_providers,
            "selected_provider": admin_providers[0]["name"] if admin_providers else None,
            "default_model": default_model,
        }

    async def test_llm(self) -> dict[str, bool]:
        return {"success": True}

    async def set_default_llm(self) -> dict[str, bool]:
        return {"success": True}

    async def get_ollama_models(self) -> list[dict[str, Any]]:
        return await self._auth_controller.get_ollama_models()

    async def save_llm_provider(self) -> dict[str, bool]:
        return {"success": True}

    async def create_llm_provider(self) -> dict[str, bool]:
        return {"success": True}

    async def get_persona_providers(self, persona_id: int) -> dict[str, Any]:
        _ = persona_id
        llm_provider = await self.get_llm_provider()
        return {
            "providers": llm_provider.get("providers", []),
            "selected_provider": llm_provider.get("selected_provider"),
            "default_model": llm_provider.get("default_text"),
        }


_user_controller: UserController | None = None


def get_user_controller() -> UserController:
    """Get singleton UserController."""
    global _user_controller
    if _user_controller is None:
        _user_controller = UserController()
    return _user_controller
