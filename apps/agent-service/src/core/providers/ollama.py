"""Ollama LLM Provider implementation."""

import httpx
from langchain_ollama import ChatOllama

from core.env import env
from core.logger import get_logger
from core.providers.base import LLMProvider, ModelInfo

logger = get_logger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama provider that fetches models from the local Ollama server."""

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama"

    @property
    def base_url(self) -> str:
        return env.OLLAMA_BASE_URL or "http://localhost:11434"

    async def get_available_models(self) -> list[ModelInfo]:
        """Fetch available models from Ollama /api/tags endpoint."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code != 200:
                    logger.warning("Ollama returned %d when fetching models", response.status_code)
                    return []

                data = response.json()
                models = data.get("models", [])
                return [
                    ModelInfo(
                        name=m["name"],
                        display_name=m["name"],
                        provider_type="ollama",
                        max_input_tokens=m.get("details", {}).get("context_length"),
                    )
                    for m in models
                ]
        except httpx.ConnectError:
            logger.warning("Cannot connect to Ollama at %s", self.base_url)
            return []
        except Exception as e:
            logger.warning("Failed to fetch Ollama models: %s", e)
            return []

    def get_model_instance(self, model_name: str) -> ChatOllama:
        """Get a ChatOllama instance for the given model."""
        return ChatOllama(
            model=model_name,
            temperature=0.5,
            streaming=True,
            base_url=self.base_url,
        )
