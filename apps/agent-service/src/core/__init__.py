"""Core package for agent-service."""

from config_manager import env

from core.observability.logger import configure_logging, get_logger

__all__ = ["configure_logging", "env", "get_logger"]
