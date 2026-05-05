"""Test MiniMax with real tool calling (streaming).

Run with:
    uv run python test_scripts/test_tools.py

Requires MINIMAX_API_KEY in .env
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import asyncio

from agent import Agent, ToolRegistry
from agent.memory import InMemoryMemory
from providers.minimax import MiniMaxProvider


async def run_streaming(agent, user_msg: str):
    """Run agent with streaming and print chunks."""
    print(f"User: {user_msg}")
    print("\nAssistant: ", end="", flush=True)

    full_content = []
    tool_calls = []

    async for chunk in agent.run_stream(user_msg):
        print(chunk)
        # if isinstance(chunk, str):
        #     print(chunk, end="", flush=True)
        #     full_content.append(chunk)
        # else:
        #     chunk_type = chunk.get("type")
        #     if chunk_type == "tool_use":
        #         tool_name = chunk.get("tool_name")
        #         if tool_name:
        #             tool_calls.append(tool_name)
        #             print(f"\n[Tool Call]: {tool_name}", end="", flush=True)
        #     elif chunk_type == "thinking":
        #         print(f"\n[Thinking]: {chunk.get('content', '')[:100]}...", end="", flush=True)

    print()
    return "".join(full_content), tool_calls


async def test_calculator():
    """Test calculator tool with MiniMax (streaming)."""
    print("\n" + "=" * 50)
    print("Test 1: Calculator Tool")
    print("=" * 50)

    registry = ToolRegistry(tools=["calculator"])
    provider = MiniMaxProvider()
    agent = Agent(provider=provider, registry=registry, memory=InMemoryMemory())

    user_msg = "What is 125 * 17 + 43? Please calculate it step by step."
    content, tool_calls = await run_streaming(agent, user_msg)

    if tool_calls:
        print(f"\nTool calls executed: {tool_calls}")

    return content


async def test_file_operations():
    """Test file operations with MiniMax (streaming)."""
    print("\n" + "=" * 50)
    print("Test 2: File Operations Tool")
    print("=" * 50)

    registry = ToolRegistry(tools=["file_ops"])
    provider = MiniMaxProvider()
    agent = Agent(provider=provider, registry=registry, memory=InMemoryMemory())

    user_msg = "List the files in the current directory and tell me how many items there are."
    content, tool_calls = await run_streaming(agent, user_msg)

    if tool_calls:
        print(f"\nTool calls executed: {tool_calls}")

    return content


async def test_all_tools_unified():
    """Test unified tool loading with MiniMax (streaming)."""
    print("\n" + "=" * 50)
    print("Test 3: Unified Tool Registration")
    print("=" * 50)

    registry = ToolRegistry(tools=["calculator", "file_ops", "file_parser"])
    print(f"Registered tools: {registry.get_names()}")

    provider = MiniMaxProvider()
    agent = Agent(provider=provider, registry=registry, memory=InMemoryMemory())

    user_msg = "Read the file at /home/ubuntu/workspace/agentforge/pyproject.toml and tell me the project name."
    content, tool_calls = await run_streaming(agent, user_msg)

    if tool_calls:
        print(f"\nTool calls executed: {tool_calls}")

    return content


async def test_multi_step():
    """Test multi-step tool calling with MiniMax (streaming)."""
    print("\n" + "=" * 50)
    print("Test 4: Multi-Step Tool Calling")
    print("=" * 50)

    registry = ToolRegistry(tools=["calculator", "file_ops"])
    provider = MiniMaxProvider()
    agent = Agent(provider=provider, registry=registry, memory=InMemoryMemory())

    user_msg = """First calculate the result of 99 * 99, then list the files in /tmp, and finally calculate 50 + 50."""
    content, tool_calls = await run_streaming(agent, user_msg)

    if tool_calls:
        print(f"\nTool calls executed ({len(tool_calls)}): {tool_calls}")

    return content


async def main():
    print("MiniMax Tool Calling Tests (Streaming)")
    print("=" * 50)

    try:
        await test_calculator()
        await test_file_operations()
        await test_all_tools_unified()
        await test_multi_step()

        print("\n" + "=" * 50)
        print("All tests completed!")
        print("=" * 50)
    except Exception as e:
        print(f"\nError: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())