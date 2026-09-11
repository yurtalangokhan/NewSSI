import pytest

from langconnect import config


def test_settings_from_mapping_requires_required_values():
    with pytest.raises(
        ValueError, match="Required environment variable POSTGRES_HOST is not set"
    ):
        config.Settings.from_mapping({})


def test_settings_from_mapping_parses_required_runtime_values():
    settings = config.Settings.from_mapping(
        {
            "POSTGRES_HOST": "postgres",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "rag",
            "POSTGRES_PASSWORD": "secret",
            "POSTGRES_DB": "rag",
            "USER_SERVICE_URL": "http://user-service",
            "INTERNAL_SERVICE_TOKEN": "internal",
            "KEYCLOAK_CLIENT_SECRET": "client-secret",
            "KEYCLOAK_ISSUER_URL": "http://keycloak/realms/agenticai",
            "KEYCLOAK_AUDIENCE": "rag-service",
        }
    )

    assert settings.postgres_port == 5432
    assert settings.postgres_config == {
        "host": "postgres",
        "port": 5432,
        "user": "rag",
        "password": "secret",
        "database": "rag",
    }
    assert settings.user_service_url == "http://user-service"


def test_valid_api_keys_are_read_from_config(monkeypatch):
    monkeypatch.setattr(config, "VALID_API_KEYS", " alpha, , beta ,")

    assert config.parse_valid_api_keys() == {"alpha", "beta"}


def test_logging_config_has_operator_friendly_defaults():
    assert config.LOG_LEVEL == "INFO"
    assert config.LOG_FORMAT == "text"
