"""Provider-aware LLM factory.

Builds a concrete LangChain chat model instance based on provider type and
credentials resolved at request time.

Each provider family has a small builder function; :data:`_PROVIDER_BUILDERS`
maps every recognised provider alias to one. Adding a provider is a new
builder plus its aliases in that table — ``get_llm_for_provider`` itself never
grows another ``if`` branch.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from core.logger import get_logger
from core.providers.vllm_chat import VLLMChatOpenAI
from core.settings import settings
from core.utils.model_classifier import (
    anthropic_supports_reasoning,
    gemini_supports_reasoning,
)

logger = get_logger(__name__)

# Placeholder API key for OpenAI-compatible endpoints that need no auth but
# whose client still requires the field to be set.
_PLACEHOLDER_API_KEY = "dummy"

# request_overrides scalar keys forwarded verbatim to any chat client.
_PASSTHROUGH_OVERRIDE_KEYS = (
    "temperature",
    "top_p",
    "max_tokens",
    "reasoning_effort",
    "stop",
    "seed",
)


@dataclass(frozen=True)
class ProviderBuildContext:
    """Everything a provider builder needs to construct one chat model."""

    model_name: str
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    api_version: str | None = None
    supports_reasoning: bool | None = None
    request_overrides: dict | None = None

    def wants_thinking(self, family_heuristic: Callable[[str], bool]) -> bool:
        """Resolve the reasoning signal: explicit capability flag wins, else
        fall back to the model-family heuristic the caller couldn't apply.
        """
        if self.supports_reasoning is not None:
            return bool(self.supports_reasoning)
        return family_heuristic(self.model_name)


ProviderBuilder = Callable[[ProviderBuildContext], BaseChatModel]


def _normalize_provider(provider_type: str) -> str:
    return (provider_type or "").strip().lower()


def _deep_merge_dict(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _reliability_kwargs(timeout_field: str | None = "request_timeout") -> dict[str, Any]:
    """max_retries + read timeout applied to every provider client.

    The per-library defaults are all over the place (langchain-google-genai
    retries 6x with 2→64s backoff, the OpenAI client has no read timeout), so a
    stalled upstream can hang an SSE turn for minutes. ``timeout_field`` names
    the client's timeout kwarg; pass ``None`` for clients that take none.
    """
    kwargs: dict[str, Any] = {}
    if settings.LLM_MAX_RETRIES is not None:
        kwargs["max_retries"] = settings.LLM_MAX_RETRIES
    if timeout_field and settings.LLM_REQUEST_TIMEOUT:
        kwargs[timeout_field] = settings.LLM_REQUEST_TIMEOUT
    return kwargs


def _apply_request_overrides(
    kwargs: dict[str, Any],
    request_overrides: dict | None,
    *,
    extra_body_supported: bool,
) -> dict[str, Any]:
    """Fold provider-config ``request_overrides`` into constructor kwargs.

    Shape: ``{"model_kwargs": {...}, "extra_body": {...}, "temperature": ...}``.
    ``extra_body`` is a first-class ChatOpenAI arg; for clients without it the
    contents are merged into ``model_kwargs`` instead.
    """
    if not isinstance(request_overrides, dict):
        return kwargs

    model_kwargs = dict(kwargs.get("model_kwargs") or {})
    configured_mk = request_overrides.get("model_kwargs")
    if isinstance(configured_mk, dict):
        model_kwargs = _deep_merge_dict(model_kwargs, configured_mk)

    extra_body = request_overrides.get("extra_body")
    if isinstance(extra_body, dict):
        if extra_body_supported:
            kwargs["extra_body"] = _deep_merge_dict(kwargs.get("extra_body") or {}, extra_body)
        else:
            model_kwargs = _deep_merge_dict(model_kwargs, {"extra_body": extra_body})

    # LangChain wants extra_body as a top-level arg, never nested in model_kwargs.
    if extra_body_supported and isinstance(model_kwargs.get("extra_body"), dict):
        kwargs["extra_body"] = _deep_merge_dict(
            kwargs.get("extra_body") or {}, model_kwargs.pop("extra_body")
        )

    for key in _PASSTHROUGH_OVERRIDE_KEYS:
        if key in request_overrides:
            kwargs[key] = request_overrides[key]

    if model_kwargs:
        kwargs["model_kwargs"] = model_kwargs
    return kwargs


# ---------------------------------------------------------------------------
# Per-provider builders
# ---------------------------------------------------------------------------


def _build_openai(ctx: ProviderBuildContext) -> BaseChatModel:
    # VLLMChatOpenAI handles reasoning fields from vLLM/OpenAI-compatible endpoints.
    cls = VLLMChatOpenAI if ctx.base_url else ChatOpenAI
    kwargs: dict[str, Any] = {
        "model": ctx.model_name,
        "api_key": ctx.api_key,
        "base_url": ctx.base_url,
        **_reliability_kwargs("request_timeout"),
    }
    if ctx.supports_reasoning is True:
        kwargs["reasoning_effort"] = settings.LLM_OPENAI_REASONING_EFFORT
    kwargs = _apply_request_overrides(kwargs, ctx.request_overrides, extra_body_supported=True)
    return cls(**kwargs)


def _build_anthropic(ctx: ProviderBuildContext) -> BaseChatModel:
    kwargs: dict[str, Any] = {
        "model": ctx.model_name,
        "api_key": ctx.api_key,
        **_reliability_kwargs("default_request_timeout"),
    }
    if ctx.base_url:
        kwargs["anthropic_api_url"] = ctx.base_url
    kwargs = _apply_request_overrides(kwargs, ctx.request_overrides, extra_body_supported=False)
    if ctx.wants_thinking(anthropic_supports_reasoning):
        kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": settings.LLM_ANTHROPIC_THINKING_BUDGET_TOKENS,
        }
        kwargs["temperature"] = 1  # required by Anthropic when thinking is on
    return ChatAnthropic(**kwargs)


def _build_gemini(ctx: ProviderBuildContext) -> BaseChatModel:
    if not ctx.api_key:
        raise ValueError("google_genai provider requires an API key")
    kwargs: dict[str, Any] = {
        "model": ctx.model_name,
        "google_api_key": ctx.api_key,
        **_reliability_kwargs("timeout"),
    }
    if ctx.base_url:
        kwargs["base_url"] = ctx.base_url
    kwargs = _apply_request_overrides(kwargs, ctx.request_overrides, extra_body_supported=False)
    if ctx.wants_thinking(gemini_supports_reasoning):
        # `thinking_budget` is a first-class ChatGoogleGenerativeAI arg. Passing
        # `thinking_config=...` instead makes langchain-google-genai silently
        # drop it into model_kwargs, so the budget never reaches the API.
        # `include_thoughts` is required for Gemini to return thought summaries
        # at all — without it the budget is spent but no reasoning text comes
        # back, so the client never sees a "Thinking…" block.
        kwargs["thinking_budget"] = settings.LLM_GEMINI_THINKING_BUDGET_TOKENS
        kwargs["include_thoughts"] = True
    return ChatGoogleGenerativeAI(**kwargs)


def _build_groq(ctx: ProviderBuildContext) -> BaseChatModel:
    kwargs: dict[str, Any] = {
        "model": ctx.model_name,
        "api_key": ctx.api_key,
        **_reliability_kwargs("request_timeout"),
    }
    if ctx.base_url:
        kwargs["base_url"] = ctx.base_url
    if ctx.supports_reasoning is True:
        # Surface chain-of-thought in a dedicated field instead of inline
        # <think> tags in the visible answer.
        kwargs["reasoning_format"] = "parsed"
    kwargs = _apply_request_overrides(kwargs, ctx.request_overrides, extra_body_supported=False)
    return ChatGroq(**kwargs)


def _build_mistral(ctx: ProviderBuildContext) -> BaseChatModel:
    # langchain-mistralai is not a dependency — use Mistral's own
    # OpenAI-compatible endpoint.
    kwargs: dict[str, Any] = {
        "model": ctx.model_name,
        "api_key": ctx.api_key or _PLACEHOLDER_API_KEY,
        "base_url": ctx.base_url or settings.LLM_MISTRAL_BASE_URL,
        **_reliability_kwargs("request_timeout"),
    }
    kwargs = _apply_request_overrides(kwargs, ctx.request_overrides, extra_body_supported=True)
    return ChatOpenAI(**kwargs)


def _build_bedrock(ctx: ProviderBuildContext) -> BaseChatModel:
    overrides = ctx.request_overrides if isinstance(ctx.request_overrides, dict) else {}
    bedrock_kwargs: dict[str, Any] = {}
    try:
        from botocore.config import Config

        bedrock_kwargs["config"] = Config(
            retries={
                "max_attempts": (settings.LLM_MAX_RETRIES or 0) + 1,
                "mode": "standard",
            },
            read_timeout=int(
                settings.LLM_REQUEST_TIMEOUT or settings.LLM_BEDROCK_READ_TIMEOUT_SECONDS
            ),
            connect_timeout=settings.LLM_BEDROCK_CONNECT_TIMEOUT_SECONDS,
        )
    except ImportError:  # botocore ships with langchain-aws; tolerate its absence
        logger.warning("botocore unavailable — Bedrock client built without retry/timeout config")
    if ctx.base_url:
        bedrock_kwargs["endpoint_url"] = ctx.base_url
    for key in ("region_name", "credentials_profile_name"):
        if overrides.get(key):
            bedrock_kwargs[key] = overrides[key]

    try:
        from langchain_aws import ChatBedrock

        return ChatBedrock(model_id=ctx.model_name, **bedrock_kwargs)
    except ImportError:
        from langchain_aws import ChatBedrockConverse

        return ChatBedrockConverse(model=ctx.model_name, **bedrock_kwargs)


def _build_ollama(ctx: ProviderBuildContext) -> BaseChatModel:
    # Only enable Ollama reasoning for models that explicitly advertise
    # thinking capability. Some models reject thinking=true with HTTP 400.
    return ChatOllama(
        model=ctx.model_name,
        base_url=ctx.base_url,
        streaming=True,
        reasoning=bool(ctx.supports_reasoning),
    )


def _build_openai_compatible(ctx: ProviderBuildContext) -> BaseChatModel:
    """vLLM / LiteLLM / DeepSeek / OpenRouter / generic OpenAI-compatible."""
    request_overrides = ctx.request_overrides
    model_kwargs: dict[str, Any] = {}
    explicit_extra_body: dict | None = None

    if isinstance(request_overrides, dict):
        configured_model_kwargs = request_overrides.get("model_kwargs")
        if isinstance(configured_model_kwargs, dict):
            model_kwargs = _deep_merge_dict(model_kwargs, configured_model_kwargs)

        configured_extra_body = request_overrides.get("extra_body")
        if isinstance(configured_extra_body, dict):
            explicit_extra_body = _deep_merge_dict(explicit_extra_body or {}, configured_extra_body)

    # Capability-driven default for vLLM/Qwen-like endpoints that require
    # explicit thinking enablement via chat_template_kwargs.
    if ctx.provider == "vllm" and ctx.supports_reasoning is True:
        explicit_extra_body = _deep_merge_dict(
            explicit_extra_body or {},
            {"chat_template_kwargs": {"enable_thinking": True}},
        )

    # LangChain expects extra_body as a first-class argument for ChatOpenAI,
    # not embedded in model_kwargs.
    if isinstance(model_kwargs.get("extra_body"), dict):
        explicit_extra_body = _deep_merge_dict(
            explicit_extra_body or {}, model_kwargs.pop("extra_body")
        )

    kwargs: dict[str, Any] = {
        "model": ctx.model_name,
        "api_key": ctx.api_key or _PLACEHOLDER_API_KEY,
        "base_url": ctx.base_url,
        **_reliability_kwargs("request_timeout"),
    }
    for key in _PASSTHROUGH_OVERRIDE_KEYS:
        if isinstance(request_overrides, dict) and key in request_overrides:
            kwargs[key] = request_overrides[key]
    if model_kwargs:
        kwargs["model_kwargs"] = model_kwargs
    if explicit_extra_body:
        kwargs["extra_body"] = explicit_extra_body

    return VLLMChatOpenAI(**kwargs)


def _build_azure(ctx: ProviderBuildContext) -> BaseChatModel:
    if not ctx.base_url:
        raise ValueError("Azure provider requires base_url")
    kwargs: dict[str, Any] = {
        "model": ctx.model_name,
        "azure_endpoint": ctx.base_url,
        "api_key": ctx.api_key,
        "api_version": ctx.api_version or settings.LLM_AZURE_API_VERSION,
        **_reliability_kwargs("request_timeout"),
    }
    if ctx.supports_reasoning is True:
        kwargs["reasoning_effort"] = settings.LLM_OPENAI_REASONING_EFFORT
    kwargs = _apply_request_overrides(kwargs, ctx.request_overrides, extra_body_supported=True)
    return AzureChatOpenAI(**kwargs)


def _build_openai_fallback(ctx: ProviderBuildContext) -> BaseChatModel:
    """Unknown provider that still exposes an OpenAI-compatible API."""
    kwargs: dict[str, Any] = {
        "model": ctx.model_name,
        "api_key": ctx.api_key or _PLACEHOLDER_API_KEY,
        "base_url": ctx.base_url,
        **_reliability_kwargs("request_timeout"),
    }
    kwargs = _apply_request_overrides(kwargs, ctx.request_overrides, extra_body_supported=True)
    return ChatOpenAI(**kwargs)


# provider alias -> builder. The key set is the authoritative "known providers"
# list; ``_KNOWN_PROVIDERS`` is derived from it so the two can't drift.
_PROVIDER_BUILDERS: dict[str, ProviderBuilder] = {
    "openai": _build_openai,
    "anthropic": _build_anthropic,
    "google": _build_gemini,
    "google_genai": _build_gemini,
    "google_vertexai": _build_gemini,
    "groq": _build_groq,
    "mistral": _build_mistral,
    "bedrock": _build_bedrock,
    "aws": _build_bedrock,
    "aws_bedrock": _build_bedrock,
    "ollama": _build_ollama,
    "vllm": _build_openai_compatible,
    "openai_compatible": _build_openai_compatible,
    "litellm": _build_openai_compatible,
    "deepseek": _build_openai_compatible,
    "openrouter": _build_openai_compatible,
    "azure": _build_azure,
    "azure_openai": _build_azure,
}

_KNOWN_PROVIDERS = frozenset(_PROVIDER_BUILDERS)

# When the caller gave no recognised provider type, fall back to a model-name
# prefix hint — but never override an ``azure_openai`` provider serving
# ``gpt-4o`` into plain OpenAI.
_NAME_HINT_BUILDERS: tuple[tuple[str, ProviderBuilder], ...] = (
    ("gpt-", _build_openai),
    ("claude-", _build_anthropic),
    ("gemini-", _build_gemini),
)


def _select_builder(provider: str, model_name: str) -> ProviderBuilder:
    builder = _PROVIDER_BUILDERS.get(provider)
    if builder is not None:
        return builder
    if provider not in _KNOWN_PROVIDERS:
        for prefix, hint_builder in _NAME_HINT_BUILDERS:
            if model_name.startswith(prefix):
                return hint_builder
    return _build_openai_fallback


async def get_llm_for_provider(
    model_name: str,
    provider_type: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    api_version: str | None = None,
    supports_reasoning: bool | None = None,
    request_overrides: dict | None = None,
) -> BaseChatModel:
    ctx = ProviderBuildContext(
        model_name=model_name,
        provider=_normalize_provider(provider_type),
        api_key=api_key,
        base_url=base_url,
        api_version=api_version,
        supports_reasoning=supports_reasoning,
        request_overrides=request_overrides,
    )
    return _select_builder(ctx.provider, model_name)(ctx)
