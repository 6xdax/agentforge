"""Thread-safe tool registry with self-registration support."""

import asyncio
import inspect
import json
import threading
from typing import Callable, Optional

from .errors import ToolNotFoundError


class ToolEntry:
    """Metadata for a registered tool. Uses __slots__ for memory efficiency."""
    __slots__ = ("name", "schema", "handler", "description")

    def __init__(
        self,
        name: str,
        schema: dict,
        handler: Callable[[dict], str],
        description: str = "",
    ):
        self.name = name
        self.schema = schema
        self.handler = handler
        self.description = description or schema.get("description", "")


class ToolRegistry:
    """Thread-safe tool registry with self-registration support.

    Tools register themselves by calling registry.register().
    Uses RLock for thread-safe writes and async-safe reads via snapshot pattern.
    """

    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}
        self._lock = threading.RLock()

    def register(
        self,
        name: str,
        schema: dict,
        handler: Callable[[dict], str],
        description: str = "",
    ) -> None:
        """Register a tool (thread-safe).

        Args:
            name: Unique tool name
            schema: OpenAI-format tool schema
            handler: Callable that takes dict args, returns JSON string
            description: Human-readable description
        """
        with self._lock:
            self._tools[name] = ToolEntry(
                name=name,
                schema=schema,
                handler=handler,
                description=description,
            )

    async def dispatch(self, name: str, args: dict) -> str:
        """Execute a tool handler by name.

        Args:
            name: Tool name
            args: Arguments dict

        Returns:
            JSON string result

        Raises:
            ToolNotFoundError: If tool not found
        """
        entry = self.get_entry(name)
        if not entry:
            raise ToolNotFoundError(f"Unknown tool: {name}")
        try:
            # Handle async handlers directly
            if inspect.iscoroutinefunction(entry.handler):
                result = await entry.handler(args)
            else:
                result = await asyncio.to_thread(entry.handler, args)
            return result
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    def get_entry(self, name: str) -> Optional[ToolEntry]:
        """Get tool entry by name."""
        return self._tools.get(name)

    def get_schemas(self) -> list[dict]:
        """Get all tool schemas for LLM function calling."""
        return [
            {"type": "function", "function": {**e.schema, "name": e.name}}
            for e in self._tools.values()
        ]

    def get_names(self) -> list[str]:
        """Get sorted list of all tool names."""
        return sorted(self._tools.keys())


# Module-level helpers for tool handlers
def tool_result(data: dict = None, **kwargs) -> str:
    """Serialize tool success result as JSON string."""
    if data is not None:
        return json.dumps(data, ensure_ascii=False)
    return json.dumps(kwargs, ensure_ascii=False)


def tool_error(message: str, **kwargs) -> str:
    """Serialize tool error as JSON string."""
    result = {"error": str(message)}
    result.update(kwargs)
    return json.dumps(result, ensure_ascii=False)
