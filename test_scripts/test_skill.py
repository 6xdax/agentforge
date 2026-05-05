"""Test SkillLoader with MiniMax.

Run with:
    uv run python test_scripts/test_skill.py

Requires MINIMAX_API_KEY in .env

Tests the two-layer skill injection pattern:
- Layer 1: Skill metadata in system prompt
- Layer 2: Full skill body loaded on demand via load_skill tool
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import asyncio

from agent import Agent, ToolRegistry, SkillLoader
from agent.memory import InMemoryMemory
from providers.minimax import MiniMaxProvider


def create_skill_agent(skills_dir: Path):
    """Create an agent with load_skill tool and SkillLoader for descriptions."""
    loader = SkillLoader(skills_dir)
    registry = ToolRegistry(tools=["skill_tool"])
    provider = MiniMaxProvider()
    memory = InMemoryMemory()
    agent = Agent(provider=provider, registry=registry, memory=memory)
    return agent, loader


async def test_skill_loader():
    """Test SkillLoader basic functionality."""
    print("\n" + "=" * 50)
    print("Test 1: SkillLoader Basic")
    print("=" * 50)

    skills_dir = SRC / "skills"
    loader = SkillLoader(skills_dir)

    print(f"Skills found: {list(loader.skills.keys())}")
    print(f"\nDescriptions for system prompt:")
    print(loader.get_descriptions())

    print(f"\n--- Test loading 'pdf' skill ---")
    content = loader.get_content("pdf")
    print(content[:500] + "..." if len(content) > 500 else content)


async def test_skill_with_agent():
    """Test agent with load_skill tool using streaming."""
    print("\n" + "=" * 50)
    print("Test 2: Agent with load_skill Tool (Stream)")
    print("=" * 50)

    skills_dir = SRC / "skills"
    agent, loader = create_skill_agent(skills_dir)

    user_msg = "帮我做一个黄金价格的pdf"
    print(f"User: {user_msg}")
    print("\nAssistant: ", end="", flush=True)

    full_content = []
    async for chunk in agent.run_stream(user_msg):
        print(chunk)
        # if isinstance(chunk, str):
        #     print(chunk, end="", flush=True)
        #     full_content.append(chunk)
        # else:
        #     print(f"\n[Stream chunk]: {chunk}")

    print()


async def test_load_specific_skill():
    """Test loading a specific skill content using streaming."""
    print("\n" + "=" * 50)
    print("Test 3: Load Specific Skill via Agent (Stream)")
    print("=" * 50)

    skills_dir = SRC / "skills"
    agent, _ = create_skill_agent(skills_dir)

    user_msg = "Load the code-review skill and summarize what it does."
    print(f"User: {user_msg}")
    print("\nAssistant: ", end="", flush=True)

    full_content = []
    async for chunk in agent.run_stream(user_msg):
        print(chunk)
        # if isinstance(chunk, str):
        #     print(chunk, end="", flush=True)
        #     full_content.append(chunk)
        # else:
        #     print(f"\n[Stream chunk]: {chunk}")

    print()


async def test_agent_builder_skill():
    """Test loading agent-builder skill."""
    print("\n" + "=" * 50)
    print("Test 4: Agent-Builder Skill")
    print("=" * 50)

    skills_dir = SRC / "skills"
    loader = SkillLoader(skills_dir)

    print("Loading agent-builder skill content:")
    content = loader.get_content("agent-builder")
    print(content[:800] + "\n...[truncated]..." if len(content) > 800 else content)


async def main():
    print("SkillLoader Tests with MiniMax")
    print("=" * 50)

    try:
        # await test_skill_loader()
        await test_skill_with_agent()
        # await test_load_specific_skill()
        # await test_agent_builder_skill()

        print("\n" + "=" * 50)
        print("All skill tests completed!")
        print("=" * 50)
    except Exception as e:
        print(f"\nError: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())