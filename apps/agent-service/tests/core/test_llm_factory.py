import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from core.llm_factory import get_llm_for_provider


@pytest.mark.asyncio
async def test_gemini_reasoning_sets_real_thinking_budget_param():
    """A reasoning-capable Gemini model must get `thinking_budget` as a
    first-class constructor arg.

    Regression: the factory used to pass `thinking_config={"thinking_budget": N}`,
    which is not a valid ChatGoogleGenerativeAI parameter. langchain-google-genai
    silently shoves unknown kwargs into `model_kwargs` (with a warning), so the
    thinking budget was never actually applied to requests.
    """
    llm = await get_llm_for_provider(
        "gemini-flash-latest",
        "google_genai",
        api_key="dummy-key",
        supports_reasoning=True,
    )

    assert isinstance(llm, ChatGoogleGenerativeAI)
    assert llm.thinking_budget == 8000
    assert "thinking_config" not in (llm.model_kwargs or {})


@pytest.mark.asyncio
async def test_gemini_reasoning_requests_thought_summaries():
    """Setting a thinking budget without `include_thoughts=True` makes Gemini
    spend thinking tokens but return no reasoning text at all, so the client
    never gets a "Thinking…" block."""
    llm = await get_llm_for_provider(
        "gemini-flash-latest",
        "google_genai",
        api_key="dummy-key",
        supports_reasoning=True,
    )

    assert isinstance(llm, ChatGoogleGenerativeAI)
    assert llm.include_thoughts is True


@pytest.mark.asyncio
async def test_gemini_without_reasoning_does_not_request_thought_summaries():
    llm = await get_llm_for_provider(
        "gemini-flash-latest",
        "google_genai",
        api_key="dummy-key",
        supports_reasoning=False,
    )

    assert isinstance(llm, ChatGoogleGenerativeAI)
    assert not llm.include_thoughts


@pytest.mark.asyncio
async def test_gemini_without_reasoning_has_no_thinking_budget():
    llm = await get_llm_for_provider(
        "gemini-flash-latest",
        "google_genai",
        api_key="dummy-key",
        supports_reasoning=False,
    )

    assert isinstance(llm, ChatGoogleGenerativeAI)
    assert llm.thinking_budget is None


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gemini-2.5-pro", "gemini-3.6-flash", "gemini-3.1-pro-preview"])
async def test_gemini_reasoning_falls_back_to_name_heuristic_when_capability_unknown(model):
    """When the caller cannot resolve `supports_reasoning`, the name heuristic
    still enables thinking for known reasoning families (2.5+ and 3.x)."""
    llm = await get_llm_for_provider(model, "google_genai", api_key="dummy-key")

    assert isinstance(llm, ChatGoogleGenerativeAI)
    assert llm.thinking_budget == 8000


@pytest.mark.asyncio
async def test_gemini_requires_api_key():
    with pytest.raises(ValueError):
        await get_llm_for_provider("gemini-flash-latest", "google_genai", api_key=None)


# ── Cross-provider reliability (max_retries + timeout) ────────────────────────

from core.settings import settings  # noqa: E402


@pytest.mark.asyncio
async def test_openai_gets_retry_and_timeout_from_settings():
    llm = await get_llm_for_provider("gpt-4o", "openai", api_key="k")
    assert llm.max_retries == settings.LLM_MAX_RETRIES
    assert llm.request_timeout == settings.LLM_REQUEST_TIMEOUT


@pytest.mark.asyncio
async def test_anthropic_gets_retry_and_timeout_from_settings():
    llm = await get_llm_for_provider("claude-3-5-sonnet-latest", "anthropic", api_key="k")
    assert llm.max_retries == settings.LLM_MAX_RETRIES
    assert llm.default_request_timeout == settings.LLM_REQUEST_TIMEOUT


@pytest.mark.asyncio
async def test_groq_gets_retry_from_settings():
    llm = await get_llm_for_provider("llama-3.3-70b-versatile", "groq", api_key="k")
    assert llm.max_retries == settings.LLM_MAX_RETRIES


