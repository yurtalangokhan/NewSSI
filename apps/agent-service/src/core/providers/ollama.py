"""Ollama LLM Provider implementation."""

import asyncio

import httpx
from langchain_ollama import ChatOllama

from core.env import env
from core.logger import get_logger
from core.providers.base import LLMProvider, ModelInfo
from core.settings import settings

logger = get_logger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama provider that fetches models from the local Ollama server."""

    def __init__(self) -> None:
        self._reasoning_by_model: dict[str, bool] = {}

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama"

    @property
    def base_url(self) -> str:
        return env.OLLAMA_BASE_URL or settings.OLLAMA_BASE_URL

    async def get_available_models(self) -> list[ModelInfo]:
        """Fetch models and capabilities from Ollama /api/tags + /api/show."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code != 200:
                    logger.warning("Ollama returned %d when fetching models", response.status_code)
                    return []

                data = response.json()
                models = data.get("models", [])

                async def _show(name: str) -> dict:
                    try:
                        resp = await client.post(
                            f"{self.base_url}/api/show",
                            json={"name": name},
                            timeout=4.0,
                        )
                        if resp.status_code != 200:
                            return {}
                        return resp.json()
                    except Exception:
                        return {}

                show_payloads = await asyncio.gather(*(_show(m["name"]) for m in models))

                resolved_models: list[ModelInfo] = []
                for m, show in zip(models, show_payloads):
                    model_name = m["name"]

                    caps = show.get("capabilities") if isinstance(show, dict) else None
                    caps_list = caps if isinstance(caps, list) else []
                    model_info = show.get("model_info") if isinstance(show, dict) else None

                    supports_reasoning = (
                        any(
                            c in {"thinking", "reasoning"}
                            for c in [str(item).lower() for item in caps_list]
                        )
                        or any(
                            "reasoning" in str(k).lower() or "thinking" in str(k).lower()
                            for k in (model_info or {}).keys()
                        )
                        or any(
                            p in model_name.lower()
                            for p in (
                                "r1",
                                "qwq",
                                "reasoning",
                                "reasoner",
                                "thinking",
                                "cot",
                                "deepseek-r1",
                            )
                        )
                    )
                    self._reasoning_by_model[model_name] = supports_reasoning

                    supports_image_input = (
                        "vision" in [str(c).lower() for c in caps_list]
                        or bool((show or {}).get("projector_info"))
                        or any(
                            "vision" in str(k).lower()
                            or "clip" in str(k).lower()
                            or "projector" in str(k).lower()
                            for k in (model_info or {}).keys()
                        )
                        or any(
                            p in model_name.lower()
                            for p in (
                                "-vl",
                                ":vl",
                                "vl:",
                                "vl-",
                                "vision",
                                "llava",
                                "moondream",
                                "minicpm-v",
                                "pixtral",
                                "bakllava",
                                "qwen2.5vl",
                                "qwen2.5-vl",
                                "qwen2-vl",
                                "qwen-vl",
                                "llama3.2-vision",
                                "llama-vision",
                                "gemma3-vision",
                            )
                        )
                    )

                    supports_tools = (
                        "tools" in [str(c).lower() for c in caps_list]
                        or any(
                            "tools" in str(k).lower() or "function_calling" in str(k).lower()
                            for k in (model_info or {}).keys()
                        )
                        or any(
                            p in model_name.lower()
                            for p in (
                                "llama3.1",
                                "llama3.2",
                                "llama3.3",
                                "qwen2.5",
                                "qwen3",
                                "mistral",
                                "mixtral",
                                "command-r",
                                "firefunction",
                                "granite",
                                "functionary",
                            )
                        )
                    )

                    arch = str((model_info or {}).get("general.architecture", "")).lower()
                    supports_embedding = (
                        "embedding" in [str(c).lower() for c in caps_list]
                        or any(
                            v in arch for v in ("bert", "nomic-bert", "embedding", "xlm-roberta")
                        )
                        or any(
                            p in model_name.lower()
                            for p in (
                                "embed",
                                "bge",
                                "minilm",
                                "e5-",
                                "e5_",
                                "mxbai",
                                "gte-",
                                "snowflake-arctic-embed",
                            )
                        )
                    )

                    supports_code = any(
                        p in model_name.lower()
                        for p in (
                            "coder",
                            "code",
                            "codellama",
                            "starcoder",
                            "codegemma",
                            "codegeex",
                            "deepseek-coder",
                            "qwen2.5-coder",
                        )
                    )

                    supports_audio = (
                        any(
                            c in {"audio", "speech", "voice"}
                            for c in [str(item).lower() for item in caps_list]
                        )
                        or any(v in arch for v in ("whisper", "audio", "speech", "seamless"))
                        or any(
                            p in model_name.lower()
                            for p in (
                                "audio",
                                "whisper",
                                "speech",
                                "voice",
                                "seamless",
                                "bark",
                                "tts",
                                "stt",
                            )
                        )
                    )

                    ctx_len = None
                    if isinstance(model_info, dict):
                        for key, value in model_info.items():
                            if (
                                key.endswith(".context_length")
                                and isinstance(value, int)
                                and value > 0
                            ):
                                ctx_len = value
                                break

                    if ctx_len is None:
                        details_ctx = (m.get("details") or {}).get("context_length")
                        if isinstance(details_ctx, int) and details_ctx > 0:
                            ctx_len = details_ctx

                    resolved_models.append(
                        ModelInfo(
                            name=model_name,
                            display_name=model_name,
                            provider_type="ollama",
                            max_input_tokens=ctx_len,
                            supports_image_input=supports_image_input,
                            supports_reasoning=supports_reasoning,
                            supports_tools=supports_tools,
                            supports_embedding=supports_embedding,
                            supports_code=supports_code,
                            supports_audio=supports_audio,
                            is_remote=bool(m.get("remote_model")),
                        )
                    )

                return resolved_models
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
            reasoning=self._reasoning_by_model.get(model_name, False),
        )
