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

from agent import Agent, ToolRegistry, MCPServerConfig, MCPClient, MCPToolProvider
from agent.memory import InMemoryMemory
from agent.registry import tool_result
from providers.minimax import MiniMaxProvider


async def test_mcp_mock_provider() -> None:
    """Test agent with mock MCP provider (no real server needed)."""
    mock_tools = [
        {
            "name": "calculator",
            "description": "A simple calculator for expressions",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression"}
                },
                "required": ["expression"]
            }
        },
        {
            "name": "weather",
            "description": "Get weather for a location",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"}
                },
                "required": ["city"]
            }
        }
    ]

    provider = MCPToolProvider(
        tools=mock_tools,
        response_final="The weather in Tokyo is sunny, 22°C.",
        tool_to_call="weather",
        tool_args={"city": "Tokyo"}
    )

    registry = ToolRegistry()
    memory = InMemoryMemory()

    # Manually register mock MCP tools
    for tool in mock_tools:
        schema = {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["inputSchema"]
        }
        registry.register(
            name=tool["name"],
            schema=schema,
            handler=lambda args, name=tool["name"]: tool_result({"result": f"Executed {name} with {args}"})
        )

    agent = Agent(provider=provider, registry=registry, memory=memory, max_iterations=5)

    result = await agent.run("What's the weather in Tokyo?")
    content = result.get("content", "") if isinstance(result, dict) else result
    print(f"Response: {content}")
    assert "weather" in content.lower() or "tokyo" in content.lower(), f"Expected weather response, got: {content}"
    print("PASS MCP mock provider")


async def test_mcp_client_schema_generation() -> None:
    """Test that MCPToolProvider generates proper schemas."""
    mock_tools = [
        {
            "name": "test_tool",
            "description": "A test tool",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "input": {"type": "string"}
                }
            }
        }
    ]

    provider = MCPToolProvider(tools=mock_tools, response_final="Done")
    registry = ToolRegistry()

    # Register tool
    schema = {
        "name": "test_tool",
        "description": "A test tool",
        "parameters": mock_tools[0]["inputSchema"]
    }
    registry.register(
        name="test_tool",
        schema=schema,
        handler=lambda args: tool_result({"status": "ok"})
    )

    schemas = registry.get_schemas()
    assert len(schemas) == 1
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "test_tool"
    print(f"Generated schema: {schemas[0]}")
    print("PASS MCP schema generation")


# Real MCP server tests - require npx and @anthropic/mcp-server-filesystem
# Uncomment when you have the MCP server installed
#
# async def test_mcp_client_connect() -> None:
#     """Test connecting to a real MCP server."""
#     config = MCPServerConfig(
#         command="npx",
#         args=["-y", "@anthropic/mcp-server-filesystem", "/tmp"],
#     )
#
#     registry = ToolRegistry()
#
#     async with MCPClient(config) as client:
#         client.register_tools(registry)
#         print(f"Discovered tools: {registry.get_names()}")
#         assert len(registry.get_names()) > 0, "Should discover at least one tool"
#         print("PASS MCP client connect")
#
#
# async def test_mcp_client_with_minimax() -> None:
#     """Test agent with real MCP server and MiniMax."""
#     config = MCPServerConfig(
#         command="npx",
#         args=["-y", "@anthropic/mcp-server-filesystem", "/tmp"],
#     )
#
#     registry = ToolRegistry()
#
#     async with MCPClient(config) as client:
#         client.register_tools(registry)
#         agent = Agent(provider=MiniMaxProvider(), registry=registry)
#         result = await agent.run("List files in /tmp")
#         content = result.get("content", "") if isinstance(result, dict) else result
#         print(f"Response: {content}")
#         assert content and len(content) > 0
#         print("PASS MCP client with MiniMax")


async def main() -> None:
    await test_mcp_mock_provider()
    await test_mcp_client_schema_generation()
    # await test_mcp_client_connect()
    # await test_mcp_client_with_minimax()
    print("\nAll MCP tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
