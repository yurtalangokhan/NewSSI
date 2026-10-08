"""RAG database credentials have no invented default."""

from config_manager import ConfigManager


def test_postgres_password_is_returned_when_configured(monkeypatch):
    monkeypatch.setenv("POSTGRES_RAG_SERVICE_PASSWORD", "hunter2")
    assert ConfigManager().POSTGRES_RAG_SERVICE_PASSWORD == "hunter2"


def test_postgres_password_is_missing_when_unconfigured(monkeypatch):
    monkeypatch.delenv("POSTGRES_RAG_SERVICE_PASSWORD", raising=False)
    assert ConfigManager().POSTGRES_RAG_SERVICE_PASSWORD is None
