"""Base LLM Provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelInfo:
    """Information about an available model."""

    name: str
    """The model identifier."""

    display_name: str | None = None
    """Human-readable name. Defaults to name if None."""

    is_visible: bool = True
    """Whether this model should be shown in the UI."""

    max_input_tokens: int | None = None
    """Maximum input tokens supported."""

    supports_image_input: bool = False
    """Whether the model supports image input."""

    supports_reasoning: bool = False
    """Whether the model supports reasoning/thinking."""

    provider_type: str = "unknown"
    """The provider type (ollama, vllm, etc.)."""

    @property
    def full_name(self) -> str:
        """Return the display name, falling back to name."""
        return self.display_name or self.name


@dataclass
class ProviderInfo:
    """Information about an LLM provider."""

    name: str
    """Unique provider identifier."""

    provider_type: str
    """Provider type (ollama, vllm, etc.)."""

    display_name: str
    """Human-readable provider name."""

    base_url: str | None = None
    """Base URL for the provider."""

    is_available: bool = False
    """Whether the provider is reachable and configured."""

    models: list[ModelInfo] = field(default_factory=list)
    """Available models from this provider."""

    error: str | None = None
    """Error message if provider is unavailable."""


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier (e.g., 'ollama', 'vllm')."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name (e.g., 'Ollama', 'vLLM')."""

    @abstractmethod
    async def get_available_models(self) -> list[ModelInfo]:
        """Fetch available models from the provider.

        Returns:
            List of ModelInfo objects for available models.
            Empty list if provider is unreachable or has no models.
        """

    @abstractmethod
    def get_model_instance(self, model_name: str) -> Any:
        """Get a LangChain model instance for the given model name.

        Args:
            model_name: The model identifier.

        Returns:
            A LangChain-compatible model instance.

        Raises:
            ValueError: If the model is not available.
        """

    async def is_available(self) -> bool:
        """Check if the provider is reachable and configured.

        Returns:
            True if the provider can be used.
        """
        try:
            models = await self.get_available_models()
            return len(models) > 0
        except Exception:
            return False

    async def get_info(self) -> ProviderInfo:
        """Get full provider information including available models.

        Returns:
            ProviderInfo with current status and models.
        """
        try:
            models = await self.get_available_models()
            return ProviderInfo(
                name=self.name,
                provider_type=self.name,
                display_name=self.display_name,
                is_available=len(models) > 0,
                models=models,
            )
        except Exception as e:
            return ProviderInfo(
                name=self.name,
                provider_type=self.name,
                display_name=self.display_name,
                is_available=False,
                models=[],
                error=str(e),
            )
