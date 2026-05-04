"""Example file operations tool demonstrating tool registration."""

import json
from pathlib import Path

from agent import tool_result, tool_error


def _read_file(args: dict) -> str:
    """Read contents of a file."""
    path = args.get("path", "")
    if not path:
        return tool_error("path is required")

    try:
        p = Path(path).expanduser()
        if not p.exists():
            return tool_error(f"File not found: {path}")
        if not p.is_file():
            return tool_error(f"Not a file: {path}")

        content = p.read_text(encoding="utf-8")
        # Truncate if too long
        max_chars = args.get("max_chars", 10000)
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n... (truncated, total {len(content)} chars)"

        return tool_result({
            "path": str(p),
            "content": content,
            "size": len(content),
        })
    except Exception as e:
        return tool_error(str(e))


def _write_file(args: dict) -> str:
    """Write content to a file."""
    path = args.get("path", "")
    content = args.get("content", "")

    if not path:
        return tool_error("path is required")

    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

        return tool_result({
            "path": str(p),
            "bytes_written": len(content),
        })
    except Exception as e:
        return tool_error(str(e))


def _list_dir(args: dict) -> str:
    """List contents of a directory."""
    path = args.get("path", ".")

    try:
        p = Path(path).expanduser()
        if not p.exists():
            return tool_error(f"Directory not found: {path}")
        if not p.is_dir():
            return tool_error(f"Not a directory: {path}")

        items = []
        for item in sorted(p.iterdir()):
            items.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })

        return tool_result({
            "path": str(p),
            "items": items,
            "count": len(items),
        })
    except Exception as e:
        return tool_error(str(e))


# Self-registration
def register(registry):
    """Register all file operation tools with the registry."""
    registry.register(
        name="file_read",
        schema={
            "name": "file_read",
            "description": "Read the contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to read (default: 10000)",
                    },
                },
                "required": ["path"],
            },
        },
        handler=_read_file,
    )

    registry.register(
        name="file_write",
        schema={
            "name": "file_write",
            "description": "Write content to a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write",
                    },
                },
                "required": ["path", "content"],
            },
        },
        handler=_write_file,
    )

    registry.register(
        name="list_dir",
        schema={
            "name": "list_dir",
            "description": "List contents of a directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory",
                    },
                },
                "required": ["path"],
            },
        },
        handler=_list_dir,
    )
