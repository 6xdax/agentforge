"""user item configs

Revision ID: 0002_user_item_configs
Revises: 0001_initial_schema
Create Date: 2026-05-17 00:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_user_item_configs"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_item_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("item_name", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "category", "item_name", name="uq_user_item_category_name"),
    )
    op.create_index("ix_user_item_configs_user_id", "user_item_configs", ["user_id"], unique=False)
    op.create_index("ix_user_item_configs_category", "user_item_configs", ["category"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_item_configs_category", table_name="user_item_configs")
    op.drop_index("ix_user_item_configs_user_id", table_name="user_item_configs")
    op.drop_table("user_item_configs")