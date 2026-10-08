"""RAG configuration is read and converted by the shared env accessor."""

from config_manager import ConfigManager


def test_rag_service_port_is_typed(monkeypatch):
    monkeypatch.setenv("RAG_SERVICE_PORT", "18083")
    assert ConfigManager().RAG_SERVICE_PORT == 18083


def test_rag_defaults_when_values_are_absent(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.delenv("VECTOR_DB_PROVIDER", raising=False)
    settings = ConfigManager()
    assert settings.LOG_LEVEL == "INFO"
    assert settings.LOG_FORMAT == "text"
    assert settings.VECTOR_DB_PROVIDER == "milvus"
