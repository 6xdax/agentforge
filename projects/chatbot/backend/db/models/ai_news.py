from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


def _current_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class AiNewsItem(Base):
    __tablename__ = "ai_news"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_current_timestamp)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_current_timestamp)