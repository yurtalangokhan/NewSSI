from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

SERVICE_SOURCE_ROOTS = (
    REPO_ROOT / "apps" / "agent-service" / "src",
    REPO_ROOT / "apps" / "rag-service" / "langconnect",
    REPO_ROOT / "apps" / "tools-service" / "src",
    REPO_ROOT / "apps" / "user-service" / "src",
)

CENTRAL_LOGGING_MODULES = {
    REPO_ROOT / "apps" / "agent-service" / "src" / "core" / "logger.py",
    REPO_ROOT / "apps" / "agent-service" / "src" / "core" / "observability.py",
    REPO_ROOT / "apps" / "rag-service" / "langconnect" / "observability.py",
    REPO_ROOT / "apps" / "tools-service" / "src" / "core" / "observability.py",
    REPO_ROOT / "apps" / "user-service" / "src" / "core" / "observability.py",
}


def test_backend_code_uses_centralized_logger_modules() -> None:
    offenders: list[str] = []

    for source_root in SERVICE_SOURCE_ROOTS:
        for path in source_root.rglob("*.py"):
            if path in CENTRAL_LOGGING_MODULES or "scripts" in path.parts:
                continue

            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.Import) and any(
                    alias.name == "logging" for alias in node.names
                ):
                    offenders.append(str(path.relative_to(REPO_ROOT)))
                elif isinstance(node, ast.ImportFrom) and node.module == "logging":
                    offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []
