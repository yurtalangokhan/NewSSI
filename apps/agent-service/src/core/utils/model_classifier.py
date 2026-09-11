"""Model capability and classification utilities based on provider metadata and flags."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.providers.base import ModelInfo

    ModelLike = ModelInfo | Mapping[str, Any] | None
else:  # pragma: no cover - runtime alias, no import cycle
    ModelLike = Any

# Values (case-insensitive) that mark a model_type/model as an embedding model.
_EMBEDDING_TYPE_TOKENS = frozenset({"embedding", "embeddings"})
# llama.cpp / GGUF ``general.architecture`` values that are embedding-only.
_EMBEDDING_ARCHITECTURES = frozenset({"embedding", "nomic-bert", "bert", "xlm-roberta"})

# Gemini model-name prefixes whose families "think" by default. Google's
# ``/models`` response carries no capability flag for this, so the family name
# is the only signal — extend with LLM_EXTRA_REASONING_MODEL_PREFIXES rather
# than editing this list for every new release.
_GEMINI_REASONING_PREFIXES = (
    "gemini-2.5",
    "gemini-3",
    "gemini-flash-latest",
    "gemini-pro-latest",
)


def _extra_reasoning_prefixes() -> tuple[str, ...]:
    """Operator-supplied reasoning model-name prefixes, lower-cased."""
    from core.settings import settings

    raw = getattr(settings, "LLM_EXTRA_REASONING_MODEL_PREFIXES", "") or ""
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def _embedding_from_attributes(model: Any) -> bool:
    """Embedding signal from a typed object (e.g. ``ModelInfo``)."""
    if getattr(model, "supports_embedding", None) is True:
        return True
    mtype = getattr(model, "model_type", None)
    return isinstance(mtype, str) and mtype.strip().lower() in _EMBEDDING_TYPE_TOKENS


def _embedding_from_mapping(data: Mapping[str, Any]) -> bool:
    """Embedding signal from a dict payload (model_configurations, raw API)."""
    if data.get("supports_embedding") is True:
        return True

    model_type = data.get("model_type")
    if isinstance(model_type, str) and model_type.strip().lower() in _EMBEDDING_TYPE_TOKENS:
        return True

    capabilities = (
        data.get("capabilities")
        or data.get("supported_capabilities")
        or data.get("supported_features")
    )
    if isinstance(capabilities, list):
        if "embedding" in {str(c).strip().lower() for c in capabilities}:
            return True
    elif isinstance(capabilities, dict):
        if capabilities.get("embedding") is True or capabilities.get("embeddings") is True:
            return True

    gen_methods = data.get("supportedGenerationMethods")
    if isinstance(gen_methods, list):
        methods = {str(m).strip() for m in gen_methods}
        if "embedContent" in methods and "generateContent" not in methods:
            return True

    model_info = data.get("model_info") or data.get("metadata")
    if isinstance(model_info, dict):
        if model_info.get("supports_embedding") is True:
            return True
        arch = str(model_info.get("general.architecture", "")).strip().lower()
        if arch in _EMBEDDING_ARCHITECTURES and not data.get("supports_reasoning"):
            return True

    return False


def is_embedding_model(model_or_metadata: ModelLike) -> bool:
    """Return True if the model or its metadata indicates an embedding capability.

    Evaluates exclusively provider-reported capability flags, model types,
    modalities, and API metadata without hardcoded model names.
    """
    if model_or_metadata is None:
        return False
    if isinstance(model_or_metadata, Mapping):
        return _embedding_from_mapping(model_or_metadata)
    return _embedding_from_attributes(model_or_metadata)


def is_chat_model(model_or_metadata: ModelLike) -> bool:
    """Return True if the model is suitable for chat/conversational execution."""
    return not is_embedding_model(model_or_metadata)


def gemini_supports_reasoning(model_name: str) -> bool:
    """Infer built-in "thinking" support for a Gemini model from its name.

    Google's ``/models`` response exposes no capability flag for thinking, so
    unlike :func:`is_embedding_model` this has to key off the model family: the
    Gemini 2.5+ and 3.x lines all think by default, while Gemma, image and TTS
    variants do not. This is the single source of truth shared by provider
    discovery and the LLM factory's fallback path.
    """
    name = (model_name or "").lower()
    if "gemma" in name or "-image" in name or "-tts" in name:
        return False
    if "thinking" in name:
        return True
    return name.startswith(_GEMINI_REASONING_PREFIXES + _extra_reasoning_prefixes())


def anthropic_supports_reasoning(model_name: str) -> bool:
    """Infer extended-thinking support for a Claude model from its name.

    The Anthropic API exposes no capability flag for it, so key off the family:
    ``claude-3-7-*`` and every Claude 4.x line (opus/sonnet/haiku) support
    extended thinking; ``claude-3-5`` and earlier do not.
    """
    name = (model_name or "").lower()
    if name.startswith("claude-3-7"):
        return True
    if any(name.startswith(prefix) for prefix in _extra_reasoning_prefixes()):
        return True
    return bool(re.search(r"claude-(?:opus|sonnet|haiku)-4", name))
