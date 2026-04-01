"""Core module - provides backward compatibility.

This module re-exports core modules.
"""

# Re-export settings
# Re-export get_model
from core.llm import get_model
from core.settings import settings

__all__ = ["settings", "get_model"]
