"""add t_memory_cursor table

Revision ID: b7c8d9e0f1a2
Revises: e7f8a9b0c1d2
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a2"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "t_memory_cursor",
        sa.Column("cursor_key", sa.String(255), nullable=False),
        sa.Column("last_processed_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("cursor_key"),
    )


def downgrade():
    op.drop_table("t_memory_cursor")
