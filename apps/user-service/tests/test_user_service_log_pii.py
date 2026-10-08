"""UserService's Keycloak-sync logs must not carry email or full name.

create_user/update_user/set_user_active used to log the user's email and
first/last name at INFO level on every create, profile update, and
activation toggle -- personal data sitting in a log stream that is typically
retained far longer, and read by far more people, than the database itself.
keycloak_id (and, for creation, the username already given at the API
boundary) is enough to correlate a log line to a user record.
"""

from __future__ import annotations

import ast
import inspect

from src.service import user_service

_FORBIDDEN_TERMS = ("normalized_email", "email", "firstName", "lastName", "first_name", "last_name")


def _logger_calls(tree: ast.AST) -> list[ast.Call]:
    calls = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "logger"
            and node.func.attr in {"info", "debug", "warning", "error", "exception"}
        ):
            calls.append(node)
    return calls


def test_no_log_call_references_email_or_name_fields():
    source = inspect.getsource(user_service)
    tree = ast.parse(source)
    calls = _logger_calls(tree)
    assert calls, "expected at least one logger call in user_service.py"

    for call in calls:
        rendered = ast.unparse(call)
        for term in _FORBIDDEN_TERMS:
            assert term not in rendered, f"PII term {term!r} found in log call: {rendered}"
