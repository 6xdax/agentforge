"""initial schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-05-17 00:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=36), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=64), nullable=False),
        sa.Column("salt", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("thinking", sa.Text(), nullable=True),
        sa.Column("tool_calls", sa.Text(), nullable=True),
        sa.Column("usage", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")