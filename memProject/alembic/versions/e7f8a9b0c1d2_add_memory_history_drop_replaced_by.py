"""add t_memory_history table, drop replaced_by column

Revision ID: e7f8a9b0c1d2
Revises: 027a0ea34e34
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "027a0ea34e34"
branch_labels = None
depends_on = None


def upgrade():
    # 1. 建 t_memory_history 表
    op.create_table(
        "t_memory_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("memory_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("key_points", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("entities", sa.JSON(), nullable=True),
        sa.Column("importance", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("action", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_memory_history_memory", "t_memory_history", ["memory_id", "version"])

    # 2. 删 replaced_by 列
    op.drop_column("t_memory", "replaced_by")


def downgrade():
    op.add_column(
        "t_memory",
        sa.Column("replaced_by", sa.String(64), nullable=True),
    )
    op.drop_index("idx_memory_history_memory", table_name="t_memory_history")
    op.drop_table("t_memory_history")
