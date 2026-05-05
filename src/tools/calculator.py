"""Example calculator tool demonstrating self-registration."""

import operator
from typing import Callable

from agent import tool_result, tool_error

OPS = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "**": operator.pow,
}

def _handle(args: dict) -> str:
    """Handle calculator calls."""
    expr = args.get("expression", "")
    if not expr:
        return tool_error("expression is required")

    try:
        allowed_chars = set("0123456789.+-*/**() ")
        if not all(c in allowed_chars for c in expr.replace(" ", "")):
            return tool_error("Invalid characters in expression")

        result = eval(expr, {"__builtins__": {}}, OPS)
        return tool_result(result=result)
    except Exception as e:
        return tool_error(str(e))


# Self-registration (called at module import time)
def register(registry):
    registry.register(
        name="calculator",
        schema={
            "name": "calculator",
            "description": "Evaluate a simple math expression like '2+2' or '3*4'",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression like '2+2' or '3*4'",
                    }
                },
                "required": ["expression"],
            },
        },
        handler=_handle,
    )


register_calculator = register

__all__ = ["register", "register_calculator"]
