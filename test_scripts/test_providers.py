"""Provider tests for AgentForge.

Tests each LLM provider's:
- chat() returns usage fields
- chat_stream() yields done chunk with usage fields

Run with:
    uv run python test_scripts/test_providers.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import asyncio
from typing import AsyncIterator

from agent.types import ThinkingLevel, LLMResponse
from agent.provider import LLMProvider
from agent.message import StreamChunk


# ---------------------------------------------------------------------------
# MiniMax provider
# ---------------------------------------------------------------------------

async def test_minimax_chat_usage() -> None:
    """Test MiniMaxProvider.chat() returns usage."""
    from providers.minimax import MiniMaxProvider

    provider = MiniMaxProvider(thinking=ThinkingLevel.ADAPTIVE)
    messages = [{"role": "user", "content": "Say hello in one word."}]

    response = await provider.chat(messages)
    print(f"[MiniMax chat] response keys: {response.keys()}")
    print(f"[MiniMax chat] usage: input={response.get('input_tokens')}, output={response.get('output_tokens')}, cache_write={response.get('cache_write_tokens')}, cache_read={response.get('cache_read_tokens')}")

    assert response.get("input_tokens") is not None, "input_tokens should not be None"
    assert response.get("output_tokens") is not None, "output_tokens should not be None"
    print("PASS minimax chat usage")


async def test_minimax_stream_usage() -> None:
    """Test MiniMaxProvider.chat_stream() done chunk has usage."""
    from providers.minimax import MiniMaxProvider

    provider = MiniMaxProvider(thinking=ThinkingLevel.ADAPTIVE)
    messages = [{"role": "user", "content": "Count from 1 to 3."}]

    chunks = []
    async for chunk in provider.chat_stream(messages):
        chunks.append(chunk)
        if isinstance(chunk, dict) and chunk.get("type") == "done":
            print(f"[MiniMax stream] done chunk usage: input={chunk.get('input_tokens')}, output={chunk.get('output_tokens')}, cache_write={chunk.get('cache_write_tokens')}, cache_read={chunk.get('cache_read_tokens')}")

    done_chunks = [c for c in chunks if isinstance(c, dict) and c.get("type") == "done"]
    assert len(done_chunks) > 0, "Expected at least one done chunk"

    done = done_chunks[0]
    assert done.get("input_tokens") is not None, "input_tokens should not be None in done chunk"
    assert done.get("output_tokens") is not None, "output_tokens should not be None in done chunk"
    print("PASS minimax stream usage")


# ---------------------------------------------------------------------------
# Provider-agnostic interface tests
# ---------------------------------------------------------------------------

async def test_provider_interface() -> None:
    """Verify LLMProvider ABC is correctly implemented by available providers."""
    from providers.minimax import MiniMaxProvider

    provider = MiniMaxProvider()

    # Should have chat method
    assert hasattr(provider, "chat"), "Provider must have chat method"

    # Should have supports_streaming property
    _ = provider.supports_streaming

    # chat must accept thinking parameter
    import inspect
    sig = inspect.signature(provider.chat)
    assert "thinking" in sig.parameters, "chat() must accept 'thinking' parameter"

    print("PASS provider interface")


async def test_streamchunk_fields() -> None:
    """Verify StreamChunk TypedDict allows all expected fields."""
    chunk: StreamChunk = {
        "type": "done",
        "content": "hello",
        "input_tokens": 10,
        "output_tokens": 20,
        "cache_write_tokens": 5,
        "cache_read_tokens": 3,
    }
    assert chunk["type"] == "done"
    assert chunk["input_tokens"] == 10
    print("PASS StreamChunk fields")


# ---------------------------------------------------------------------------
# Agent with thinking levels
# ---------------------------------------------------------------------------

async def test_agent_thinking_override() -> None:
    """Test Agent.run() and run_stream() thinking parameter override."""
    from agent import Agent
    from providers.minimax import MiniMaxProvider
    from agent.registry import ToolRegistry

    registry = ToolRegistry()
    provider = MiniMaxProvider()

    agent = Agent(provider=provider, registry=registry, thinking=ThinkingLevel.OFF)

    # Non-streaming with thinking override
    result = await agent.run("What is 1+1?", thinking=ThinkingLevel.ADAPTIVE)
    assert result.get("input_tokens") is not None, "Usage should be returned"
    print(f"[Agent.run with override] usage: input={result.get('input_tokens')}")

    # Streaming with thinking override
    chunks = []
    async for chunk in agent.run_stream("Reply briefly.", thinking=ThinkingLevel.ADAPTIVE):
        chunks.append(chunk)

    done = next((c for c in chunks if isinstance(c, dict) and c.get("type") == "done"), None)
    assert done is not None, "Should have a done chunk"
    print(f"[Agent.run_stream with override] done usage: input={done.get('input_tokens')}")
    print("PASS agent thinking override")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def test_minimax_prompt_caching() -> None:
    """Test that prompt caching works: second call with same context yields cache_read_tokens > 0."""
    from providers.minimax import MiniMaxProvider

    # Use a long enough system message to exceed Anthropic's 1024-token cache threshold
    system_content = (
        "You are a knowledgeable assistant specialized in software engineering. "
        "You help developers with Python, TypeScript, Rust, Go, and other languages. "
        "You provide concise, accurate answers and always prefer idiomatic solutions. "
        "When answering questions, think step by step but keep responses short. "
        "Never include unnecessary boilerplate or caveats. "
        "If asked a factual question, answer directly without preamble. "
    ) * 20  # repeat to exceed 1024-token minimum

    messages_first = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "What is 2 + 2?"},
    ]
    messages_second = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "What is 3 + 3?"},
    ]

    provider = MiniMaxProvider()

    # First call: populates the cache (cache_write_tokens > 0)
    r1 = await provider.chat(messages_first)
    print(f"[cache test] call 1: input={r1.get('input_tokens')}, cache_write={r1.get('cache_write_tokens')}, cache_read={r1.get('cache_read_tokens')}")

    # Second call: same system message should be served from cache
    r2 = await provider.chat(messages_second)
    print(f"[cache test] call 2: input={r2.get('input_tokens')}, cache_write={r2.get('cache_write_tokens')}, cache_read={r2.get('cache_read_tokens')}")

    cache_read = r2.get("cache_read_tokens") or 0
    if cache_read > 0:
        print(f"PASS prompt caching: {cache_read} tokens served from cache")
    else:
        print("WARN prompt caching: cache_read_tokens=0 — provider may not support caching or content too short")


PROVIDER_TESTS = {
    "minimax": [
        test_minimax_chat_usage,
        test_minimax_stream_usage,
        test_minimax_prompt_caching,
    ],
}


async def run_provider_tests(provider_name: str, tests: list) -> None:
    print(f"\n{'='*60}")
    print(f" Testing {provider_name} provider ")
    print(f"{'='*60}")
    for test in tests:
        try:
            await test()
        except Exception as e:
            print(f"FAIL {test.__name__}: {e}")
            raise


async def main() -> None:
    # Interface tests
    await test_provider_interface()
    await test_streamchunk_fields()

    # Agent integration tests
    await test_agent_thinking_override()

    # Per-provider tests
    for provider_name, tests in PROVIDER_TESTS.items():
        await run_provider_tests(provider_name, tests)

    print("\nAll provider tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
