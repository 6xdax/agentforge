"""LLM provider base class and protocol."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Final, Optional

from .types import LLMResponse, ThinkingLevel


# Aliases mapping
THINKING_ALIASES: Final[dict[str, ThinkingLevel]] = {
    "x-high": ThinkingLevel.XHIGH,
    "x_high": ThinkingLevel.XHIGH,
    "extra-high": ThinkingLevel.XHIGH,
    "extra high": ThinkingLevel.XHIGH,
    "extra_high": ThinkingLevel.XHIGH,
    "highest": ThinkingLevel.HIGH,
}


def _normalize_thinking_key(value: str) -> str:
    """Normalize aliases like 'x_high' / 'X HIGH' into a canonical key."""
    normalized = value.casefold().strip().replace("_", "-")
    return "-".join(normalized.split())


def parse_thinking_level(
    value: str | ThinkingLevel | None,
) -> Optional[ThinkingLevel]:
    """Parse thinking level from string, handling aliases."""
    if value is None:
        return None
    if isinstance(value, ThinkingLevel):
        return value

    normalized = _normalize_thinking_key(value)
    if not normalized:
        return None

    if normalized in THINKING_ALIASES:
        return THINKING_ALIASES[normalized]

    try:
        return ThinkingLevel(normalized)
    except ValueError:
        return None


class LLMProvider(ABC):
    """Base class for LLM providers.

    Implement `chat()` method to provide LLM responses.
    Optionally override `chat_stream()` for streaming support.
    """

    @property
    def supports_streaming(self) -> bool:
        """Whether this provider implements true token streaming."""
        return False

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        thinking: Optional[ThinkingLevel] = None,
    ) -> LLMResponse:
        """Send chat request to LLM.

        Args:
            messages: List of messages in OpenAI format
            tools: Optional list of tool schemas
            thinking: Thinking effort level (default: provider's default)

        Returns:
            LLMResponse with content and optional tool_calls
        """
        ...

    async def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        thinking: Optional[ThinkingLevel] = None,
    ):
        """Stream chat response as text chunks.

        Default implementation falls back to chat() and yields full content.
        Override in subclasses for true streaming support.

        Args:
            messages: List of messages in OpenAI format
            tools: Optional list of tool schemas
            thinking: Thinking effort level

        Yields:
            Text chunks from the LLM response
        """
        response = await self.chat(messages, tools, thinking)
        content = response.get("content")
        if content:
            yield content
