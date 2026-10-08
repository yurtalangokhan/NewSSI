"""Architectural test: one implementation of the agent runtime's shared behaviour.

``ComposedAgent`` was written to replace ``LazyLoadingAgent``. The replacement
never finished, so for a while both existed with their own copy of long-term
memory recall — the same logic twice, already drifting apart in docstrings and
log prefixes, and differing on whether a recall failure should end the turn.

Both now delegate to ``memory.recall``. These tests keep it that way: the next
person to touch recall should not have to find out there are two places.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"

RUNTIME_MODULES = {
    "LazyLoadingAgent": SRC_DIR / "agents" / "primitives" / "base.py",
    "ComposedAgent": SRC_DIR / "agent_composition" / "runtime" / "composed_agent.py",
}

#: Recall helpers that must be delegated, not reimplemented.
SHARED_HELPERS = (
    "_get_langgraph_store",
    "_build_memory_recall_event",
    "_mark_input_with_ltm_recalled",
    "_tag_output_with_recalled_memories",
    "_inject_memory_into_input",
)

#: A delegating wrapper is small. A reimplementation is not.
MAX_DELEGATION_LINES = 12


def _method(path: Path, cls: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for member in node.body:
                if (
                    isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and member.name == name
                ):
                    return member
    return None


@pytest.mark.parametrize("cls", sorted(RUNTIME_MODULES))
@pytest.mark.parametrize("helper", SHARED_HELPERS)
def test_recall_helpers_delegate_rather_than_reimplement(cls: str, helper: str):
    path = RUNTIME_MODULES[cls]
    method = _method(path, cls, helper)
    assert method is not None, f"{cls}.{helper} is missing from {path.name}"

    line_count = method.end_lineno - method.lineno + 1
    assert line_count <= MAX_DELEGATION_LINES, (
        f"{cls}.{helper} is {line_count} lines — long enough to be a second "
        f"implementation. Both runtimes must delegate to memory.recall so the "
        f"logic lives in one place."
    )


@pytest.mark.parametrize("cls", sorted(RUNTIME_MODULES))
def test_both_runtimes_import_the_shared_recall_module(cls: str):
    source = RUNTIME_MODULES[cls].read_text(encoding="utf-8")
    assert "memory.recall" in source, (
        f"{cls} no longer imports memory.recall — it has probably grown its own "
        "copy of the recall logic again."
    )


def test_the_langgraph_store_lookup_exists_in_exactly_one_place():
    """Three copies of this lookup existed, including one in MemoryPolicy."""
    definitions: list[str] = []

    for py_file in SRC_DIR.rglob("*.py"):
        if "__pycache__" in py_file.parts or py_file.name == "recall.py":
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in ("_get_langgraph_store", "resolve_langgraph_store"):
                continue
            if node.end_lineno - node.lineno + 1 > MAX_DELEGATION_LINES:
                definitions.append(f"{py_file.relative_to(SRC_DIR)}:{node.lineno} {node.name}")

    assert not definitions, (
        "The LangGraph store lookup is implemented outside memory.recall:\n"
        + "\n".join(definitions)
    )
