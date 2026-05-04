"""Memory backend abstractions and implementations."""

from typing import Protocol

from .types import Message


class MemoryBackend(Protocol):
    """Protocol for memory backends.

    Implement this protocol to create custom memory backends.
    """

    async def add(self, msg: Message) -> None:
        """Add a message to memory.

        Args:
            msg: Message dict with keys role, content, name (optional)
        """
        ...

    async def get_context(self) -> str:
        """Get formatted context string for system prompt.

        Returns:
            Context string to prepend to messages, or empty string
        """
        ...


class InMemoryMemory:
    """Basic in-memory memory backend.

    Stores messages in process memory. Optionally limits retained messages.
    """

    def __init__(self, max_messages: int | None = None):
        self.max_messages = max_messages
        self._messages: list[Message] = []

    async def add(self, msg: Message) -> None:
        """Add a message to memory."""
        self._messages.append(dict(msg))
        if self.max_messages is not None and len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages :]

    async def get_context(self) -> str:
        """Get formatted context string."""
        if not self._messages:
            return ""
        return "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in self._messages
        )

    async def clear(self) -> None:
        """Clear all messages."""
        self._messages.clear()

    async def get_messages(self) -> list[Message]:
        """Get a snapshot of current messages."""
        return list(self._messages)


class SlidingWindowMemory(InMemoryMemory):
    """Simple sliding window memory implementation.

    Keeps only the most recent N messages, discarding older ones.
    """

    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        super().__init__(max_messages=window_size)
