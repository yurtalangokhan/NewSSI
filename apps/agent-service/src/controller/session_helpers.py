"""Pure helpers for session/persona/LLM-provider operations.

Extracted from ``SessionController`` to reduce its size.  Persona
serialization is shared by list/create/update paths; the LLM-provider
functions are stateless and need no controller instance.
"""

from __future__ import annotations

from typing import Any

from core.env import env
from core.utils.model_classifier import is_embedding_model


def serialize_builtin_persona(agent: Any, persona_id: int) -> dict[str, Any]:
    """Serialize a builtin agent (from ``get_all_agent_info``) as a persona dict."""
    return {
        "id": persona_id,
        "name": agent.key.replace("-", " ").title(),
        "description": agent.description,
        "tools": [],
        "starter_messages": None,
        "document_sets": [],
        "is_public": True,
        "is_visible": True,
        "display_priority": None,
        "featured": False,
        "builtin_persona": True,
        "labels": [],
        "owner": {"id": "system", "email": "System"},
    }


def serialize_custom_persona(persona: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Serialize a custom persona DB row as a persona dict."""
    return {
        "id": persona["id"],
        "name": persona["name"],
        "description": persona["description"],
        "tools": [],
        "starter_messages": persona.get("starter_messages"),
        "document_sets": [],
        "is_public": persona.get("is_public", True),
        "is_visible": True,
        "display_priority": None,
        "featured": False,
        "builtin_persona": False,
        "labels": persona.get("labels", []),
        "owner": {"id": persona.get("user_id", user_id), "email": "dev@local.dev"},
        "base_agent": persona.get("base_agent"),
        "mcp_tools": persona.get("mcp_tools", []),
    }


async def get_llm_providers() -> dict[str, Any]:
    """Return the provider list plus the selected/default model names."""
    from core.providers.registry import provider_registry

    provider_registry.initialize()
    provider_infos = await provider_registry.get_provider_infos()

    providers = []
    for i, info in enumerate(provider_infos):
        model_configs = [
            {
                "name": m.name,
                "is_visible": m.is_visible,
                "max_input_tokens": m.max_input_tokens,
                "supports_image_input": m.supports_image_input,
                "supports_reasoning": m.supports_reasoning,
                "supports_tools": getattr(m, "supports_tools", False),
                "supports_embedding": getattr(m, "supports_embedding", False),
                "supports_code": getattr(m, "supports_code", False),
                "supports_audio": getattr(m, "supports_audio", False),
            }
            for m in info.models
            if not is_embedding_model(m)
        ]
        providers.append(
            {
                "id": i + 1,
                "name": info.name,
                "provider": info.provider_type,
                "provider_display_name": info.display_name,
                "model_configurations": model_configs,
            }
        )

    default_model = env.DEFAULT_MODEL or None
    if not default_model and provider_infos:
        for info in provider_infos:
            if info.is_available and info.models:
                default_model = info.models[0].name
                break

    return {
        "providers": providers,
        "selected_provider": providers[0]["name"] if providers else None,
        "default_text": default_model,
        "default_vision": None,
    }


async def get_llm_built_in_options() -> list[dict[str, Any]]:
    """Return a flat list of all built-in model options across providers."""
    from core.providers.registry import provider_registry

    provider_registry.initialize()
    provider_infos = await provider_registry.get_provider_infos()

    result = []
    for info in provider_infos:
        for model in info.models:
            if is_embedding_model(model):
                continue
            result.append(
                {
                    "name": model.name,
                    "is_visible": model.is_visible,
                    "max_input_tokens": model.max_input_tokens,
                    "supports_image_input": model.supports_image_input,
                    "supports_reasoning": model.supports_reasoning,
                    "provider": info.name,
                }
            )

    return result


async def get_ollama_models() -> list[dict[str, Any]]:
    """Return the list of models available from the local Ollama provider."""
    from core.providers.ollama import OllamaProvider

    provider = OllamaProvider()
    models = await provider.get_available_models()
    return [
        {"name": m.name, "display_name": m.display_name}
        for m in models
        if not is_embedding_model(m)
    ]
