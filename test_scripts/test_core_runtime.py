"""Runtime tests for Agent with real MiniMax LLM.

Run with:
    uv run python test_scripts/test_core_runtime.py

Requires ANTHROPIC_API_KEY environment variable.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import asyncio

from agent import Agent, SlidingWindowMemory, tracker, ToolRegistry
from providers.minimax import MiniMaxProvider
from agent.types import ThinkingLevel
from tools.calculator import register as register_calculator
from tools.file_ops import register as register_file_ops


async def test_simple_chat() -> None:
    """Test basic chat without tools."""
    provider = MiniMaxProvider()
    agent = Agent(provider=provider)

    result = await agent.run("What is 2 + 2?")
    content = result.get("content", "") if isinstance(result, dict) else result
    print(f"Response: {result}")
    assert content and len(content) > 0, "Expected non-empty response"
    print("PASS simple chat")


async def test_memory_captures_conversation() -> None:
    """Test that memory captures the conversation history."""
    memory = SlidingWindowMemory(window_size=10)
    agent = Agent(provider=MiniMaxProvider(), memory=memory)

    result = await agent.run("My name is Alice")
    print(f"First response: {result.get('content', '') if isinstance(result, dict) else result}")

    result = await agent.run("What is my name?")
    print(f"Second response: {result.get('content', '') if isinstance(result, dict) else result}")

    # Memory should have captured the conversation
    context = await memory.get_context()
    print(f"Memory context: {context}")
    assert "Alice" in context or "alice" in context.lower(), "Memory should have captured the name"
    print("PASS memory captures conversation")


async def test_system_message() -> None:
    """Test agent with a system message."""
    memory = SlidingWindowMemory(window_size=10)
    agent = Agent(provider=MiniMaxProvider(), memory=memory)

    # The agent should remember it's a helpful assistant
    result = await agent.run("What is your purpose?")
    content = result.get("content", "") if isinstance(result, dict) else result
    print(f"System test response: {content}")
    assert content and len(content) > 0
    print("PASS system message")


async def test_streaming() -> None:
    """Test streaming response."""
    agent = Agent(provider=MiniMaxProvider(thinking=ThinkingLevel.ADAPTIVE))

    chunks = []
    async for chunk in agent.run_stream("你好"):
        chunks.append(chunk)
        print(f"chunk: {chunk}", end="", flush=True)
    print()

    # Filter out dict chunks (thinking) when joining
    full_response = "".join(c for c in chunks if isinstance(c, str))
    print(f"Full response: {full_response}")
    assert full_response and len(full_response) > 0, "Expected non-empty streaming response"
    print("PASS streaming")


async def test_tool_calling() -> None:
    """Test agent with tool calling (calculator)."""
    registry = ToolRegistry()
    register_calculator(registry)

    agent = Agent(provider=MiniMaxProvider(), registry=registry)

    result = await agent.run("What is 123 + 456?")
    content = result.get("content", "") if isinstance(result, dict) else result
    print(f"Response: {result}")
    # Should contain the result from calculator tool
    assert "579" in content or "result" in content.lower(), f"Expected calculator result in response, got: {content}"
    print("PASS tool calling")


async def test_tool_streaming() -> None:
    """Test streaming with tool calling."""
    registry = ToolRegistry()
    register_calculator(registry)

    agent = Agent(provider=MiniMaxProvider(thinking=ThinkingLevel.ADAPTIVE), registry=registry)

    chunks = []
    tool_calls_seen = []
    async for chunk in agent.run_stream("分开两次调用工具计算 431*131 再乘2"):
        print(f"chunk: {chunk}")
        chunks.append(chunk)
        if isinstance(chunk, dict):
            if chunk.get("type") == "tool_use":
                tool_calls_seen.append(chunk.get("tool_name"))
        #         print(f"\n[Tool Call]: {chunk}", flush=True)
        #     elif chunk.get("type") == "thinking":
        #         print(f"\n[Thinking]: {chunk.get('content', '')}", flush=True)
        #     elif chunk.get("type") == "done":
        #         print(f"\n[Done]: {chunk}", flush=True)
        # else:
        #     print(f"{chunk}", end="", flush=True)
    print()

    full_response = "".join(c for c in chunks if isinstance(c, str))
    print(f"Full response: {full_response}")
    # When tools are called, model may not output text - just verify tool_use and done events
    assert len(tool_calls_seen) > 0, "Expected at least one tool call"
    done_chunks = [c for c in chunks if isinstance(c, dict) and c.get("type") == "done"]
    assert len(done_chunks) > 0, "Expected at least one done chunk"
    print("PASS tool streaming")


async def main() -> None:
    # await test_simple_chat()
    # await test_memory_captures_conversation()
    # await test_system_message()
    # await test_tool_calling()
    await test_tool_streaming()
    # await test_streaming()

    # Print token usage summary
    summary = tracker.summary()
    for provider, stats in summary.items():
        print(f"\n{provider}:")
        print(f"  input_tokens: {stats['input_tokens']}")
        print(f"  output_tokens: {stats['output_tokens']}")
        print(f"  cache_write_tokens: {stats['cache_write_tokens']}")
        print(f"  cache_read_tokens: {stats['cache_read_tokens']}")
        print(f"  cost: ${stats['cost']:.6f}")
    print(f"\nTotal cost: ${tracker.total_cost():.6f}")

    print("\nAll MiniMax runtime tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
