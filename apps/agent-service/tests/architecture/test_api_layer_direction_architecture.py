"""Architectural test: Verify API Layer Direction.

Enterprise Architecture Rule:
`src/api/` is the HTTP transport / presentation adapter layer.
It MUST NOT bypass the domain/service layer to directly interact with
the underlying agent engine (`agents`) or runtime composition (`agent_composition`).
All orchestration and catalog lookups must be mediated by `service/`.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
API_DIR = SRC_DIR / "api"


def test_api_never_imports_agents_or_agent_composition():
    """Verify that NO file in src/api/ imports directly from agents or agent_composition."""
    violations: list[str] = []
    disallowed_roots = {"agents", "agent_composition"}

    for py_file in API_DIR.rglob("*.py"):
        rel_path = py_file.relative_to(SRC_DIR)
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
        except Exception as e:
            violations.append(f"{rel_path}: Failed to parse AST: {e}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0]
                    if root_pkg in disallowed_roots:
                        violations.append(f"{rel_path}:{node.lineno} imports '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_pkg = node.module.split(".")[0]
                    if root_pkg in disallowed_roots:
                        violations.append(f"{rel_path}:{node.lineno} imports from '{node.module}'")

    assert not violations, (
        "API Layer Skipping Violations found (src/api/ must not import agents or agent_composition):\n"
        + "\n".join(violations)
    )
