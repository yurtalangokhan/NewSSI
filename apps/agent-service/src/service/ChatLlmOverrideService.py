"""Resolving a chat turn's ``llm_override`` into a usable model.

Split out of ``api/routes/ChatRoute.send_chat_message``. The client sends a
provider id and a model name; turning those into a live LLM instance means
reading the provider registry, decrypting an API key, and asking whether the
model supports reasoning — none of which is route work
(docs/coding-standards.md).

Behaviour is unchanged from the extracted original, including the deliberate
"clear the override rather than fall back" rule below.
"""

from __future__ import annotations

from typing import Any

from core.logger import get_logger
from domain.providers.repository import ProviderRepository
from domain.providers.service import ProviderService

logger = get_logger(__name__)


async def _resolve_provider_for_user(
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


async def _resolve_model_supports_reasoning(
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


async def apply_provider_llm_override(
    llm_override: dict[str, Any] | None,
    effective_user_id: str,
) -> dict[str, Any] | None:
    """Attach a live ``llm_instance`` to ``llm_override``, or strip the model.

    When the provider cannot be resolved the model keys are removed rather
    than left in place: a stale pair (say a Gemini model name with an Ollama
    provider) would otherwise be handed to the agent and answered by the wrong
    backend. Returns the same dict, mutated, so callers keep their reference.
    """
    if not (llm_override and llm_override.get("provider_id") and llm_override.get("provider_type")):
        return llm_override

    model_name = llm_override.get("model") or llm_override.get("model_version")
    provider_resolution_failed = False
    if model_name:
        try:
            from core.llm_factory import get_llm_for_provider

            provider_id = str(llm_override["provider_id"])
            logger.debug(
                "Resolving provider: provider_id=%s, provider_type=%s, model=%s",
                provider_id,
                llm_override["provider_type"],
                model_name,
            )
            repo = ProviderRepository()
            provider = await _resolve_provider_for_user(effective_user_id, provider_id, repo)

            api_key = None
            base_url = None
            api_version = None
            request_overrides = None

            if provider:
                logger.debug("Found provider in registry: %s", provider)
                # Only fetch API key for DB-stored (non-builtin) providers
                if not provider.get("is_builtin"):
                    api_key = await repo.get_decrypted_api_key(provider_id, effective_user_id)
                base_url = provider.get("base_url") or (provider.get("user_config") or {}).get(
                    "api_base"
                )
                api_version = (provider.get("user_config") or {}).get("api_version")
                request_overrides = ((provider.get("config") or {}).get("custom_config") or {}).get(
                    "request_overrides"
                )
                provider_type = provider.get("provider_type") or llm_override["provider_type"]
                supports_reasoning = await _resolve_model_supports_reasoning(
                    user_id=effective_user_id,
                    provider_id=provider_id,
                    provider=provider,
                    model_name=model_name,
                    repo=repo,
                )
            else:
                logger.warning("Provider %s not found for user %s", provider_id, effective_user_id)
                provider_resolution_failed = True
                provider_type = llm_override["provider_type"]
                supports_reasoning = None

            if not provider_resolution_failed:
                llm_override["llm_instance"] = await get_llm_for_provider(
                    model_name,
                    provider_type,
                    api_key=api_key,
                    base_url=base_url,
                    api_version=api_version,
                    supports_reasoning=supports_reasoning,
                    request_overrides=request_overrides,
                )
                logger.debug("Successfully created LLM instance for model %s", model_name)
        except Exception as exc:
            provider_resolution_failed = True
            logger.exception("Provider-aware LLM resolution failed: %s", exc)

    if provider_resolution_failed:
        # Prevent stale/incompatible model fallback (e.g. Gemini model routed to Ollama).
        for key in ("model", "model_version", "provider_id", "provider_type", "llm_instance"):
            llm_override.pop(key, None)

    return llm_override
