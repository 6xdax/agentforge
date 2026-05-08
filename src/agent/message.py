"""Message type definition.

This module contains the core Message TypedDict for conversation messages
in OpenAI-compatible format, plus streaming chunk types.
"""

from typing import TypedDict, Optional


class Message(TypedDict, total=False):
    """A message in the conversation (OpenAI format)."""
    role: str
    content: str
    name: Optional[str]


class LLMResponse(TypedDict, total=False):
    """Response from an LLM provider."""
    content: str
    tool_calls: Optional[list["ToolCall"]]
    thinking: Optional[str]
    # Token usage
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None


class ToolCall(TypedDict):
    """A tool call requested by the LLM."""
    name: str
    arguments: dict


class StreamChunk(TypedDict, total=False):
    """A chunk yielded during streaming response.

    Types:
    - text: Regular text content
    - thinking: Reasoning/thinking content
    - tool_use: Tool call start
    - tool_result: Tool result content
    - done: Streaming complete
    """
    type: str  # "text" | "thinking" | "tool_use" | "tool_result" | "done"
    content: Optional[str] = None          # text, thinking, done
    tool_call_id: Optional[str] = None    # tool_use, tool_result
    tool_name: Optional[str] = None       # tool_use, tool_result
    arguments: Optional[dict] = None     # tool_use
    result: Optional[str] = None          # tool_result
    # Token usage (only in "done" chunk)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None


__all__ = ["Message", "LLMResponse", "ToolCall", "StreamChunk"]
