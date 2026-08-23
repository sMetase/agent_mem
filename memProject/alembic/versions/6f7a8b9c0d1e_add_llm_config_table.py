"""add t_llm_config table (全局默认 LLM 配置)

Revision ID: 6f7a8b9c0d1e
Revises: 5e6f7a8b9c0d
Create Date: 2026-08-21
"""
from alembic import op
import sqlalchemy as sa

revision = "6f7a8b9c0d1e"
down_revision = "5e6f7a8b9c0d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "t_llm_config",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("llm_model", sa.String(128), nullable=True),
        sa.Column("llm_api_key", sa.String(256), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("t_llm_config")
