"""Identifiers that name a person do not go into the log stream.

Usernames in this deployment are the user's email address (see
``UserService.update_user``, which sets ``payload["username"]`` from
``filtered["email"]``). Logging them puts personal data into whatever the log
pipeline ships to -- at INFO for account creation. Nothing downstream needs
the value: the correlation ids already in these messages point at the
record.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

#: Names that identify a person rather than a record.
PII_NAMES = {
    "email",
    "normalized_email",
    "username",
    "normalized_username",
    "first_name",
    "last_name",
    "full_name",
}

LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}

#: Wrapping an identifier in this is the sanctioned way to log it.
SANITIZER = "pseudonym"


def _bare_pii(node: ast.AST) -> list[str]:
    """PII names reachable in *node* without passing through the sanitizer."""
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == SANITIZER:
            return []

    found: list[str] = []
    if isinstance(node, ast.Name) and node.id in PII_NAMES:
        found.append(node.id)
    if isinstance(node, ast.Attribute) and node.attr in PII_NAMES:
        found.append(node.attr)
    for child in ast.iter_child_nodes(node):
        found.extend(_bare_pii(child))
    return found


def _log_calls_with_pii(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in LOG_METHODS:
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "logger"):
            continue
        for arg in node.args:
            found.extend((node.lineno, name) for name in _bare_pii(arg))
    return found


@pytest.mark.parametrize(
    "relative",
    ["service/user_service.py"],
)
def test_no_personal_identifier_is_logged(relative: str):
    path = SRC / relative
    offenders = _log_calls_with_pii(path)

    assert offenders == [], f"{relative} logs a personal identifier at: " + ", ".join(
        f"line {line} ({name})" for line, name in offenders
    )


def test_the_whole_service_is_clean():
    offenders = {
        str(path.relative_to(SRC)): _log_calls_with_pii(path)
        for path in SRC.rglob("*.py")
        if _log_calls_with_pii(path)
    }

    assert offenders == {}
