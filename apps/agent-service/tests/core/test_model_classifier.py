"""Tests for model capability and classification flags."""

import pytest

from core.providers.base import ModelInfo
from core.utils.model_classifier import (
    gemini_supports_reasoning,
    is_chat_model,
    is_embedding_model,
)


def test_is_embedding_model_with_flag():
    assert is_embedding_model({"supports_embedding": True}) is True
    assert is_embedding_model({"supports_embedding": False}) is False
    assert is_chat_model({"supports_embedding": False}) is True


def test_is_embedding_model_with_model_info():
    info_embed = ModelInfo(name="custom-model", supports_embedding=True)
    info_chat = ModelInfo(name="custom-model", supports_embedding=False)

    assert is_embedding_model(info_embed) is True
    assert is_chat_model(info_embed) is False

    assert is_embedding_model(info_chat) is False
    assert is_chat_model(info_chat) is True


def test_is_embedding_model_with_capabilities_list():
    assert is_embedding_model({"capabilities": ["embedding"]}) is True
    assert is_embedding_model({"capabilities": ["completion", "vision"]}) is False


def test_is_embedding_model_with_google_generation_methods():
    assert is_embedding_model({"supportedGenerationMethods": ["embedContent"]}) is True
    assert (
        is_embedding_model({"supportedGenerationMethods": ["generateContent", "embedContent"]})
        is False
    )
    assert is_embedding_model({"supportedGenerationMethods": ["generateContent"]}) is False


def test_is_embedding_model_with_model_type():
    assert is_embedding_model({"model_type": "embedding"}) is True
    assert is_embedding_model({"model_type": "embeddings"}) is True
    assert is_embedding_model({"model_type": "language"}) is False


@pytest.mark.parametrize(
    "model_name, expected",
    [
        ("gemini-3.6-flash", True),
        ("gemini-3.1-pro-preview", True),
        ("gemini-2.5-pro", True),
        ("gemini-2.5-flash-lite", True),
        ("gemini-flash-latest", True),
        ("gemini-pro-latest", True),
        ("gemini-2.0-flash-thinking-exp", True),
        ("gemini-2.0-flash", False),
        ("gemini-1.5-flash", False),
        ("gemma-4-31b-it", False),
        ("gemini-3-pro-image", False),
        ("gemini-2.5-flash-preview-tts", False),
        ("", False),
    ],
)
def test_gemini_supports_reasoning_is_inferred_from_family(model_name, expected):
    assert gemini_supports_reasoning(model_name) is expected


@pytest.mark.parametrize(
    "model_name, expected",
    [
        ("claude-3-7-sonnet-latest", True),
        ("claude-opus-4-1", True),
        ("claude-sonnet-4-5", True),
        ("claude-haiku-4", True),
        ("claude-3-5-sonnet-latest", False),
        ("claude-3-opus", False),
        ("claude-2.1", False),
        ("", False),
    ],
)
def test_anthropic_supports_reasoning_is_inferred_from_family(model_name, expected):
    from core.utils.model_classifier import anthropic_supports_reasoning

    assert anthropic_supports_reasoning(model_name) is expected
