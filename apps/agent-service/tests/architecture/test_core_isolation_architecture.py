"""Architectural test: Verify strict Core Layer Isolation.

Enterprise Architecture Rule:
`src/core/` is the foundational infrastructure layer. It MUST NOT import from any
higher-level business or application layer:
- `service`
- `schemas`
- `agents`
- `controller`
- `api`
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
CORE_DIR = SRC_DIR / "core"

FORBIDDEN_PREFIXES = ("service", "schemas", "agents", "controller", "api", "infrastructure")


def _get_imports(py_file: Path) -> list[str]:
    content = py_file.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(py_file))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    return imported


def test_core_has_zero_external_dependencies():
    """Verify that NO file in src/core/ imports from any higher layer."""
    violations: list[str] = []

    for py_file in CORE_DIR.rglob("*.py"):
        rel_path = py_file.relative_to(SRC_DIR)
        imports = _get_imports(py_file)
        for imp in imports:
            root_pkg = imp.split(".")[0]
            if root_pkg in FORBIDDEN_PREFIXES:
                violations.append(f"{rel_path} imports '{imp}'")

    assert not violations, "Core Isolation Violations found in src/core/:\n" + "\n".join(violations)


def test_idempotency_principal_is_isolated():
    """Verify idempotency_principal.py only uses core and standard libraries."""
    file_path = CORE_DIR / "http" / "idempotency_principal.py"
    assert file_path.exists()
    imports = _get_imports(file_path)
    for imp in imports:
        root_pkg = imp.split(".")[0]
        assert root_pkg not in FORBIDDEN_PREFIXES, f"idempotency_principal.py imports '{imp}'"
    # The principal is the identity Gateway established. Re-deriving it here (a
    # token decode, a header parse) would be a second answer to a question the
    # gateway boundary already owns.
    assert any(imp.split(".")[0] == "security" for imp in imports), (
        "idempotency_principal.py must resolve the caller through the security package"
    )


def test_persona_repo_does_not_import_schemas():
    """Verify persona_repo.py does not import schemas."""
    file_path = SRC_DIR / "infrastructure" / "db" / "repositories" / "persona_repo.py"
    assert file_path.exists()
    imports = _get_imports(file_path)
    for imp in imports:
        root_pkg = imp.split(".")[0]
        assert root_pkg != "schemas", f"persona_repo.py imports '{imp}'"


def test_datasource_repo_does_not_import_agents():
    """Verify datasource_repo.py does not import agents."""
    file_path = SRC_DIR / "infrastructure" / "db" / "repositories" / "datasource_repo.py"
    assert file_path.exists()
    imports = _get_imports(file_path)
    for imp in imports:
        root_pkg = imp.split(".")[0]
        assert root_pkg != "agents", f"datasource_repo.py imports '{imp}'"
