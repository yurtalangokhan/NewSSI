"""calculate must not use eval(). Spec TS-11.

eval() with an empty __builtins__ still exposes attribute access and an
unbounded ** operator: "9**9**9" alone is enough to exhaust CPU and
memory. An AST walk over an explicit node whitelist closes both.
"""

import time

import pytest

from src.tools.calculator_tools import UnsafeExpressionError, safe_eval


@pytest.mark.parametrize(
    ("expression", "expected"),
    [("2 + 3", 5), ("10 / 4", 2.5), ("2 ** 8", 256), ("sqrt(16)", 4.0)],
)
def test_arithmetic_is_evaluated(expression, expected):
    assert safe_eval(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "open('/etc/passwd').read()",
        "().__class__.__bases__",
        "pi.__class__",
        "[x for x in range(10)]",
        "lambda: 1",
    ],
)
def test_non_arithmetic_expressions_are_rejected(expression):
    with pytest.raises(UnsafeExpressionError):
        safe_eval(expression)


def test_exponent_bomb_is_rejected_quickly():
    started = time.monotonic()
    with pytest.raises(UnsafeExpressionError):
        safe_eval("9**9**9")
    assert time.monotonic() - started < 1.0


def test_large_exponent_operand_is_rejected():
    with pytest.raises(UnsafeExpressionError):
        safe_eval("2 ** 100000")


def test_overly_long_expression_is_rejected():
    with pytest.raises(UnsafeExpressionError):
        safe_eval("1+" * 1000 + "1")
