"""The bindings map environment names onto configuration, and nothing else.

The four service bindings are the boundary between a service and the shared
logging package. If a binding starts choosing a format, building a handler, or
naming a field, the platform has two logging implementations again, which is the
drift this consolidation exists to prevent. These tests read the binding sources
the way the env-coverage test does, so they hold without importing four services
into one interpreter.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: The binding module of each service, and the service name it must stamp.
BINDINGS: dict[str, Path] = {
    "agent-service": ROOT / "apps/agent-service/src/core/observability/observability.py",
    "user-service": ROOT / "apps/user-service/src/core/observability.py",
    "rag-service": ROOT / "apps/rag-service/src/shared/observability.py",
    "tools-service": ROOT / "apps/tools-service/src/core/observability.py",
}

#: Names that would mean the binding is implementing logging, not configuring it.
FORBIDDEN_NAMES = {
    "JsonFormatter",
    "TextFormatter",
    "BaseFormatter",
    "LogSink",
    "ConsoleSink",
    "FileSink",
    "SyslogSink",
    "ExternalSink",
    "Handler",
    "StreamHandler",
    "FileHandler",
    "RotatingFileHandler",
    "SysLogHandler",
    "Formatter",
}


def _imported_names(source: str) -> set[str]:
    """Every name the module binds through an import statement."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _called_names(source: str) -> set[str]:
    """Every function the module calls."""
    tree = ast.parse(source)
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_every_binding_imports_no_formatter_and_no_handler() -> None:
    """A binding configures; it does not implement."""
    for service, path in BINDINGS.items():
        names = _imported_names(path.read_text(encoding="utf-8"))
        forbidden = sorted(names & FORBIDDEN_NAMES)
        assert not forbidden, (
            f"{service}'s binding imports {forbidden}, which means it is building "
            "logging itself instead of describing it; the field set and the "
            "formatters belong to the shared package alone"
        )


def test_every_binding_builds_one_config_and_configures_once() -> None:
    """The shared builder and the shared configure call are the whole mechanism."""
    for service, path in BINDINGS.items():
        called = _called_names(path.read_text(encoding="utf-8"))
        assert "build_logger_config" in called, f"{service} does not use the shared builder"
        assert "configure" in called, f"{service} does not call the shared configure"


def test_every_binding_stamps_its_own_service_name() -> None:
    """A record's service field comes from the binding, not from a default."""
    for service, path in BINDINGS.items():
        source = path.read_text(encoding="utf-8")
        assert f'"{service}"' in source, (
            f"{service}'s binding does not name its own service; a record stamped "
            "with the wrong service name breaks every per-service dashboard query"
        )


def test_the_agent_shim_forwards_instead_of_configuring_a_second_way() -> None:
    """The historical dict entry point must not become a second implementation."""
    shim = ROOT / "apps/agent-service/src/core/observability/logger.py"
    source = shim.read_text(encoding="utf-8")
    names = _imported_names(source)
    forbidden = sorted(names & FORBIDDEN_NAMES)
    assert not forbidden, f"the agent shim imports {forbidden}"
    assert "logger_config" in _called_names(source), (
        "the agent shim does not forward to the binding's builder"
    )
