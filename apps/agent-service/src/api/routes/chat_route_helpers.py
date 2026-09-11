"""Pure helpers for chat routes.

Extracted from ``ChatRoute`` to keep the route file focused on endpoint
definitions.  All functions here are stateless.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from i18n import t

from agents import DEFAULT_AGENT
from core.logger import get_logger
from domain.providers.repository import ProviderRepository
from domain.providers.service import ProviderService
from service.AuthService import get_primary_user_id

logger = get_logger(__name__)

PERSONA_ID_TO_AGENT: dict[int, str] = {
    0: "chatbot",
    1: "configurable-mcp-agent",
}


def resolve_custom_persona_agent(
    persona_id: int,
    custom_persona: dict[str, Any],
    llm_override: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Resolve a custom persona to the execution id and runtime overrides."""
    base_agent = custom_persona.get("base_agent")
    assistant_id = str(persona_id) if base_agent == "dynamic-agent" else base_agent or DEFAULT_AGENT

    resolved_override = dict(llm_override or {})
    if custom_persona.get("system_prompt"):
        resolved_override["system_prompt"] = custom_persona["system_prompt"]
    if custom_persona.get("mcp_tools"):
        resolved_override["mcp_tools"] = custom_persona["mcp_tools"]
    if custom_persona.get("rag_config"):
        resolved_override["rag_config"] = custom_persona["rag_config"]

    resolved_override["connector_bindings"] = list(
        custom_persona.get("connector_bindings") or []
    )
    binding_references = dict(resolved_override.get("binding_references") or {})
    binding_references["connectors.persona_id"] = str(persona_id)
    resolved_override["binding_references"] = binding_references

    # Pass the numeric persona_id so _handle_input reads LTM settings from the
    # correct persona, not from the underlying builtin graph key.
    resolved_override["_persona_id"] = persona_id
    return assistant_id, resolved_override


def truncate_name(message: str, max_length: int = 50) -> str:
    name = message.strip()
    name = " ".join(name.split())
    if len(name) > max_length:
        name = name[:max_length].rsplit(" ", 1)[0] + "..."
    return name or "New Chat"


def coerce_project_id(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_project_id_from_chat_context(
    request_project_id: Any,
    thread: dict[str, Any] | None,
) -> int | None:
    resolved_project_id = coerce_project_id(request_project_id)
    if resolved_project_id is not None or not isinstance(thread, dict):
        return resolved_project_id

    resolved_project_id = coerce_project_id(thread.get("project_id"))
    if resolved_project_id is not None:
        return resolved_project_id

    metadata = thread.get("metadata") or {}
    if isinstance(metadata, dict):
        return coerce_project_id(metadata.get("project_id"))

    return None


def merge_file_descriptors(
    request_descriptors: list[dict[str, Any]],
    project_descriptors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for descriptor in [*request_descriptors, *project_descriptors]:
        descriptor_id = descriptor.get("id") or descriptor.get("file_id")
        if not descriptor_id:
            descriptor_id = str(uuid.uuid4())
            descriptor = {**descriptor, "id": descriptor_id}

        existing = merged.get(str(descriptor_id))
        if existing is None:
            merged[str(descriptor_id)] = descriptor
            continue

        if not existing.get("data") and descriptor.get("data"):
            merged[str(descriptor_id)] = {**existing, **descriptor}

    return list(merged.values())


def resolve_effective_chat_user_id(identity: dict[str, Any], user_id: str | None) -> str:
    effective_user_id = get_primary_user_id(identity, user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail=t("auth.not_authenticated"))
    return effective_user_id


async def resolve_provider_for_user(
    user_id: str, provider_id: str, repo: ProviderRepository
) -> dict[str, Any] | None:
    provider_svc = ProviderService(repo)
    all_providers = await provider_svc.list_all(user_id)
    all_entries = [
        *all_providers.get("builtin", []),
        *all_providers.get("url_providers", []),
        *all_providers.get("user_providers", []),
    ]
    for provider in all_entries:
        if str(provider.get("id")) == str(provider_id):
            return provider
    return None


async def resolve_model_supports_reasoning(
    *,
    user_id: str,
    provider_id: str,
    provider: dict[str, Any],
    model_name: str,
    repo: ProviderRepository,
) -> bool | None:
    """Resolve model reasoning capability from provider model metadata.

    Priority:
    1) provider.config.model_configurations (persisted sync metadata)
    2) live provider model fetch fallback (for built-ins / unsynced providers)
    """
    config = provider.get("config") or {}
    model_configurations = config.get("model_configurations") or []
    if isinstance(model_configurations, list):
        for model in model_configurations:
            if model.get("name") == model_name:
                return bool(model.get("supports_reasoning", False))

    try:
        provider_svc = ProviderService(repo)
        live_models = await provider_svc.get_models_for_provider(provider_id, user_id)
        for model in live_models:
            if model.get("name") == model_name:
                return bool(model.get("supports_reasoning", False))
    except Exception as exc:
        logger.debug(
            "Could not resolve model capability for provider_id=%s model=%s: %s",
            provider_id,
            model_name,
            exc,
        )

    return None
