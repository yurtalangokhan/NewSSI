"""LLM Provider Abstraction Layer.

Provides a unified interface for different LLM providers (Ollama, vLLM, etc.)
with dynamic model discovery and graceful handling of missing models.
"""

from core.providers.base import LLMProvider
from core.providers.ollama import OllamaProvider
from core.providers.registry import provider_registry
from core.providers.vllm import VLLMProvider

__all__ = [
    "LLMProvider",
    "OllamaProvider",
    "VLLMProvider",
    "provider_registry",
]
