"""Architectural test: one constant name, one value, across the service.

Two modules declaring the same ``UPPER_SNAKE_CASE`` name with different literal
values is how the drift in this codebase started::

    PASSTHROUGH_NODE_TYPES   builder.py (Router, While)   message_flow.py (Foreach, RunFlow)
    AGENT_TO_PERSONA_ID      personas/constants.py (nine) session_service.py (two)

Neither copy failed a test on its own — each agreed with the module that read it —
so the disagreement only surfaced as behaviour that depended on which module
asked. ``flow/message_flow`` silently walked past nodes the stream refused to hide, and
the two persona maps disagreed about which agent persona 1 is.

The check is deliberately blunt: same name, different literal value, two modules,
fail. Same-value duplicates are *not* reported — two modules may legitimately both
say ``TIMEOUT = 30`` — because the defect being guarded against is the
disagreement, not the repetition.

Not-literal values (comprehensions, calls to unknown names) are skipped: there is
no single value to compare, and every case that motivated this test bound a
literal.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"

#: Alembic revisions are loaded by file path, not imported as a package.
EXCLUDED_PARTS = {"migrations", "__pycache__"}

#: Sentinel for a constant whose value cannot be read statically.
_UNRESOLVED = object()

#: Names permitted to differ between modules, each with the reason it must.
ALLOWED_DIVERGENCE = {
    "DEFAULT_USER_AGENT": (
        "playwright_fetch presents a desktop-browser UA so bot walls let the "
        "fetch through; atlas_web_crawler introduces itself honestly as "
        "ATLASWebCrawler. The two values differing is the point."
    ),
}


def _literal_value(node: ast.AST) -> object:
    """Return the literal ``node`` is bound to, or ``_UNRESOLVED``.

    ``frozenset({...})`` and other single-argument wrappers are unwrapped, so the
    two shapes this codebase uses for a constant set stay comparable.
    """
    target = node
    if isinstance(node, ast.Call) and len(node.args) == 1 and not node.keywords:
        target = node.args[0]
    try:
        return ast.literal_eval(target)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return _UNRESOLVED


def _module_constants(path: Path) -> dict[str, object]:
    """Module-level ``UPPER_SNAKE_CASE`` names and their literal values."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, object] = {}

    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            if len(targets) != 1:
                continue
            name = targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        else:
            continue

        if not name.isupper() or node.value is None:
            continue
        value = _literal_value(node.value)
        if value is _UNRESOLVED:
            continue
        values[name] = value

    return values


def _divergent_names(root: Path) -> dict[str, dict[str, object]]:
    """Constant names bound to more than one value, keyed by module."""
    holders: dict[str, dict[str, object]] = defaultdict(dict)

    for path in sorted(root.rglob("*.py")):
        if EXCLUDED_PARTS & set(path.parts):
            continue
        for name, value in _module_constants(path).items():
            holders[name][str(path.relative_to(root))] = value

    return {
        name: modules
        for name, modules in holders.items()
        if len(modules) > 1 and len({repr(value) for value in modules.values()}) > 1
    }


def _render(divergent: dict[str, dict[str, object]]) -> str:
    return "\n".join(
        f"  {name}: "
        + ", ".join(f"{module}={value!r}" for module, value in sorted(modules.items()))
        for name, modules in sorted(divergent.items())
    )


def test_constant_names_carry_one_value_across_modules():
    divergent = {
        name: modules
        for name, modules in _divergent_names(SRC_DIR).items()
        if name not in ALLOWED_DIVERGENCE
    }

    assert not divergent, (
        "The same constant name is bound to different values in different modules. "
        "Give it a single owner and import it, or rename one of the two:\n" + _render(divergent)
    )


def test_every_allowlisted_divergence_is_still_real():
    """A stale entry silently widens the rule it was added to narrow."""
    divergent = _divergent_names(SRC_DIR)
    stale = sorted(name for name in ALLOWED_DIVERGENCE if name not in divergent)

    assert not stale, (
        f"These names no longer differ between modules — remove them from "
        f"ALLOWED_DIVERGENCE: {stale}"
    )


def test_the_scanner_actually_detects_divergence(tmp_path: Path):
    """Guard the guard: a check that cannot fail protects nothing."""
    (tmp_path / "one.py").write_text('NODE_TYPES = ("A", "B")\n', encoding="utf-8")
    (tmp_path / "two.py").write_text('NODE_TYPES = ("A", "C")\n', encoding="utf-8")

    assert "NODE_TYPES" in _divergent_names(tmp_path)

    # Same value on both sides is repetition, not divergence.
    (tmp_path / "two.py").write_text('NODE_TYPES = ("A", "B")\n', encoding="utf-8")

    assert "NODE_TYPES" not in _divergent_names(tmp_path)
