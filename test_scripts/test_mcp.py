"""Runtime tests for Agent with MCP tools (streaming).

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
    """Test agent with real MCP server and MiniMax (streaming)."""
    print("\n" + "=" * 50)
    print("MCP Client with MiniMax (Stream)")
    print("=" * 50)

    config = MCPServerConfig(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    )

    registry = ToolRegistry()

    async with MCPClient(config) as client:
        client.register_tools(registry)
        print(f"Discovered tools: {registry.get_names()}")

        provider = MiniMaxProvider()
        agent = Agent(provider=provider, registry=registry, memory=InMemoryMemory())

        user_msg = "List files in /tmp"
        print(f"User: {user_msg}")
        print("\nAssistant: ", end="", flush=True)

        full_content = []
        async for chunk in agent.run_stream(user_msg):
            if isinstance(chunk, str):
                print(chunk, end="", flush=True)
                full_content.append(chunk)
            else:
                chunk_type = chunk.get("type")
                if chunk_type == "tool_use":
                    tool_name = chunk.get("tool_name")
                    if tool_name:
                        print(f"\n[Tool Call]: {tool_name}", end="", flush=True)
                elif chunk_type == "thinking":
                    print(f"\n[Thinking]: {chunk.get('content', '')[:80]}...", end="", flush=True)

        print()
        assert len(full_content) > 0, "Should have some content"
        print("PASS MCP client with MiniMax")


async def main() -> None:
    await test_mcp_client_connect()
    await test_mcp_client_with_minimax()
    print("\nAll MCP tests passed!")


if __name__ == "__main__":
    asyncio.run(main())