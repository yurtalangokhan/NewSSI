"""Core embeddings provider factory.

Provides configured embeddings instances (OpenAI / Ollama) without depending on
any agent or service layer.
"""

from __future__ import annotations

from typing import Any

from config_manager import env


def get_embeddings() -> Any:
    """Get the configured embeddings model."""
    try:
        openai_key = env.OPENAI_API_KEY
        if openai_key:
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(api_key=openai_key)  # type: ignore[call-arg]
        else:
            base_url = env.OLLAMA_BASE_URL
            if not base_url:
                raise ValueError("OLLAMA_BASE_URL environment variable is required")
            from langchain_community.embeddings import OllamaEmbeddings

            return OllamaEmbeddings(base_url=base_url, model="nomic-embed-text")
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Embeddings: {e}") from e
