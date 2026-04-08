"""vLLM LLM Provider implementation."""

import httpx
from langchain_openai import ChatOpenAI

from core.env import env
from core.logger import get_logger
from core.providers.base import LLMProvider, ModelInfo

logger = get_logger(__name__)


class VLLMProvider(LLMProvider):
    """vLLM provider that fetches models from the OpenAI-compatible API."""

    @property
    def name(self) -> str:
        return "vllm"

    @property
    def display_name(self) -> str:
        return "vLLM"

    @property
    def base_url(self) -> str | None:
        return env.get("VLLM_BASE_URL")

    async def get_available_models(self) -> list[ModelInfo]:
        """Fetch available models from vLLM /v1/models endpoint."""
        base_url = self.base_url
        if not base_url:
            logger.debug("VLLM_BASE_URL not configured, skipping vLLM provider")
            return []

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}/v1/models")
                if response.status_code != 200:
                    logger.warning("vLLM returned %d when fetching models", response.status_code)
                    return []

                data = response.json()
                models = data.get("data", [])
                return [
                    ModelInfo(
                        name=m["id"],
                        display_name=m.get("name", m["id"]),
                        provider_type="vllm",
                    )
                    for m in models
                ]
        except httpx.ConnectError:
            logger.warning("Cannot connect to vLLM at %s", base_url)
            return []
        except Exception as e:
            logger.warning("Failed to fetch vLLM models: %s", e)
            return []

    def get_model_instance(self, model_name: str) -> ChatOpenAI:
        """Get a ChatOpenAI instance for the given model (vLLM uses OpenAI-compatible API)."""
        base_url = self.base_url
        if not base_url:
            raise ValueError("VLLM_BASE_URL not configured")

        return ChatOpenAI(
            model=model_name,
            temperature=0.5,
            streaming=True,
            openai_api_base=base_url,
            openai_api_key=env.get("VLLM_API_KEY") or "dummy",
        )
