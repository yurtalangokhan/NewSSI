"""Core module - provides backward compatibility.

This module re-exports core modules.
"""

from core.llm import get_model
from core.logger import configure_logging, get_logger
from core.settings import settings

__all__ = ["settings", "get_model", "get_logger", "configure_logging"]
