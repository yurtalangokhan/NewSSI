"""Unit tests for infrastructure.llm.embeddings."""

from __future__ import annotations

from unittest.mock import patch

from infrastructure.llm.embeddings import get_embeddings


def test_get_embeddings_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")
    with patch("langchain_openai.OpenAIEmbeddings") as mock_cls:
        get_embeddings()
        mock_cls.assert_called_once_with(api_key="fake-openai-key")


def test_get_embeddings_ollama(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    with patch("langchain_community.embeddings.OllamaEmbeddings") as mock_cls:
        get_embeddings()
        mock_cls.assert_called_once_with(
            base_url="http://localhost:11434", model="nomic-embed-text"
        )
