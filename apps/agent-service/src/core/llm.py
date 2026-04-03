"""
LLM Module - Only Ollama and OpenAI-compatible APIs.

This module provides LLM access using:
1. Ollama (local models)
2. Custom OpenAI-compatible APIs (self-hosted LLM servers)

No paid providers (OpenAI, Anthropic, Google, etc.) are supported.
"""

import logging
from functools import cache
from typing import TypeAlias

from langchain_community.chat_models import FakeListChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from core.env import env

logger = logging.getLogger(__name__)


class FakeToolModel(FakeListChatModel):
    def __init__(self, responses: list[str]):
        super().__init__(responses=responses)

    def bind_tools(self, tools):
        return self


ModelT: TypeAlias = ChatOllama | ChatOpenAI | FakeToolModel


@cache
def get_model(model_name: str | None = None) -> ModelT:
    """
    Get an LLM instance.

    Args:
        model_name: Model name to use. If None, uses DEFAULT_MODEL from settings.

    Returns:
        ChatOllama, ChatOpenAI (compatible), or FakeToolModel instance
    """
    from schema.models import FakeModelName, OllamaModelName

    if model_name is None:
        model_name = env.DEFAULT_MODEL or "ollama"

    if model_name == FakeModelName.FAKE or env.get("USE_FAKE_MODEL", "").lower() == "true":
        return FakeToolModel(responses=["This is a test response from the fake model."])

    if env.COMPATIBLE_BASE_URL and env.COMPATIBLE_MODEL:
        return ChatOpenAI(
            model=env.COMPATIBLE_MODEL,
            temperature=0.5,
            streaming=True,
            openai_api_base=env.COMPATIBLE_BASE_URL,
            openai_api_key=env.COMPATIBLE_API_KEY or "dummy",
        )

    if env.OLLAMA_BASE_URL:
        return ChatOllama(
            model=model_name,
            temperature=0.5,
            streaming=True,
            base_url=env.OLLAMA_BASE_URL,
        )

    return ChatOllama(
        model=model_name or env.OLLAMA_MODEL or "llama3.1:8b",
        temperature=0.5,
        streaming=True,
    )


def get_embedding_model():
    """Get an embedding model instance."""
    from langchain_ollama import ChatOllama

    embed_model = env.OLLAMA_EMBED_MODEL or "nomic-embed-text"

    if env.OLLAMA_BASE_URL:
        return ChatOllama(model=embed_model)

    return ChatOllama(model=embed_model)
