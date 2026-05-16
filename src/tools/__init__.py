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
import logging

from agent.registry import ToolRegistry

logger = logging.getLogger(__name__)

__all__ = ["load_all_tools"]


def load_all_tools(registry: ToolRegistry) -> None:
    """Register all tools into registry.

    Step 1 — Local tools: load modules listed in config/tools.yml.
    Step 2 — Hermes tools: if config/hermes_tools.yaml exists and hermes_path
              is reachable, register all enabled Hermes tools.
    """
    from config.settings import settings  # avoid circular import at module load

    # Step 1: local tools from tools.yml
    for module_name in settings.tools.all_tools():
        if not settings.tools.is_enabled(module_name):
            continue
        try:
            module = importlib.import_module(f"tools.{module_name}")
            if hasattr(module, "register"):
                module.register(registry)
        except ImportError:
            pass
        