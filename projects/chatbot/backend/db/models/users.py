from datetime import datetime, timezone

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


def _current_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    salt: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_current_timestamp)