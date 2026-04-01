"""Shared fixtures for domain and API tests."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_env():
    """Fixture to ensure environment is clean for each test."""
    import os

    with patch.dict(os.environ, {}, clear=True):
        yield


@pytest.fixture
def mock_settings(mock_env):
    """Fixture to ensure settings are clean for each test."""
    with patch("core.settings") as mock_settings:
        mock_settings.AVAILABLE_MODELS = set()
        mock_settings.DEFAULT_MODEL = None
        mock_settings.LANGFUSE_TRACING = False
        yield mock_settings
