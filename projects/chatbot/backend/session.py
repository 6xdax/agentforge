import logging
import json
import sqlite3
from pathlib import Path
from typing import Optional

from agent import Agent, SQLiteMemory, ToolRegistry
from agent.types import ThinkingLevel
from models import HistoryMessage, ToolCall
from providers.minimax import MiniMaxProvider
from tools import load_all_tools

logger = logging.getLogger("chatbot")

registry = ToolRegistry()
load_all_tools(registry)
logger.info("Loaded %d tools into registry", len(registry.get_schemas()))


def create_agent(thinking: bool = False, memory=None) -> Agent:
    thinking_level = ThinkingLevel.ADAPTIVE if thinking else ThinkingLevel.OFF
    provider = MiniMaxProvider(thinking=thinking_level)
    return Agent(provider=provider, registry=registry, memory=memory)


class SessionManager:
    def __init__(self, db_path: str = "db/chatbot_memory.db"):
        self.sessions: dict[str, dict] = {}
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                thinking TEXT,
                tool_calls TEXT,
                usage TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON messages(session_id)")
        # Migrate existing tables: add new columns if they don't exist
        for col, col_type in [("thinking", "TEXT"), ("tool_calls", "TEXT"), ("usage", "TEXT")]:
            try:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
        conn.close()

    def create_session(self, session_id: str):
        memory = SQLiteMemory(db_path="db/agent_memory.db", session_id=session_id)
        agent = create_agent(memory=memory)
        self.sessions[session_id] = {"agent": agent, "memory": memory}

    def get_session(self, session_id: str) -> Optional[dict]:
        return self.sessions.get(session_id)

    async def add_to_history(self, session_id: str, message: HistoryMessage):
        conn = sqlite3.connect(self.db_path)
        tool_calls_json = None
        if message.tool_calls:
            tool_calls_json = json.dumps([tc.model_dump() for tc in message.tool_calls])
        conn.execute(
            "INSERT INTO messages (session_id, role, content, thinking, tool_calls, usage) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, message.role, message.content, message.thinking, tool_calls_json, json.dumps(message.usage) if message.usage else None)
        )
        conn.commit()
        conn.close()

    def delete_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
        return True

    async def get_history(self, session_id: str, limit: int = 100) -> list:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT id, role, content, thinking, tool_calls, usage, created_at FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit)
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "thinking": r[3],
                "thinking_completed": bool(r[3]),
                "tool_calls": [ToolCall(**tc) for tc in json.loads(r[4])] if r[4] else None,
                "usage": json.loads(r[5]) if r[5] else None,
                "created_at": r[6]
            }
            for r in rows
        ]

    async def list_sessions(self, user_id: str) -> list[dict]:
        """List all sessions for a user with their first message title."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT session_id, role, content FROM messages WHERE session_id LIKE ? ORDER BY session_id, created_at",
            (f"{user_id}:%",)
        )
        rows = cur.fetchall()
        conn.close()

        sessions = {}
        for session_id, role, content in rows:
            if role == "user" and session_id not in sessions:
                sessions[session_id] = {
                    "chat_id": session_id.split(":", 1)[1] if ":" in session_id else session_id,
                    "title": content[:30] + ("..." if len(content) > 30 else "")
                }

        return list(sessions.values())


session_manager = SessionManager()
