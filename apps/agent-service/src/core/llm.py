"""
LLM Module - Only Ollama and OpenAI-compatible APIs.

This module provides LLM access using:
1. Ollama (local models)
2. vLLM (self-hosted LLM servers with OpenAI-compatible API)
3. Custom OpenAI-compatible APIs

No paid providers (OpenAI, Anthropic, Google, etc.) are supported.
"""

import logging
from functools import cache
from typing import TypeAlias

from langchain_community.chat_models import FakeListChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from core.env import env

logger = logging.getLogger(__name__)


def _normalize_model_name(model_name: str | None) -> str | None:
    """Normalize provider aliases to concrete model names.

    Some dynamic agent definitions may store provider labels (e.g. "ollama")
    instead of an actual model id (e.g. "llama3.1:8b").
    """
    if model_name is None:
        return None

    normalized = model_name.strip()
    if not normalized:
        return None

    lower_name = normalized.lower()
    if lower_name in {"ollama", "default", "provider", "builtin"}:
        return env.OLLAMA_MODEL or "llama3.1:8b"

    return normalized


class FakeToolModel(FakeListChatModel):
    """Fake model for testing or when no real models are available."""

    def __init__(self, responses: list[str]):
        super().__init__(responses=responses)

    def bind_tools(self, tools):
        return self


ModelT: TypeAlias = ChatOllama | ChatOpenAI | FakeToolModel


@cache
def get_model(model_name: str | None = None) -> ModelT:
    """
    Get an LLM instance.

    Uses the provider registry to find the right provider for the model.
    Falls back to FakeToolModel if no models are available.

    Args:
        model_name: Model name to use. If None, tries to find any available model.

    Returns:
        ChatOllama, ChatOpenAI (compatible), or FakeToolModel instance
    """
    from core.providers.registry import provider_registry

    # Initialize providers if not done yet
    provider_registry.initialize()

    model_name = _normalize_model_name(model_name)

    # Fake model override for testing
    if model_name == "fake" or env.get("USE_FAKE_MODEL", "").lower() == "true":
        return FakeToolModel(responses=["This is a test response from the fake model."])

    # Compatible OpenAI API (legacy support)
    if env.COMPATIBLE_BASE_URL and env.COMPATIBLE_MODEL:
        return ChatOpenAI(
            model=env.COMPATIBLE_MODEL,
            temperature=0.5,
            streaming=True,
            openai_api_base=env.COMPATIBLE_BASE_URL,
            openai_api_key=env.COMPATIBLE_API_KEY or "dummy",
        )

    # If a specific model is requested, find it across providers
    if model_name:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, but get_model is sync
                # Fall back to direct provider lookup
                return _get_model_direct(model_name)
            else:
                provider, model_info = loop.run_until_complete(
                    provider_registry.find_model(model_name)
                )
                if provider and model_info:
                    return provider.get_model_instance(model_name)
        except Exception as e:
            logger.warning("Failed to find model %s via registry: %s", model_name, e)

        # Fallback: try Ollama directly
        return ChatOllama(
            model=model_name,
            temperature=0.5,
            streaming=True,
            base_url=env.OLLAMA_BASE_URL or "http://localhost:11434",
        )

    # No model specified - try to find any available model
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            all_models = loop.run_until_complete(provider_registry.get_all_models())
            if all_models:
                first_model = all_models[0]
                provider = provider_registry.get_provider(first_model.provider_type)
                if provider:
                    return provider.get_model_instance(first_model.name)
    except Exception as e:
        logger.warning("Failed to auto-select model: %s", e)

    # No models available - return fake model with helpful message
    logger.warning(
        "No LLM models available. "
        "Please ensure Ollama is running and has models pulled, "
        "or configure VLLM_BASE_URL. "
        "Returning fake model for testing."
    )
    return FakeToolModel(
        responses=[
            "No LLM models are currently available. "
            "Please ensure your LLM provider (Ollama/vLLM) is running and has models pulled. "
            "Check the admin panel to see available models."
        ]
    )


def _get_model_direct(model_name: str) -> ModelT:
    """Get a model instance without async calls (sync fallback)."""
    # Try Ollama first
    if env.OLLAMA_BASE_URL:
        return ChatOllama(
            model=model_name,
            temperature=0.5,
            streaming=True,
            base_url=env.OLLAMA_BASE_URL,
        )

    # Try vLLM
    vllm_url = env.get("VLLM_BASE_URL")
    if vllm_url:
        return ChatOpenAI(
            model=model_name,
            temperature=0.5,
            streaming=True,
            openai_api_base=vllm_url,
            openai_api_key=env.get("VLLM_API_KEY") or "dummy",
        )

    # Fallback to fake model
    return FakeToolModel(
        responses=[f"Model '{model_name}' not found. No LLM providers are configured or available."]
    )


def get_embedding_model():
    """Get an embedding model instance."""
    from langchain_ollama import ChatOllama

    embed_model = env.OLLAMA_EMBED_MODEL or "nomic-embed-text"

    if env.OLLAMA_BASE_URL:
        return ChatOllama(model=embed_model, base_url=env.OLLAMA_BASE_URL)

    return ChatOllama(model=embed_model)
