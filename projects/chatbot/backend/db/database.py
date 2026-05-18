from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy import text

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .base import Base

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DB_DATA_DIR = BACKEND_ROOT / "db" / "data"
DEFAULT_DB_PATH = DB_DATA_DIR / "app.db"
DEFAULT_AGENT_MEMORY_DB_PATH = DB_DATA_DIR / "agent_memory.db"


def get_agent_memory_db_path() -> Path:
    DB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_AGENT_MEMORY_DB_PATH


def build_database_url(database_url_or_path: str | None = None) -> str:
    DB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not database_url_or_path:
        return f"sqlite+aiosqlite:///{DEFAULT_DB_PATH.as_posix()}"

    if "://" in database_url_or_path:
        return database_url_or_path

    path = Path(database_url_or_path)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{path.as_posix()}"


@lru_cache(maxsize=None)
def create_async_engine_for(database_url_or_path: str | None = None) -> AsyncEngine:
    return create_async_engine(build_database_url(database_url_or_path), future=True)


@lru_cache(maxsize=None)
def create_sessionmaker_for(database_url_or_path: str | None = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(create_async_engine_for(database_url_or_path), expire_on_commit=False)


async def init_database(database_url_or_path: str | None = None) -> None:
    engine = create_async_engine_for(database_url_or_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        table_info = await conn.execute(text("PRAGMA table_info(messages)"))
        columns = {row[1] for row in table_info.fetchall()}
        if "attachments" not in columns:
            await conn.execute(text("ALTER TABLE messages ADD COLUMN attachments TEXT"))