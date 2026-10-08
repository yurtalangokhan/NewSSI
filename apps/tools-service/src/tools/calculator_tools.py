"""
Calculator Tools Category.
Provides safe mathematical expression evaluation.

safe_eval walks an explicit AST node whitelist instead of calling eval():
eval() with an empty __builtins__ still allows attribute access on any
object reachable from the expression (spec TS-11's ().__class__.__bases__)
and places no bound on the ** operator, so "9**9**9" alone exhausts CPU
and memory before the character blocklist this replaces ever gets a
chance to matter.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
import math
import operator
from typing import Any

from error_contract import UnsafeExpressionError
from localization import t

from ..core.base import BaseToolCategory
from ..core.schema import ShortText
from .response import tool_error_message

MAX_EXPONENT = 1024
MAX_EXPRESSION_LENGTH = 512


_BINARY_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
}
_CONSTANTS = {"pi": math.pi, "e": math.e}


def _evaluate(node: ast.AST) -> float | int:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, int | float) and not isinstance(node.value, bool):
            return node.value
        raise UnsafeExpressionError("Only numeric literals are allowed")

    if isinstance(node, ast.BinOp):
        op = _BINARY_OPS.get(type(node.op))
        if op is None:
            raise UnsafeExpressionError("Operator is not allowed")
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise UnsafeExpressionError(f"Exponent larger than {MAX_EXPONENT} is not allowed")
        return op(left, right)

    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise UnsafeExpressionError("Unary operator is not allowed")
        return op(_evaluate(node.operand))

    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise UnsafeExpressionError(f"Unknown name {node.id!r}")

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            raise UnsafeExpressionError("Only the allowed math functions may be called")
        if node.keywords:
            raise UnsafeExpressionError("Keyword arguments are not allowed")
        return _FUNCTIONS[node.func.id](*(_evaluate(a) for a in node.args))

    raise UnsafeExpressionError(f"Expression element {type(node).__name__} is not allowed")


def safe_eval(expression: str) -> float | int:
    """Evaluate a plain arithmetic expression. Raises UnsafeExpressionError for
    anything else -- including syntactically valid Python that isn't
    arithmetic (attribute access, comprehensions, lambdas, calls to
    anything but the fixed math-function whitelist)."""
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise UnsafeExpressionError("Expression is too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise UnsafeExpressionError("Expression is not valid arithmetic") from exc
    return _evaluate(tree.body)


class CalculatorTools(BaseToolCategory):
    """Mathematical calculation tools."""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return t("categories.calculator.description", default="Safe mathematical expression evaluation")

    @property
    def label(self) -> str:
        return t("categories.calculator.label", default="Calculator")

    def register_tools(self, mcp: Any) -> None:
        """Register all calculator tools with MCP."""

        @mcp.tool()
        def calculate(expression: ShortText) -> str:
            """
            Evaluate a mathematical expression safely.

            Args:
                expression: Mathematical expression (e.g., "2 + 2 * 3", "sqrt(16)", "sin(3.14159/2)")

            Returns:
                The result of the calculation
            """
            try:
                return str(safe_eval(expression))
            except (ValueError, ArithmeticError, TypeError) as e:
                # ValueError covers UnsafeExpressionError (a disallowed
                # expression shape) and domain errors like math.sqrt(-1);
                # ArithmeticError covers ZeroDivisionError and OverflowError
                # from an otherwise-valid expression.
                return t("calculator.calculation_error", error=tool_error_message(e))
