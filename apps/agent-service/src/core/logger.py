"""
Centralized Logging Module.

Professional logging with:
- Configurable log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Text and JSON output formats
- Console and file output with rotation
- Structured logging with context

Usage:
    from core.logger import get_logger

    logger = get_logger(__name__)
    logger.info("Service started", extra={"port": 8080})
    logger.error("Connection failed", extra={"error": str(e)})
"""

import logging
import os
import sys
from datetime import datetime
from enum import StrEnum
from logging.handlers import RotatingFileHandler
from typing import Any
from uuid import uuid4

from core.env import env


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(StrEnum):
    TEXT = "text"
    JSON = "json"


class LogOutput(StrEnum):
    CONSOLE = "console"
    FILE = "file"
    BOTH = "both"


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if hasattr(record, "extra"):
            log_data.update(record.extra)

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if record.args:
            log_data["args"] = [str(arg) for arg in record.args]

        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Text formatter with colors and structured output."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",
    }

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "") if self.use_colors else ""
        reset = self.COLORS["RESET"] if self.use_colors else ""

        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level = f"{color}{record.levelname:<8}{reset}"
        name = f"{record.name:<40}"
        message = record.getMessage()

        extra_fields = ""
        if hasattr(record, "extra"):
            extra_parts = [f"{k}={v}" for k, v in record.extra.items()]
            extra_fields = f" | {' '.join(extra_parts)}"

        if record.exc_info:
            return f"{timestamp} | {level} | {name} | {message}{extra_fields}\n{self.formatException(record.exc_info)}"

        return f"{timestamp} | {level} | {name} | {message}{extra_fields}"


class ContextFilter(logging.Filter):
    """Add context to all log records."""

    def __init__(self, extra: dict[str, Any] | None = None):
        super().__init__()
        self.extra = extra or {}

    def filter(self, record: logging.LogRecord):
        if not hasattr(record, "extra"):
            record.extra = {}
        record.extra.update(self.extra)
        record.extra.setdefault("request_id", str(uuid4())[:8])
        return True


class LoggerFactory:
    """Factory for creating configured loggers."""

    _initialized = False
    _log_level = logging.INFO
    _log_format = LogFormat.TEXT
    _log_output = LogOutput.CONSOLE
    _log_file_path = "/var/log/agent-service/app.log"
    _log_max_bytes = 10 * 1024 * 1024
    _log_backup_count = 5

    @classmethod
    def configure(cls, config: dict[str, Any] | None = None):
        """Configure logging from dict or env vars."""
        config = config or {}

        level_str = config.get("LOG_LEVEL") or env.LOG_LEVEL
        try:
            cls._log_level = getattr(logging, level_str.upper())
        except AttributeError:
            cls._log_level = logging.INFO

        fmt_str = config.get("LOG_FORMAT") or env.LOG_FORMAT
        cls._log_format = LogFormat(fmt_str.lower())

        output_str = config.get("LOG_OUTPUT") or env.LOG_OUTPUT
        cls._log_output = LogOutput(output_str.lower())

        cls._log_file_path = config.get("LOG_FILE_PATH") or env.LOG_FILE_PATH

        cls._log_max_bytes = int(config.get("LOG_MAX_SIZE") or env.LOG_MAX_SIZE)
        cls._log_backup_count = int(config.get("LOG_BACKUP_COUNT") or env.LOG_BACKUP_COUNT)

        cls._initialized = True

    @classmethod
    def get_logger(cls, name: str, extra_context: dict[str, Any] | None = None) -> logging.Logger:
        """Get a configured logger instance."""
        logger = logging.getLogger(name)

        if not cls._initialized:
            cls.configure()

        if logging.getLogger().handlers:
            logger.setLevel(cls._log_level)
            logger.propagate = True
            return logger

        if logger.handlers:
            return logger

        logger.setLevel(cls._log_level)
        logger.propagate = False

        context_filter = ContextFilter(extra_context)

        if cls._log_output in (LogOutput.CONSOLE, LogOutput.BOTH):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(cls._log_level)
            if cls._log_format == LogFormat.JSON:
                console_handler.setFormatter(JsonFormatter())
            else:
                console_handler.setFormatter(TextFormatter(use_colors=True))
            console_handler.addFilter(context_filter)
            logger.addHandler(console_handler)

        if cls._log_output in (LogOutput.FILE, LogOutput.BOTH):
            log_dir = os.path.dirname(cls._log_file_path)
            if log_dir and not os.path.exists(log_dir):
                try:
                    os.makedirs(log_dir, exist_ok=True)
                except OSError:
                    pass

            try:
                file_handler = RotatingFileHandler(
                    cls._log_file_path,
                    maxBytes=cls._log_max_bytes,
                    backupCount=cls._log_backup_count,
                )
                file_handler.setLevel(cls._log_level)
                if cls._log_format == LogFormat.JSON:
                    file_handler.setFormatter(JsonFormatter())
                else:
                    file_handler.setFormatter(TextFormatter(use_colors=False))
                file_handler.addFilter(context_filter)
                logger.addHandler(file_handler)
            except OSError:
                pass

        return logger


def get_logger(name: str, extra_context: dict[str, Any] | None = None) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Logger name (typically __name__)
        extra_context: Additional context to add to all log records

    Returns:
        Configured logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Service started", extra={"port": 8080})
    """
    return LoggerFactory.get_logger(name, extra_context)


def configure_logging(config: dict[str, Any] | None = None):
    """Configure logging system. Call this at application startup."""
    LoggerFactory.configure(config)
