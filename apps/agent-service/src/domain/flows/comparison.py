"""Pure comparison primitives for the ``ConditionalRouter`` ("If-Else") node.

A faithful port of Langflow's
``ConditionalRouterComponent.evaluate_condition``: a **fixed** operator set
applied to two strings, never ``eval()``. A string that looks like code is
just a literal operand.

Kept dependency-free (stdlib only) so both the flow validator — which is
contractually pure, no I/O — and the LangGraph compiler can import it.
"""

from __future__ import annotations

import re

# Canonical operator identifiers. Shared by the component template
# (``operator`` options), the validator (allowed-value check) and the
# compiler (routing function). Order is the order shown in the canvas
# dropdown.
CONDITION_OPERATORS: tuple[str, ...] = (
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "regex",
    "less_than",
    "less_than_or_equal",
    "greater_than",
    "greater_than_or_equal",
    "is_truthy",
)

_NUMERIC_OPERATORS = frozenset(
    {"less_than", "less_than_or_equal", "greater_than", "greater_than_or_equal"}
)


def evaluate_comparison(
    operator: str,
    left: object,
    right: object,
    *,
    case_sensitive: bool = True,
) -> bool:
    """Return whether ``left <operator> right`` holds.

    - Numeric operators coerce both sides with ``float()``; a non-numeric
      operand makes the comparison ``False`` (never raises).
    - ``regex`` treats ``right`` as the pattern and is anchored at the start
      of ``left`` (``re.match`` semantics, matching Langflow). An invalid
      pattern is ``False``. ``case_sensitive`` does not apply to ``regex``.
    - Every other operator is a plain string comparison, lower-cased on both
      sides when ``case_sensitive`` is false.
    - ``is_truthy`` ignores ``right`` and reports ``bool(left)`` on the raw
      value (not its string form), so a ``False`` / ``0`` / empty operand
      stays falsy. It is what the Router v1->v2 migration maps the old
      "condition is a truthy scratch key" rows onto.
    - An unknown operator is ``False`` — a routing function must not raise.
    """
    if operator == "is_truthy":
        return bool(left)

    left_str = "" if left is None else str(left)
    right_str = "" if right is None else str(right)

    if operator in _NUMERIC_OPERATORS:
        try:
            left_num = float(left_str)
            right_num = float(right_str)
        except (TypeError, ValueError):
            return False
        if operator == "less_than":
            return left_num < right_num
        if operator == "less_than_or_equal":
            return left_num <= right_num
        if operator == "greater_than":
            return left_num > right_num
        return left_num >= right_num  # greater_than_or_equal

    if operator == "regex":
        try:
            return re.match(right_str, left_str) is not None
        except re.error:
            return False

    if not case_sensitive:
        left_str = left_str.lower()
        right_str = right_str.lower()

    if operator == "equals":
        return left_str == right_str
    if operator == "not_equals":
        return left_str != right_str
    if operator == "contains":
        return right_str in left_str
    if operator == "not_contains":
        return right_str not in left_str
    if operator == "starts_with":
        return left_str.startswith(right_str)
    if operator == "ends_with":
        return left_str.endswith(right_str)
    return False
