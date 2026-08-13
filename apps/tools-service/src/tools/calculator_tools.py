"""
Calculator Tools Category.
Provides safe mathematical expression evaluation.
"""

import math
from typing import Any

from i18n import t

from ..core.base import BaseToolCategory


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
        def calculate(expression: str) -> str:
            """
            Evaluate a mathematical expression safely.

            Args:
                expression: Mathematical expression (e.g., "2 + 2 * 3", "sqrt(16)", "sin(3.14159/2)")

            Returns:
                The result of the calculation
            """
            # Safe math functions
            safe_dict = {
                "abs": abs,
                "round": round,
                "min": min,
                "max": max,
                "sum": sum,
                "pow": pow,
                "sqrt": math.sqrt,
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "log": math.log,
                "log10": math.log10,
                "exp": math.exp,
                "pi": math.pi,
                "e": math.e,
            }

            try:
                # Remove any potentially dangerous characters
                allowed = set("0123456789+-*/.() ,")
                for char in expression:
                    if char not in allowed and not char.isalpha():
                        return t("calculator.invalid_character", char=char)

                result = eval(expression, {"__builtins__": {}}, safe_dict)
                return str(result)
            except Exception as e:
                return t("calculator.calculation_error", error=str(e))
