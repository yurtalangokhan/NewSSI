"""Known provider/model catalog for provider management.

Pure data + small constructors describing the well-known providers and their
known models. Extracted from ``ProviderService`` to keep the service focused on
orchestration and to make the catalog independently testable.
"""

from __future__ import annotations

from typing import Any


def _known_model(
    name: str,
    *,
    display_name: str | None = None,
    supports_image_input: bool = False,
    supports_reasoning: bool = False,
    supports_embedding: bool = False,
    max_input_tokens: int | None = None,
    is_remote: bool = False,
) -> dict[str, Any]:
    res = {
        "name": name,
        "display_name": display_name or name,
        "is_visible": True,
        "max_input_tokens": max_input_tokens,
        "supports_image_input": supports_image_input,
        "supports_reasoning": supports_reasoning,
        "is_remote": is_remote,
    }
    if supports_embedding:
        res["supports_embedding"] = True
    return res


KNOWN_MODELS_BY_PROVIDER: dict[str, list[dict[str, Any]]] = {
    # Providers rename and retire model ids often (and block retired ones for
    # new keys), so the model catalog is discovered live per connected account
    # (see _fetch_api_key_provider_models / _fetch_google_models / _fetch_*_models).
    # A provider with no live discovery simply exposes no preset models until the
    # user enters one.
}


def _well_known_api_key(
    name: str,
    provider_type: str,
    *,
    icon: str,
    default_model: str | None = None,
    default_model_display: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "provider_type": provider_type,
        "category": "api_key",
        "icon": icon,
        "known_models": KNOWN_MODELS_BY_PROVIDER.get(provider_type, []),
        "recommended_default_model": (
            {"name": default_model, "display_name": default_model_display or default_model}
            if default_model
            else None
        ),
    }


WELL_KNOWN_PROVIDERS: list[dict[str, Any]] = [
    # URL-based
    {"name": "Ollama", "provider_type": "ollama", "category": "url_based", "icon": "ollama"},
    {"name": "vLLM", "provider_type": "vllm", "category": "url_based", "icon": "cpu"},
    {
        "name": "OpenAI-Compatible",
        "provider_type": "openai_compatible",
        "category": "url_based",
        "icon": "openai",
    },
    {"name": "LiteLLM Proxy", "provider_type": "litellm", "category": "url_based", "icon": "cpu"},
    # API-key-based. No default_model on any of these: the recommended/selectable
    # models come from live discovery against the connected account, because
    # every one of these providers renames or retires model ids on its own
    # schedule. A provider whose account can't be introspected just starts with
    # an empty model list until the user types one.
    _well_known_api_key("OpenAI", "openai", icon="openai"),
    _well_known_api_key("Anthropic", "anthropic", icon="anthropic"),
    _well_known_api_key("Google Gemini", "google_genai", icon="google"),
    _well_known_api_key("Google Vertex AI", "google_vertexai", icon="google"),
    _well_known_api_key("Azure OpenAI", "azure_openai", icon="azure"),
    _well_known_api_key("Azure AI", "azure_ai", icon="azure"),
    _well_known_api_key("AWS Bedrock", "aws_bedrock", icon="amazon"),
    _well_known_api_key("Groq", "groq", icon="cpu"),
    _well_known_api_key("MistralAI", "mistral", icon="mistral"),
    _well_known_api_key("Cohere", "cohere", icon="cpu"),
    _well_known_api_key("DeepSeek", "deepseek", icon="deepseek"),
    _well_known_api_key("xAI (Grok)", "xai", icon="cpu"),
    _well_known_api_key("Perplexity", "perplexity", icon="cpu"),
    _well_known_api_key("Together AI", "together", icon="cpu"),
    _well_known_api_key("Fireworks AI", "fireworks", icon="cpu"),
    _well_known_api_key("Cerebras", "cerebras", icon="cpu"),
    _well_known_api_key("HuggingFace", "huggingface", icon="cpu"),
    _well_known_api_key("NVIDIA AI", "nvidia", icon="cpu"),
    _well_known_api_key("IBM WatsonX", "ibm_watsonx", icon="cpu"),
    _well_known_api_key("SambaNova", "sambanova", icon="cpu"),
    _well_known_api_key("OpenRouter", "openrouter", icon="openrouter"),
]

_WELL_KNOWN_BY_TYPE: dict[str, dict[str, Any]] = {
    p["provider_type"]: p for p in WELL_KNOWN_PROVIDERS
}
