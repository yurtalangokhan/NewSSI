"""Business logic for managing the built-in Ollama service."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Protocol

from core.logger import get_logger

logger = get_logger(__name__)


class OllamaRepositoryProtocol(Protocol):
    base_url: str

    async def get_version(self) -> str: ...

    async def list_models(self) -> list[dict[str, Any]]: ...

    async def show_model(self, model_name: str) -> dict[str, Any]: ...

    async def delete_model(self, model_name: str) -> bool: ...


class OllamaPullRepositoryProtocol(OllamaRepositoryProtocol, Protocol):
    def stream_pull(self, model_name: str) -> AsyncIterator[str]: ...


class OllamaService:
    def __init__(self, repository: OllamaRepositoryProtocol) -> None:
        self._repository = repository

    async def get_status(self) -> dict[str, Any]:
        try:
            version, models = await asyncio.gather(
                self._repository.get_version(),
                self._repository.list_models(),
            )
            return {
                "base_url": self._repository.base_url,
                "online": True,
                "version": version or None,
                "model_count": len(models),
                "error": None,
            }
        except Exception as exc:
            logger.warning("Built-in Ollama status check failed: %s", exc)
            return {
                "base_url": self._repository.base_url,
                "online": False,
                "version": None,
                "model_count": 0,
                "error": str(exc) or type(exc).__name__,
            }

    async def list_models(self) -> list[dict[str, Any]]:
        raw_models = await self._repository.list_models()

        async def _show(raw_model: dict[str, Any]) -> dict[str, Any]:
            name = raw_model.get("name")
            if not isinstance(name, str) or not name:
                return {}
            try:
                return await self._repository.show_model(name)
            except Exception as exc:
                logger.warning("Failed to inspect Ollama model %s: %s", name, exc)
                return {}

        show_payloads = await asyncio.gather(*(_show(model) for model in raw_models))

        models: list[dict[str, Any]] = []
        for raw_model, show_payload in zip(raw_models, show_payloads):
            name = raw_model.get("name")
            if not isinstance(name, str) or not name:
                continue

            models.append(
                {
                    "name": name,
                    "display_name": name,
                    "size": raw_model.get("size"),
                    "max_input_tokens": self._extract_context_length(raw_model, show_payload),
                    "supports_image_input": self._infer_image_support(name, show_payload, raw_model),
                    "supports_reasoning": self._infer_reasoning_support(name, show_payload),
                    "supports_tools": self._infer_tools_support(name, show_payload),
                    "supports_embedding": self._infer_embedding_support(name, show_payload, raw_model),
                    "supports_code": self._infer_code_support(name, show_payload),
                    "supports_audio": self._infer_audio_support(name, show_payload, raw_model),
                    "is_remote": bool(raw_model.get("remote_model")),
                }
            )
        return models

    @staticmethod
    def _infer_image_support(
        name: str, show_payload: dict[str, Any], raw_model: dict[str, Any]
    ) -> bool:
        capabilities = show_payload.get("capabilities")
        if isinstance(capabilities, list) and "vision" in {str(c).lower() for c in capabilities}:
            return True
        if show_payload.get("projector_info"):
            return True
        model_info = show_payload.get("model_info")
        if isinstance(model_info, dict):
            arch = str(model_info.get("general.architecture", "")).lower()
            if any(v in arch for v in ("vl", "vision", "clip", "mllama", "llava", "multimodal")):
                return True
            for key in model_info.keys():
                k_low = str(key).lower()
                if "vision." in k_low or "clip." in k_low or "projector." in k_low:
                    return True
        details = raw_model.get("details")
        if isinstance(details, dict):
            families = details.get("families") or []
            if isinstance(families, list) and any(
                "clip" in str(f).lower() or "vision" in str(f).lower() or "mllama" in str(f).lower()
                for f in families
            ):
                return True
        name_low = name.lower()
        if any(
            pattern in name_low
            for pattern in (
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
        ):
            return True
        return False

    @staticmethod
    def _infer_tools_support(name: str, show_payload: dict[str, Any]) -> bool:
        capabilities = show_payload.get("capabilities")
        if isinstance(capabilities, list) and "tools" in {str(c).lower() for c in capabilities}:
            return True
        model_info = show_payload.get("model_info")
        if isinstance(model_info, dict):
            for key in model_info.keys():
                k_low = str(key).lower()
                if "tools" in k_low or "function_calling" in k_low:
                    return True
        name_low = name.lower()
        if any(
            pattern in name_low
            for pattern in (
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
        ):
            return True
        return False

    @staticmethod
    def _infer_embedding_support(
        name: str, show_payload: dict[str, Any], raw_model: dict[str, Any]
    ) -> bool:
        capabilities = show_payload.get("capabilities")
        if isinstance(capabilities, list) and "embedding" in {str(c).lower() for c in capabilities}:
            return True
        model_info = show_payload.get("model_info")
        if isinstance(model_info, dict):
            arch = str(model_info.get("general.architecture", "")).lower()
            if any(v in arch for v in ("bert", "nomic-bert", "embedding", "xlm-roberta")):
                return True
        name_low = name.lower()
        if any(
            pattern in name_low
            for pattern in (
                "embed",
                "bge",
                "minilm",
                "e5-",
                "e5_",
                "mxbai",
                "gte-",
                "snowflake-arctic-embed",
            )
        ):
            return True
        return False

    @staticmethod
    def _infer_code_support(name: str, show_payload: dict[str, Any]) -> bool:
        name_low = name.lower()
        if any(
            pattern in name_low
            for pattern in (
                "coder",
                "code",
                "codellama",
                "starcoder",
                "codegemma",
                "codegeex",
                "deepseek-coder",
                "qwen2.5-coder",
            )
        ):
            return True
        return False

    @staticmethod
    def _infer_audio_support(
        name: str, show_payload: dict[str, Any], raw_model: dict[str, Any]
    ) -> bool:
        capabilities = show_payload.get("capabilities")
        if isinstance(capabilities, list) and any(
            c in {"audio", "speech", "voice"} for c in {str(item).lower() for item in capabilities}
        ):
            return True
        model_info = show_payload.get("model_info")
        if isinstance(model_info, dict):
            arch = str(model_info.get("general.architecture", "")).lower()
            if any(v in arch for v in ("whisper", "audio", "speech", "seamless")):
                return True
            for key in model_info.keys():
                k_low = str(key).lower()
                if "audio." in k_low or "whisper." in k_low or "speech." in k_low:
                    return True
        details = raw_model.get("details")
        if isinstance(details, dict):
            families = details.get("families") or []
            if isinstance(families, list) and any(
                "whisper" in str(f).lower() or "audio" in str(f).lower() for f in families
            ):
                return True
        name_low = name.lower()
        if any(
            pattern in name_low
            for pattern in (
                "audio",
                "whisper",
                "speech",
                "voice",
                "seamless",
                "bark",
                "tts",
                "stt",
            )
        ):
            return True
        return False

    @staticmethod
    def _infer_reasoning_support(name: str, show_payload: dict[str, Any]) -> bool:
        capabilities = show_payload.get("capabilities")
        if isinstance(capabilities, list) and any(
            c in {"thinking", "reasoning"} for c in {str(item).lower() for item in capabilities}
        ):
            return True
        model_info = show_payload.get("model_info")
        if isinstance(model_info, dict):
            for key in model_info.keys():
                k_low = str(key).lower()
                if "reasoning" in k_low or "thinking" in k_low:
                    return True
        name_low = name.lower()
        if any(
            pattern in name_low
            for pattern in ("r1", "qwq", "reasoning", "reasoner", "thinking", "cot", "deepseek-r1")
        ):
            return True
        return False

    async def delete_model(self, model_name: str) -> dict[str, bool]:
        deleted = await self._repository.delete_model(model_name)
        if not deleted:
            raise ValueError("Model not found")
        return {"success": True}

    async def stream_pull(self, model_name: str) -> AsyncIterator[str]:
        stream_pull = getattr(self._repository, "stream_pull", None)
        if stream_pull is None:
            raise RuntimeError("Ollama repository does not support model pulls")

        async for line in stream_pull(model_name):
            yield f"data: {line}\n\n"
        yield 'data: {"status":"done"}\n\n'

    @staticmethod
    def _extract_context_length(
        raw_model: dict[str, Any], show_payload: dict[str, Any]
    ) -> int | None:
        model_info = show_payload.get("model_info")
        if isinstance(model_info, dict):
            for key, value in model_info.items():
                if key.endswith(".context_length") and isinstance(value, int) and value > 0:
                    return value

        context_length = show_payload.get("context_length")
        if isinstance(context_length, int) and context_length > 0:
            return context_length

        details = raw_model.get("details")
        if isinstance(details, dict):
            details_context_length = details.get("context_length")
            if isinstance(details_context_length, int) and details_context_length > 0:
                return details_context_length

        return None
