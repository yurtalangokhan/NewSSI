"""Tests for the pure comparison mini-language shared by Router and If-Else.

The operator table proper is exercised in
tests/agents/graphs/test_conditional_router_node.py; this file covers the
``is_truthy`` operator added so the Router v1->v2 migration can carry the old
"condition is a truthy scratch key" rows across without meaning loss.
"""

from __future__ import annotations

import pytest

from domain.flows.comparison import CONDITION_OPERATORS, evaluate_comparison


def test_is_truthy_is_a_known_operator():
    assert "is_truthy" in CONDITION_OPERATORS


@pytest.mark.parametrize(
    ("left", "expected"),
    [
        ("x", True),
        ("", False),
        (None, False),
        (True, True),
        (False, False),
        (0, False),
        (1, True),
        ([], False),
        (["a"], True),
    ],
)
def test_is_truthy_ignores_the_right_operand(left, expected):
    assert evaluate_comparison("is_truthy", left, "") is expected
    assert evaluate_comparison("is_truthy", left, "anything at all") is expected
