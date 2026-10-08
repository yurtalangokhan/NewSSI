"""Architectural test: every ``__all__`` entry actually exists.

An ``__all__`` that names something the module does not define is a lie that
stays quiet: nothing fails until someone writes ``from x import *``, and in the
meantime the list reads as documentation of a public API that isn't there.

This has already bitten this codebase once. ``service.auth.auth_service`` kept
listing the FastAPI dependencies that had moved to ``api.dependencies``, with a
``# noqa: F822`` silencing the linter that would have said so.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"

# Alembic revisions are loaded by file path, not imported as a package.
EXCLUDED_PARTS = {"migrations", "__pycache__"}


def _modules_declaring_all() -> list[tuple[Path, list[str], set[str]]]:
    """Return (path, declared __all__, names the module actually binds)."""
    found: list[tuple[Path, list[str], set[str]]] = []

    for py_file in sorted(SRC_DIR.rglob("*.py")):
        if EXCLUDED_PARTS & set(py_file.parts):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        declared: list[str] | None = None
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(getattr(t, "id", None) == "__all__" for t in node.targets):
                continue
            if isinstance(node.value, (ast.List, ast.Tuple)):
                declared = [
                    element.value
                    for element in node.value.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                ]
        if declared is None:
            continue

        bound: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bound.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                bound.add(node.target.id)

        found.append((py_file, declared, bound))
    return found


def test_the_scan_finds_modules_to_check():
    """Guard the guard: an empty scan would make the check below vacuous."""
    modules = _modules_declaring_all()
    assert len(modules) >= 20, f"expected modules declaring __all__, found {len(modules)}"


def test_every_all_entry_is_defined_by_its_module():
    violations: list[str] = []

    for py_file, declared, bound in _modules_declaring_all():
        rel_path = py_file.relative_to(SRC_DIR)
        # A package __init__ may also re-export a submodule it never names.
        submodules = {p.stem for p in py_file.parent.iterdir() if p.suffix == ".py"}
        if py_file.name == "__init__.py":
            submodules |= {p.name for p in py_file.parent.iterdir() if p.is_dir()}
        else:
            submodules = set()

        missing = [name for name in declared if name not in bound and name not in submodules]
        if missing:
            violations.append(f"{rel_path}: __all__ names {', '.join(sorted(missing))}")

    assert not violations, (
        "__all__ must only name what the module defines or imports:\n" + "\n".join(violations)
    )


@pytest.mark.parametrize(
    "removed_port",
    [
        "Brain",
        "Perceptron",
        "BrainRequest",
        "BrainResponse",
        "PerceptionRequest",
        "PerceptionResult",
    ],
)
def test_unimplemented_composition_ports_stay_removed(removed_port: str):
    """These ports had no implementation and no caller; they must not creep back.

    A port with nothing behind it reads as a capability the platform has. The
    agent editor listed perceptrons on that basis while nothing executed them.
    """
    ports = (SRC_DIR / "agent_composition" / "domain" / "ports.py").read_text(encoding="utf-8")
    tree = ast.parse(ports)
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert removed_port not in defined, (
        f"'{removed_port}' is back in agent_composition.domain.ports with no implementation. "
        "Add the adapter that implements it in the same change, or leave it out."
    )
