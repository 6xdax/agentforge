"""Runtime tests for Agent with MCP tools.

Run with:
    uv run python test_scripts/test_mcp.py

This test module includes both mock tests (no API key needed) and real tests
that require a running MCP server.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import asyncio

from agent import Agent, ToolRegistry, MCPServerConfig, MCPClient
from agent.memory import InMemoryMemory
from agent.registry import tool_result
from providers.minimax import MiniMaxProvider


async def test_mcp_client_connect() -> None:
    """Test connecting to a real MCP server."""
    config = MCPServerConfig(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    )

    registry = ToolRegistry()

    async with MCPClient(config) as client:
        client.register_tools(registry)
        print(f"Discovered tools: {registry.get_names()}")
        assert len(registry.get_names()) > 0, "Should discover at least one tool"
        print("PASS MCP client connect")


async def test_mcp_client_with_minimax() -> None:
    """Test agent with real MCP server and MiniMax."""
    config = MCPServerConfig(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    )

    registry = ToolRegistry()

    async with MCPClient(config) as client:
        client.register_tools(registry)
        agent = Agent(provider=MiniMaxProvider(), registry=registry)
        result = await agent.run("List files in /tmp")
        content = result.get("content", "") if isinstance(result, dict) else result
        print(f"Response: {content}")
        assert content and len(content) > 0
        print("PASS MCP client with MiniMax")


async def main() -> None:
    await test_mcp_client_connect()
    await test_mcp_client_with_minimax()  # Requires MiniMax API key
    print("\nAll MCP tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
