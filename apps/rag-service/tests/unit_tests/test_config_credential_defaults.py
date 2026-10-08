"""RAG database credentials have no published fallback value."""

from config_manager import ConfigManager


def test_neo4j_password_has_no_default(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    assert ConfigManager().NEO4J_PASSWORD is None


def test_neo4j_password_is_returned_when_configured(monkeypatch):
    monkeypatch.setenv("NEO4J_PASSWORD", "s3cret")
    assert ConfigManager().NEO4J_PASSWORD == "s3cret"
