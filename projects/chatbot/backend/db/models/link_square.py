from datetime import datetime, timezone

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


def _current_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class LinkSquare(Base):
    __tablename__ = "link_square"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    owner_username: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_current_timestamp)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_current_timestamp)