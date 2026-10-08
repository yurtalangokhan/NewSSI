"""Architectural test: Verify Controller Elimination and Single-Door Service Access.

Enterprise Architecture Rule (SOTA FastAPI 3-Tier):
In FastAPI, `APIRouter` endpoint functions serve as the Presentation / Controller layer.
The legacy `src/controller/` layer is completely eliminated.
All business logic belongs in `src/service/`.
`src/api/` communicates strictly with `src/service/` (plus `core`, `schemas`, `integrations`).
Zero `*Controller` classes or `get_*_controller` aliases exist in `src/service/`.
`tests/controller/` does not exist; all unit/integration tests belong in `tests/service/`.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = REPO_ROOT / "src"
TESTS_DIR = REPO_ROOT / "tests"
API_DIR = SRC_DIR / "api"
SERVICE_DIR = SRC_DIR / "service"
CONTROLLER_DIR = SRC_DIR / "controller"
TESTS_CONTROLLER_DIR = TESTS_DIR / "controller"


def test_controller_directory_does_not_exist():
    """Verify that the legacy src/controller directory has been completely eliminated."""
    assert not CONTROLLER_DIR.exists(), (
        f"Legacy controller directory exists at {CONTROLLER_DIR}. "
        "All controllers must be migrated to src/service/ and the directory removed."
    )


def test_tests_controller_directory_does_not_exist():
    """Verify that the legacy tests/controller directory has been completely eliminated."""
    assert not TESTS_CONTROLLER_DIR.exists(), (
        f"Legacy tests/controller directory exists at {TESTS_CONTROLLER_DIR}. "
        "All controller tests must be migrated to tests/service/ and the directory removed."
    )


def test_no_src_module_imports_controller():
    """Verify that NO module in src/ imports from controller."""
    violations: list[str] = []

    for py_file in SRC_DIR.rglob("*.py"):
        rel_path = py_file.relative_to(SRC_DIR)
        if rel_path.parts[0] == "controller":
            continue

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
                    if root_pkg == "controller":
                        violations.append(f"{rel_path}:{node.lineno} imports '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_pkg = node.module.split(".")[0]
                    if root_pkg == "controller":
                        violations.append(f"{rel_path}:{node.lineno} imports from '{node.module}'")

    msg = "\n".join(violations)
    assert not violations, f"Forbidden controller imports found in src/:\n{msg}"


def test_no_controller_classes_or_aliases_in_service():
    """Verify that NO class or alias ending with Controller is defined in src/service/."""
    violations: list[str] = []

    for py_file in SERVICE_DIR.rglob("*.py"):
        rel_path = py_file.relative_to(SRC_DIR)
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
        except Exception as e:
            violations.append(f"{rel_path}: Failed to parse AST: {e}")
            continue

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                if node.name.endswith("Controller"):
                    violations.append(f"{rel_path}:{node.lineno} defines class '{node.name}'")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.endswith("Controller"):
                        violations.append(f"{rel_path}:{node.lineno} defines alias '{target.id}'")

    msg = "\n".join(violations)
    assert not violations, f"Forbidden Controller classes or aliases found in src/service/:\n{msg}"


def test_no_get_controller_functions_or_aliases_in_service():
    """Verify that NO get_*_controller function or alias is defined in src/service/."""
    violations: list[str] = []

    for py_file in SERVICE_DIR.rglob("*.py"):
        rel_path = py_file.relative_to(SRC_DIR)
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
        except Exception as e:
            violations.append(f"{rel_path}: Failed to parse AST: {e}")
            continue

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if "controller" in node.name.lower():
                    violations.append(f"{rel_path}:{node.lineno} defines function '{node.name}'")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and "controller" in target.id.lower():
                        violations.append(f"{rel_path}:{node.lineno} defines alias '{target.id}'")

    msg = "\n".join(violations)
    assert not violations, (
        f"Forbidden get_*_controller functions or aliases found in src/service/:\n{msg}"
    )


def test_no_api_routes_define_get_controller():
    """Verify that NO route in src/api/routes/ defines _get_controller."""
    violations: list[str] = []
    routes_dir = API_DIR / "routes"

    for py_file in routes_dir.glob("*.py"):
        rel_path = py_file.relative_to(SRC_DIR)
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
        except Exception as e:
            violations.append(f"{rel_path}: Failed to parse AST: {e}")
            continue

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "_get_controller":
                    violations.append(f"{rel_path}:{node.lineno} defines function '{node.name}'")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "_get_controller":
                        violations.append(f"{rel_path}:{node.lineno} defines alias '{target.id}'")

    msg = "\n".join(violations)
    assert not violations, f"Forbidden _get_controller found in src/api/routes/:\n{msg}"
