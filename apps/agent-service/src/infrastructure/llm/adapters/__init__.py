"""LLM Provider Abstraction Layer.

Provides a unified interface for different LLM providers (Ollama, vLLM, etc.)
with dynamic model discovery and graceful handling of missing models.
"""

from infrastructure.llm.adapters.base import LLMProvider
from infrastructure.llm.adapters.ollama import OllamaProvider
from infrastructure.llm.adapters.registry import provider_registry
from infrastructure.llm.adapters.vllm import VLLMProvider

__all__ = [
    "LLMProvider",
    "OllamaProvider",
    "VLLMProvider",
    "provider_registry",
]
