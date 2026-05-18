import asyncio
import json
import logging
from typing import Optional

from agent import Agent, SQLiteMemory, ToolRegistry
from agent.types import ThinkingLevel
from sqlalchemy import delete, select

from db.database import create_sessionmaker_for, get_agent_memory_db_path, init_database
from db.models import Message
from models import HistoryMessage, ToolCall
from providers.minimax import MiniMaxProvider
from user_config import build_tool_registry_for_user

logger = logging.getLogger("chatbot")


def create_agent(thinking: bool = False, memory=None, registry: ToolRegistry | None = None) -> Agent:
    thinking_level = ThinkingLevel.ADAPTIVE if thinking else ThinkingLevel.OFF
    provider = MiniMaxProvider(thinking=thinking_level)
    return Agent(provider=provider, registry=registry, memory=memory)


class SessionManager:
    def __init__(self, db_path: str = "db/data/app.db"):
        self.sessions: dict[str, dict] = {}
        self.db_path = db_path
        self._sessionmaker = create_sessionmaker_for(self.db_path)
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def _ensure_tables(self):
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            await init_database(self.db_path)
            self._initialized = True

    async def create_session(self, session_id: str):
        await self._ensure_tables()
        user_id = session_id.split(":", 1)[0] if ":" in session_id else session_id
        registry = await build_tool_registry_for_user(user_id)
        memory = SQLiteMemory(db_path=str(get_agent_memory_db_path()), session_id=session_id)
        agent = create_agent(memory=memory, registry=registry)
        self.sessions[session_id] = {"agent": agent, "memory": memory}

    def get_session(self, session_id: str) -> Optional[dict]:
        return self.sessions.get(session_id)

    async def add_to_history(self, session_id: str, message: HistoryMessage):
        await self._ensure_tables()
        tool_calls_json = None
        if message.tool_calls:
            tool_calls_json = json.dumps([tc.model_dump() for tc in message.tool_calls])
        async with self._sessionmaker() as session:
            session.add(
                Message(
                    session_id=session_id,
                    role=message.role,
                    content=message.content,
                    thinking=message.thinking,
                    tool_calls=tool_calls_json,
                    usage=json.dumps(message.usage) if message.usage else None,
                )
            )
            await session.commit()

    async def delete_session(self, session_id: str) -> bool:
        await self._ensure_tables()
        if session_id in self.sessions:
            del self.sessions[session_id]
        async with self._sessionmaker() as session:
            await session.execute(delete(Message).where(Message.session_id == session_id))
            await session.commit()
        return True

    def reset_user_sessions(self, user_id: str) -> None:
        prefix = f"{user_id}:"
        for session_id in list(self.sessions.keys()):
            if session_id == user_id or session_id.startswith(prefix):
                del self.sessions[session_id]

    async def get_history(self, session_id: str, limit: int = 100) -> list:
        await self._ensure_tables()
        async with self._sessionmaker() as session:
            result = await session.scalars(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.id.asc())
                .limit(limit)
            )
            rows = result.all()
        return [
            {
                "id": row.id,
                "role": row.role,
                "content": row.content,
                "thinking": row.thinking,
                "thinking_completed": bool(row.thinking),
                "tool_calls": [ToolCall(**tc) for tc in json.loads(row.tool_calls)] if row.tool_calls else None,
                "usage": json.loads(row.usage) if row.usage else None,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    async def list_sessions(self, user_id: str) -> list[dict]:
        """List all sessions for a user with their first message title."""
        await self._ensure_tables()
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(Message.session_id, Message.role, Message.content)
                .where(Message.session_id.like(f"{user_id}:%"))
                .order_by(Message.session_id.asc(), Message.id.asc())
            )
            rows = result.all()

        sessions = {}
        for session_id, role, content in rows:
            if role == "user" and session_id not in sessions:
                sessions[session_id] = {
                    "chat_id": session_id.split(":", 1)[1] if ":" in session_id else session_id,
                    "title": content[:30] + ("..." if len(content) > 30 else "")
                }

        return list(sessions.values())


session_manager = SessionManager()
