"""Tools package with self-registration support.

All tools follow a unified registration pattern:
    from agent import ToolRegistry
    from tools import load_all_tools

    registry = ToolRegistry()
    load_all_tools(registry)

Or load individual tools:
    from tools.calculator import register as register_calculator
    register_calculator(registry)
"""

import importlib
from agent.registry import ToolRegistry

__all__ = ["load_all_tools"]


def load_all_tools(registry: ToolRegistry) -> None:
    """Register all available tools with the given registry.

    Discovers and loads all tool modules in this package.
    Each module should have a `register(registry)` function.
    """
    tool_modules = ["calculator", "file_ops", "file_parser", "skill_tool"]

    for module_name in tool_modules:
        try:
            module = importlib.import_module(f"tools.{module_name}")
            if hasattr(module, "register"):
                module.register(registry)
        except ImportError as e:
            pass