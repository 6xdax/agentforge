"""Session tests with real MiniMax LLM.

Run with:
    uv run python test_scripts/test_session.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import asyncio

from agent import Session, Agent
from providers.minimax import MiniMaxProvider


async def test_single_conversation() -> None:
    """Test single conversation tracking."""
    provider = MiniMaxProvider()
    agent = Agent(provider=provider)
    session = Session(agent)

    result = await session.run("What is 2 + 2?")
    print(f"Response: {result}")
    assert result and len(result) > 0

    session.print_summary()
    print("\nPASS single conversation")


async def test_multiple_conversations() -> None:
    """Test multiple conversations in a session."""
    provider = MiniMaxProvider()
    agent = Agent(provider=provider)
    session = Session(agent)

    # First conversation
    result = await session.run("My name is Alice")
    print(f"1: {result}")

    # Second conversation
    result = await session.run("What is my name?")
    print(f"2: {result}")

    session.print_summary()
    print("\nPASS multiple conversations")


async def test_streaming() -> None:
    """Test streaming with session tracking."""
    provider = MiniMaxProvider()
    agent = Agent(provider=provider)
    session = Session(agent)

    print("Streaming: ", end="", flush=True)
    async for chunk in session.run_stream("What is 5 + 5?"):
        print(chunk, end="", flush=True)
    print()

    session.print_summary()
    print("\nPASS streaming")


async def test_mixed() -> None:
    """Test mixed regular and streaming calls."""
    provider = MiniMaxProvider()
    agent = Agent(provider=provider)
    session = Session(agent)

    # Regular call
    result = await session.run("What is 1 + 1?")
    print(f"1: {result}")

    # Streaming call
    print("Streaming: ", end="", flush=True)
    async for chunk in session.run_stream("What is 2 + 2?"):
        print(chunk, end="", flush=True)
    print()

    # Another regular call
    result = await session.run("What is 3 + 3?")
    print(f"3: {result}")

    session.print_summary()
    print("\nPASS mixed")


async def main() -> None:
    await test_single_conversation()
    await test_multiple_conversations()
    await test_streaming()
    await test_mixed()
    print("\nAll session tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
