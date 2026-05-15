"""Provider-aware LLM factory.

Builds a concrete LangChain chat model instance based on provider type and
credentials resolved at request time.
"""

from __future__ import annotations

from copy import deepcopy

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq


# Claude models that support extended thinking (claude-3-7+, claude-4 family).
# Temperature must be 1 when thinking is enabled (Anthropic requirement).
_ANTHROPIC_THINKING_PREFIXES = (
    "claude-3-7",
    "claude-opus-4",
    "claude-sonnet-4",
    "claude-haiku-4",
)

# Gemini models with built-in thinking (thinking is on by default for these).
_GEMINI_THINKING_PREFIXES = (
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash-thinking",
)


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
    provider = _normalize_provider(provider_type)

    if provider in {"openai"} or model_name.startswith("gpt-"):
        return ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url)

    if provider in {"anthropic"} or model_name.startswith("claude-"):
        if any(model_name.lower().startswith(p) for p in _ANTHROPIC_THINKING_PREFIXES):
            return ChatAnthropic(
                model=model_name,
                api_key=api_key,
                thinking={"type": "enabled", "budget_tokens": 8000},
                temperature=1,
            )
        return ChatAnthropic(model=model_name, api_key=api_key)

    if provider in {"google", "google_genai"} or model_name.startswith("gemini-"):
        if not api_key:
            raise ValueError("google_genai provider requires an API key")
        if any(model_name.lower().startswith(p) for p in _GEMINI_THINKING_PREFIXES):
            try:
                return ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=api_key,
                    thinking_config={"thinking_budget": 8000},
                )
            except TypeError:
                pass  # older langchain_google_genai without thinking_config
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key)

    if provider == "groq":
        return ChatGroq(model=model_name, api_key=api_key)

    if provider == "mistral":
        try:
            from langchain_mistralai import ChatMistralAI  # type: ignore[import-not-found]

            return ChatMistralAI(model=model_name, api_key=api_key)
        except Exception:
            # Fallback to OpenAI-compatible mode for environments that use
            # Mistral-compatible gateways.
            return ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url)

    if provider in {"bedrock", "aws", "aws_bedrock"}:
        try:
            from langchain_aws import ChatBedrock

            return ChatBedrock(model_id=model_name)
        except Exception:
            from langchain_aws import ChatBedrockConverse

            return ChatBedrockConverse(model=model_name)

    if provider == "ollama":
        # Only enable Ollama reasoning for models that explicitly advertise
        # thinking capability. Some models reject thinking=true with HTTP 400.
        return ChatOllama(
            model=model_name,
            base_url=base_url,
            streaming=True,
            reasoning=bool(supports_reasoning),
        )

    if provider in {"vllm", "openai_compatible", "litellm", "deepseek", "openrouter"}:
        model_kwargs: dict = {}

        if isinstance(request_overrides, dict):
            # Supports arbitrary OpenAI-compatible request options from provider config.
            configured_model_kwargs = request_overrides.get("model_kwargs")
            if isinstance(configured_model_kwargs, dict):
                model_kwargs = _deep_merge_dict(model_kwargs, configured_model_kwargs)

            configured_extra_body = request_overrides.get("extra_body")
            if isinstance(configured_extra_body, dict):
                model_kwargs = _deep_merge_dict(model_kwargs, {"extra_body": configured_extra_body})

        # Capability-driven default for vLLM/Qwen-like endpoints that require
        # explicit thinking enablement via chat_template_kwargs.
        if provider == "vllm" and supports_reasoning is True:
            model_kwargs = _deep_merge_dict(
                model_kwargs,
                {"extra_body": {"chat_template_kwargs": {"enable_thinking": True}}},
            )

        kwargs = {
            "model": model_name,
            "api_key": api_key or "dummy",
            "base_url": base_url,
        }
        if model_kwargs:
            kwargs["model_kwargs"] = model_kwargs

        return ChatOpenAI(
            **kwargs,
        )

    if provider in {"azure", "azure_openai"}:
        if not base_url:
            raise ValueError("Azure provider requires base_url")
        return AzureChatOpenAI(
            model=model_name,
            azure_endpoint=base_url,
            api_key=api_key,
            api_version=api_version or "2024-02-01",
        )

    # Safe fallback for unknown providers that expose OpenAI-compatible APIs.
    return ChatOpenAI(
        model=model_name,
        api_key=api_key or "dummy",
        base_url=base_url,
    )
