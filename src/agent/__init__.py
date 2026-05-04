"""agent - the core runtime package inside AgentForge.

A minimal (~120 lines core), zero-dependency agent runtime designed for:
- Learning Agent concepts
- Interview demonstrations
- Personal task automation

Example usage:
    from agent import Agent, ToolRegistry

    registry = ToolRegistry()
    registry.register(name="calc", schema={...}, handler=lambda a: str(eval(a["expr"])))

    agent = Agent(provider=my_provider, registry=registry)
    result = agent.run("Calculate 2+2")
"""

from .core import Agent
from .message import Message
from .registry import ToolRegistry, tool_result, tool_error, ToolEntry
from .memory import MemoryBackend, InMemoryMemory, SlidingWindowMemory
from .provider import LLMProvider, ThinkingLevel, parse_thinking_level
from .errors import (
    ToolError,
    ToolNotFoundError,
    MaxIterationsError,
    jittered_backoff,
    retry_with_backoff,
)
from .types import (
    LLMResponse,
    ToolCall,
    ToolSchema,
    StreamChunk,
)
from .schema_validator import (
    SchemaValidator,
    SchemaValidationError,
    create_tool_schema,
)
from .usage import tracker, UsageTracker, TokenUsage, TokenPricing, UsageRecord
from .session import Session, ConversationRecord, TurnRecord
from tools.file_parser import parse_document, get_document_schema

__all__ = [
    # Core
    "Agent",
    "Message",
    # Registry
    "ToolRegistry",
    "ToolEntry",
    "tool_result",
    "tool_error",
    # Memory
    "MemoryBackend",
    "InMemoryMemory",
    "SlidingWindowMemory",
    # Provider
    "LLMProvider",
    "ThinkingLevel",
    "parse_thinking_level",
    # Errors
    "ToolError",
    "ToolNotFoundError",
    "MaxIterationsError",
    "jittered_backoff",
    "retry_with_backoff",
    # Types
    "LLMResponse",
    "ToolCall",
    "ToolSchema",
    "StreamChunk",
    # Schema validation (reliable tool calling)
    "SchemaValidator",
    "SchemaValidationError",
    "create_tool_schema",
    # Usage tracking
    "tracker",
    "UsageTracker",
    "TokenUsage",
    "TokenPricing",
    "UsageRecord",
    # Session
    "Session",
    "ConversationRecord",
    "TurnRecord",
    # File parser
    "parse_document",
    "get_document_schema",
]
