"""vLLM LLM Provider implementation."""

import httpx
from langchain_openai import ChatOpenAI

from core.http import outbound
from core.observability.logger import get_logger
from core.utils.model_classifier import is_embedding_model
from infrastructure.llm.adapters.base import LLMProvider, ModelInfo
from infrastructure.llm.adapters.vllm_chat import VLLMChatOpenAI

logger = get_logger(__name__)


class VLLMProvider(LLMProvider):
    """vLLM provider that fetches models from the OpenAI-compatible API."""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self._base_url = base_url
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "vllm"

    @property
    def display_name(self) -> str:
        return "vLLM"

    @property
    def base_url(self) -> str | None:
        return self._base_url

    async def get_available_models(self) -> list[ModelInfo]:
        """Fetch available models from vLLM /v1/models endpoint."""
        base_url = self.base_url
        if not base_url:
            logger.debug("vLLM base_url is empty, skipping model discovery")
            return []

        try:
            response = await outbound.request(
                outbound.VLLM,
                "GET",
                f"{base_url}/v1/models",
                timeout=5.0,
            )
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
                    max_input_tokens=m.get("max_model_len") or m.get("context_length") or m.get("max_input_tokens"),
                    supports_embedding=is_embedding_model(m),
                )
                for m in models
            ]
        except httpx.ConnectError:
            logger.warning("Cannot connect to vLLM at %s", base_url)
            return []
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            logger.warning("Failed to fetch vLLM models: %s", e)
            return []

    def get_model_instance(self, model_name: str) -> ChatOpenAI:
        """Get a ChatOpenAI instance for the given model (vLLM uses OpenAI-compatible API)."""
        base_url = self.base_url
        if not base_url:
            raise ValueError("vLLM base_url is required")

        return VLLMChatOpenAI(
            model=model_name,
            temperature=0.5,
            streaming=True,
            openai_api_base=base_url,
            openai_api_key=self._api_key or "dummy",
        )
