"""Provider registry - manages all available LLM providers."""

from core.logger import get_logger
from core.providers.base import LLMProvider, ModelInfo, ProviderInfo
from core.providers.ollama import OllamaProvider
from core.providers.vllm import VLLMProvider

logger = get_logger(__name__)


class ProviderRegistry:
    """Registry of all available LLM providers.

    Discovers and caches provider information.
    Providers are discovered at startup and cached for performance.
    """

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._initialized: bool = False
        self._model_cache: dict[str, list[ModelInfo]] = {}
        self._all_models_cache: list[ModelInfo] | None = None

    def register(self, provider: LLMProvider) -> None:
        """Register a provider instance."""
        self._providers[provider.name] = provider
        self._all_models_cache = None
        logger.info("Registered provider: %s", provider.name)

    def get_provider(self, name: str) -> LLMProvider | None:
        """Get a provider by name."""
        return self._providers.get(name)

    def get_all_providers(self) -> dict[str, LLMProvider]:
        """Get all registered providers."""
        return dict(self._providers)

    async def get_all_models(self) -> list[ModelInfo]:
        """Get all available models from all providers.

        Returns models grouped by provider with format:
        - ollama: llama3.1:8b
        - ollama: qwen3:8b-fp16
        - vllm: my-model
        """
        if self._all_models_cache is not None:
            return self._all_models_cache

        all_models: list[ModelInfo] = []
        for provider in self._providers.values():
            try:
                models = await provider.get_available_models()
                all_models.extend(models)
            except Exception as e:
                logger.warning("Failed to get models from %s: %s", provider.name, e)

        self._all_models_cache = all_models
        return all_models

    async def get_model_names(self) -> list[str]:
        """Get all available model names as strings."""
        models = await self.get_all_models()
        return [m.name for m in models]

    async def find_model(self, model_name: str) -> tuple[LLMProvider | None, ModelInfo | None]:
        """Find a model across all providers.

        Args:
            model_name: The model name to find.

        Returns:
            Tuple of (provider, model_info) or (None, None) if not found.
        """
        for provider in self._providers.values():
            try:
                models = await provider.get_available_models()
                for model in models:
                    if model.name == model_name:
                        return provider, model
            except Exception:
                continue
        return None, None

    async def get_provider_infos(self) -> list[ProviderInfo]:
        """Get information for all providers."""
        infos: list[ProviderInfo] = []
        for provider in self._providers.values():
            info = await provider.get_info()
            infos.append(info)
        return infos

    def clear_cache(self) -> None:
        """Clear the model cache."""
        self._all_models_cache = None
        self._model_cache.clear()

    def initialize(self) -> None:
        """Initialize and register all available providers."""
        if self._initialized:
            return

        # Register Ollama provider (always available)
        self.register(OllamaProvider())

        # Register vLLM provider if configured
        from core.env import env

        if env.get("VLLM_BASE_URL"):
            self.register(VLLMProvider())

        self._initialized = True
        logger.info("Provider registry initialized with %d providers", len(self._providers))


# Singleton instance
provider_registry = ProviderRegistry()
