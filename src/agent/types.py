"""Type definitions for the agent runtime.

These are raw TypedDicts used as data containers.
For protocol definitions, see provider.py and memory.py.
"""

from enum import Enum
from typing import TypedDict

# Re-exports from message.py for backwards compatibility
from .message import Message, LLMResponse, ToolCall, StreamChunk

__all__ = ["Message", "LLMResponse", "ToolCall", "StreamChunk", "ToolSchema", "ThinkingLevel"]


class ToolSchema(TypedDict):
    """Schema for a tool definition."""
    name: str
    description: str
    parameters: dict


class ThinkingLevel(str, Enum):
    """Thinking effort levels for LLM reasoning.

    Maps to provider-specific implementations:
    - off: No extended thinking
    - minimal: Quick "think"
    - low: "think hard"
    - medium: "think harder"
    - high: "ultrathink" (max budget)
    - xhigh: "ultrathink+" (GPT-5.2+, Claude Opus 4.7, Codex)
    - adaptive: Provider-managed adaptive thinking
    - max: Provider max inference (Claude Opus 4.7, Ollama highest)
    """
    OFF = "off"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    ADAPTIVE = "adaptive"
    MAX = "max"
