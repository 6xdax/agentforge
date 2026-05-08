"""Memory backend abstractions and implementations."""
import sqlite3
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


class SQLiteMemory:
    """SQLite-based persistent memory backend.

    Stores messages in a SQLite database, with support for multiple
    sessions identified by session_id.
    """

    def __init__(self, db_path: str = "memory.db", session_id: str = "default"):
        self.db_path = db_path
        self.session_id = session_id
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session ON messages(session_id, created_at)"
        )
        conn.commit()
        conn.close()

    async def add(self, msg: Message) -> None:
        """Add a message to the database."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO messages (session_id, role, content, name) VALUES (?, ?, ?, ?)",
            (self.session_id, msg.get("role", "unknown"), msg.get("content", ""), msg.get("name")),
        )
        conn.commit()
        conn.close()

    async def get_context(self, limit: int = 100) -> str:
        """Get formatted context string for recent messages."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (self.session_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return ""
        return "\n".join(f"{role}: {content}" for role, content in reversed(rows))

    async def clear(self) -> None:
        """Clear all messages for the current session."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM messages WHERE session_id = ?", (self.session_id,))
        conn.commit()
        conn.close()

    async def get_messages(self, limit: int = 100) -> list[Message]:
        """Get recent messages as a list."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT role, content, name FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (self.session_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()

        return [{"role": r, "content": c, "name": n} for r, c, n in reversed(rows)]