@pytest.mark.asyncio
async def test_gemini_max_retries_capped_by_settings():
    llm = await get_llm_for_provider("gemini-3.6-flash", "google_genai", api_key="k")
    assert llm.max_retries == settings.LLM_MAX_RETRIES


# ── Anthropic reasoning + base_url ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_reasoning_honours_explicit_capability_flag():
    on = await get_llm_for_provider(
        "claude-3-5-sonnet-latest", "anthropic", api_key="k", supports_reasoning=True
    )
    assert on.thinking == {"type": "enabled", "budget_tokens": 8000}
    assert on.temperature == 1

    off = await get_llm_for_provider(
        "claude-sonnet-4-5", "anthropic", api_key="k", supports_reasoning=False
    )
    assert not off.thinking


@pytest.mark.asyncio
async def test_anthropic_reasoning_falls_back_to_family_when_capability_unknown():
    llm = await get_llm_for_provider("claude-3-7-sonnet-latest", "anthropic", api_key="k")
    assert llm.thinking == {"type": "enabled", "budget_tokens": 8000}


@pytest.mark.asyncio
async def test_anthropic_base_url_maps_to_anthropic_api_url():
    llm = await get_llm_for_provider(
        "claude-3-5-sonnet-latest", "anthropic", api_key="k", base_url="https://proxy.internal/v1"
    )
    assert str(llm.anthropic_api_url) == "https://proxy.internal/v1"


# ── OpenAI / Groq reasoning + Groq base_url ──────────────────────────────────


@pytest.mark.asyncio
async def test_openai_reasoning_effort_set_only_when_capability_true():
    on = await get_llm_for_provider("gpt-5", "openai", api_key="k", supports_reasoning=True)
    assert on.reasoning_effort == "medium"
    off = await get_llm_for_provider("gpt-4o", "openai", api_key="k")
    assert off.reasoning_effort is None


@pytest.mark.asyncio
async def test_groq_base_url_and_reasoning_format():
    llm = await get_llm_for_provider(
        "deepseek-r1-distill-llama-70b",
        "groq",
        api_key="k",
        base_url="https://api.groq.com/openai",
        supports_reasoning=True,
    )
    assert str(llm.groq_api_base) == "https://api.groq.com/openai"
    assert llm.reasoning_format == "parsed"


# ── Mistral uses the OpenAI-compatible endpoint ──────────────────────────────


@pytest.mark.asyncio
async def test_mistral_uses_openai_compatible_endpoint():
    llm = await get_llm_for_provider("mistral-large-latest", "mistral", api_key="k")
    assert isinstance(llm, ChatOpenAI)
    assert str(llm.openai_api_base) == "https://api.mistral.ai/v1"
    assert llm.max_retries == settings.LLM_MAX_RETRIES


# ── request_overrides threaded to non-vLLM providers ─────────────────────────


@pytest.mark.asyncio
async def test_request_overrides_apply_to_openai():
    llm = await get_llm_for_provider(
        "gpt-4o",
        "openai",
        api_key="k",
        request_overrides={"temperature": 0.2, "extra_body": {"service_tier": "flex"}},
    )
    assert llm.temperature == 0.2
    assert llm.extra_body == {"service_tier": "flex"}


@pytest.mark.asyncio
async def test_request_overrides_apply_to_anthropic():
    llm = await get_llm_for_provider(
        "claude-3-5-sonnet-latest",
        "anthropic",
        api_key="k",
        request_overrides={"temperature": 0.3},
    )
    assert llm.temperature == 0.3


# ── Azure api_version default ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_azure_uses_modern_api_version_default():
    llm = await get_llm_for_provider(
        "gpt-4o", "azure_openai", api_key="k", base_url="https://x.openai.azure.com"
    )
    assert llm.openai_api_version == "2024-10-21"
