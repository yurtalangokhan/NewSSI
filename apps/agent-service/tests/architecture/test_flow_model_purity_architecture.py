"""Architectural test: ``service.flow_model`` stays a pure model.

The flow canvas vocabulary — component templates, the registry, validation,
migration, handle compatibility, data operations — is needed by two sides at
once: ``service.flows`` validates and stores specs, and ``agents.graphs.flow``
compiles them into graphs.

It earns its own bounded context by being free of I/O. That is what lets the
agent runtime depend on it without pulling in a context that talks to the
database, and it is the property these tests hold. Add a repository call here
and the agent runtime silently acquires a database dependency.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
FLOW_MODEL_DIR = SRC_DIR / "service" / "flow_model"

#: Packages the model must not reach for, and what each one would drag in.
FORBIDDEN_ROOTS = {
    "infrastructure": "a database or storage dependency",
    "integrations": "an outbound HTTP dependency",
    "api": "the transport layer",
    "agents": "the agent runtime, which depends on this model",
    "agent_composition": "the composition core",
    "fastapi": "the web framework",
    "starlette": "the web framework",
}

#: Callables that mean a module reached for persistence without importing it.
FORBIDDEN_CALLS = ("agent_definition_repository", "persona_repository", "datasource_repository")


def _iter_modules() -> list[tuple[Path, ast.AST]]:
    modules = []
    for py_file in sorted(FLOW_MODEL_DIR.rglob("*.py")):
        modules.append(
            (py_file, ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file)))
        )
    return modules


def test_the_flow_model_package_is_populated():
    """Guard the guard: an empty scan would make every test below vacuous."""
    assert FLOW_MODEL_DIR.is_dir(), f"{FLOW_MODEL_DIR} must exist"
    modules = _iter_modules()
    assert len(modules) >= 15, f"expected the flow model's modules, found {len(modules)}"


@pytest.mark.parametrize("forbidden_root", sorted(FORBIDDEN_ROOTS))
def test_flow_model_does_not_import(forbidden_root: str):
    violations: list[str] = []

    for py_file, tree in _iter_modules():
        rel_path = py_file.relative_to(SRC_DIR)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level or not node.module:
                    continue
                modules = [node.module]
            else:
                continue

            for module in modules:
                if module.split(".")[0] == forbidden_root:
                    violations.append(f"{rel_path}:{node.lineno} imports '{module}'")

    assert not violations, (
        f"service/flow_model/ must not import '{forbidden_root}' — that would give it "
        f"{FORBIDDEN_ROOTS[forbidden_root]}, and every consumer inherits it.\n"
        + "\n".join(violations)
    )


def test_flow_model_does_not_reach_for_a_repository():
    """No persistence, even through a gateway helper rather than a direct import."""
    violations: list[str] = []

    for py_file, tree in _iter_modules():
        rel_path = py_file.relative_to(SRC_DIR)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in FORBIDDEN_CALLS:
                violations.append(f"{rel_path}:{node.lineno} calls '{name}()'")

    assert not violations, "service/flow_model/ must stay free of persistence:\n" + "\n".join(
        violations
    )


def test_flow_model_does_not_depend_on_the_flow_services():
    """The dependency runs one way: services build on the model, never the reverse."""
    service_modules = {
        "service.flows",
        "service.flows.resolvers",
        "service.flows.service",
        "service.flows.audit",
        "service.flows.gating",
        "service.flows.agent_expansion",
        "service.flows.playground_service",
    }
    violations: list[str] = []

    for py_file, tree in _iter_modules():
        rel_path = py_file.relative_to(SRC_DIR)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                if node.module in service_modules:
                    violations.append(f"{rel_path}:{node.lineno} imports '{node.module}'")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in service_modules:
                        violations.append(f"{rel_path}:{node.lineno} imports '{alias.name}'")

    assert not violations, "service/flow_model/ must not import service/flows/:\n" + "\n".join(
        violations
    )
