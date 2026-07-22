import logging
import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from core.settings import DatabaseType, LogLevel, Settings, check_str_is_http


def test_check_str_is_http():
    assert check_str_is_http("http://example.com/") == "http://example.com/"
    assert check_str_is_http("https://api.test.com/") == "https://api.test.com/"

    with pytest.raises(ValidationError):
        check_str_is_http("not_a_url")
    with pytest.raises(ValidationError):
        check_str_is_http("ftp://invalid.com")


def test_settings_default_values():
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None)

    assert settings.HOST == "0.0.0.0"
    assert settings.PORT == 8080
    assert settings.DATABASE_TYPE == DatabaseType.SQLITE
    assert settings.DEFAULT_MODEL == "llama3.1:8b"
    assert settings.AVAILABLE_MODELS == {"llama3.1:8b"}
    assert settings.MCP_GITHUB_SERVER_URL == "https://api.githubcopilot.com/mcp/"


def test_settings_available_models_include_configured_fallbacks():
    settings = Settings(
        DEFAULT_MODEL="qwen3",
        OLLAMA_MODEL="llama3.1:8b",
        COMPATIBLE_MODEL="custom-model",
        _env_file=None,
    )

    assert settings.AVAILABLE_MODELS == {"qwen3", "llama3.1:8b", "custom-model"}


def test_settings_base_url():
    settings = Settings(HOST="0.0.0.0", PORT=8000, _env_file=None)

    assert settings.BASE_URL == "http://0.0.0.0:8000"


def test_settings_is_dev():
    assert Settings(MODE="dev", _env_file=None).is_dev() is True
    assert Settings(MODE="prod", _env_file=None).is_dev() is False


def test_log_level_enum():
    assert LogLevel.DEBUG.to_logging_level() == logging.DEBUG
    assert LogLevel.INFO.to_logging_level() == logging.INFO
    assert LogLevel.WARNING.to_logging_level() == logging.WARNING
    assert LogLevel.ERROR.to_logging_level() == logging.ERROR
    assert LogLevel.CRITICAL.to_logging_level() == logging.CRITICAL


def test_settings_log_level_default():
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None)

    assert settings.LOG_LEVEL == LogLevel.WARNING
    assert settings.LOG_LEVEL.to_logging_level() == logging.WARNING


def test_settings_log_level_from_env():
    with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=True):
        settings = Settings(_env_file=None)

    assert settings.LOG_LEVEL == LogLevel.DEBUG
    assert settings.LOG_LEVEL.to_logging_level() == logging.DEBUG


def test_settings_log_level_invalid():
    with patch.dict(os.environ, {"LOG_LEVEL": "INVALID"}, clear=True):
        with pytest.raises(ValueError, match="validation error for Settings\nLOG_LEVEL\n"):
            Settings(_env_file=None)
