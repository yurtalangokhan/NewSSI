"""Architectural test: Verify Service Layer Direction.

Enterprise Architecture Rule:
`src/service/` holds the business logic layer. `src/api/` is the transport
adapter: it parses requests, resolves auth dependencies and serialises
responses. Under Clean Architecture the dependency points inward only —
`api` may import `service`, never the other way round.

`controller` is the layer `service` replaced. Nothing may import it, and it
must not come back under another name, so the rule covers both packages.

A service that needs something from a request (a bearer token, an uploaded
file) takes it as a plain argument; extracting it from the transport is the
route's job.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
SERVICE_DIR = SRC_DIR / "service"

# Packages the service layer must never depend on, and why.
FORBIDDEN_ROOTS = {
    "api": "the API layer is an adapter above service — dependencies point inward",
    "controller": "the controller layer was removed; its logic belongs in service",
}


def _imported_roots(tree: ast.AST) -> list[tuple[int, str, str]]:
    """Return (lineno, root_package, full_module) for every import in *tree*."""
    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name.split(".")[0], alias.name))
        elif isinstance(node, ast.ImportFrom):
            # Relative imports stay inside the package; they cannot escape it.
            if node.level or not node.module:
                continue
            found.append((node.lineno, node.module.split(".")[0], node.module))
    return found


@pytest.mark.parametrize("forbidden_root", sorted(FORBIDDEN_ROOTS))
def test_service_never_imports(forbidden_root: str) -> None:
    """No module under src/service/ may import the forbidden package."""
    violations: list[str] = []

    for py_file in SERVICE_DIR.rglob("*.py"):
        rel_path = py_file.relative_to(SRC_DIR)
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as exc:  # pragma: no cover - a parse failure is itself a failure
            violations.append(f"{rel_path}: Failed to parse AST: {exc}")
            continue

        for lineno, root, module in _imported_roots(tree):
            if root == forbidden_root:
                violations.append(f"{rel_path}:{lineno} imports '{module}'")

    assert not violations, (
        f"src/service/ must not import '{forbidden_root}' — "
        f"{FORBIDDEN_ROOTS[forbidden_root]}.\n" + "\n".join(violations)
    )


def test_service_layer_does_not_import_the_web_framework() -> None:
    """No module under src/service/ may import FastAPI or Starlette.

    An ``HTTPException`` raised below the route layer decides a status code in
    a place that cannot know whether the caller is a request at all. Services
    raise ``core.exceptions`` errors instead; the API layer's registered
    handler turns those into responses.
    """
    violations: list[str] = []
    web_frameworks = {"fastapi", "starlette"}

    for py_file in SERVICE_DIR.rglob("*.py"):
        rel_path = py_file.relative_to(SRC_DIR)
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:  # pragma: no cover - covered by the import test above
            continue

        for lineno, root, module in _imported_roots(tree):
            if root in web_frameworks:
                violations.append(f"{rel_path}:{lineno} imports '{module}'")

    assert not violations, (
        "src/service/ must not import a web framework — raise core.exceptions "
        "errors and let the API layer render them.\n" + "\n".join(violations)
    )


def test_service_layer_does_not_take_fastapi_request_objects() -> None:
    """Service functions take plain values, not FastAPI ``Request`` objects.

    A ``Request`` parameter means the transport leaked one layer down: the
    service can then only be called from inside a live HTTP request, and its
    tests have to fabricate one.
    """
    violations: list[str] = []

    for py_file in SERVICE_DIR.rglob("*.py"):
        rel_path = py_file.relative_to(SRC_DIR)
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:  # pragma: no cover - covered by the import test above
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = node.args
            for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
                if arg.annotation is None:
                    continue
                annotation = ast.unparse(arg.annotation)
                if "Request" in annotation.split("[")[0].replace("|", " ").split():
                    violations.append(
                        f"{rel_path}:{node.lineno} {node.name}({arg.arg}: {annotation})"
                    )

    assert not violations, (
        "src/service/ must not accept FastAPI Request objects; "
        "pass the value the service actually needs instead.\n" + "\n".join(violations)
    )


def test_agent_composition_never_imports_the_service_layer() -> None:
    """The composition core stays behind its ports.

    ``agent_composition`` is the hexagonal core: it defines the ports (tool
    gateway, runtime policy, executable agent) that adapters implement. Reaching
    into ``service`` for a concrete collaborator would make those ports
    decorative, so the dependency runs the other way only.
    """
    composition_dir = SRC_DIR / "agent_composition"
    violations: list[str] = []

    for py_file in composition_dir.rglob("*.py"):
        rel_path = py_file.relative_to(SRC_DIR)
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as exc:  # pragma: no cover - a parse failure is a failure
            violations.append(f"{rel_path}: Failed to parse AST: {exc}")
            continue

        for lineno, root, module in _imported_roots(tree):
            if root in {"service", "api", "controller"}:
                violations.append(f"{rel_path}:{lineno} imports '{module}'")

    assert not violations, (
        "agent_composition must depend on its ports, not on the service or API "
        "layers.\n" + "\n".join(violations)
    )
