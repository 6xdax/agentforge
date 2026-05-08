from typing import TYPE_CHECKING, Optional

from agent import SQLiteMemory

if TYPE_CHECKING:
    from agent import Agent


class SessionManager:
    def __init__(self, db_path: str = "db/chatbot_memory.db"):
        self.sessions: dict[str, dict] = {}
        self.memory = SQLiteMemory(db_path=db_path, session_id="default")

    def create_session(self, session_id: str, agent: "Agent"):
        self.sessions[session_id] = {"agent": agent}

    def get_session(self, session_id: str) -> Optional[dict]:
        return self.sessions.get(session_id)

    async def add_to_history(self, session_id: str, role: str, content: str):
        if session_id in self.sessions:
            await self.memory.add({"role": role, "content": content})

    async def get_history(self, session_id: str, limit: int = 100) -> list:
        return await self.memory.get_messages(limit=limit)


session_manager = SessionManager()
