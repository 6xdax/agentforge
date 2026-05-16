import logging
from pathlib import Path

from agent import Agent, ToolRegistry
from agent.types import ThinkingLevel
from providers.minimax import MiniMaxProvider
from tools import load_all_tools

from session import session_manager

logger = logging.getLogger("chatbot")

registry = ToolRegistry()
load_all_tools(registry)
logger.info("Loaded %d tools into registry", len(registry.get_schemas()))


def create_agent(thinking: bool = False) -> Agent:
    thinking_level = ThinkingLevel.ADAPTIVE if thinking else ThinkingLevel.OFF
    provider = MiniMaxProvider(thinking=thinking_level)
    return Agent(provider=provider, registry=registry, memory=session_manager.memory)


default_agent = create_agent()
