"""add llm_model / llm_api_key to t_agent (agent 级 LLM 配置)

Revision ID: 5e6f7a8b9c0d
Revises: 4d5e6f7a8b9c
Create Date: 2026-08-21
"""
from alembic import op
import sqlalchemy as sa

revision = "5e6f7a8b9c0d"
down_revision = "4d5e6f7a8b9c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("t_agent", sa.Column("llm_model", sa.String(128), nullable=True))
    op.add_column("t_agent", sa.Column("llm_api_key", sa.String(256), nullable=True))


def downgrade():
    op.drop_column("t_agent", "llm_api_key")
    op.drop_column("t_agent", "llm_model")
