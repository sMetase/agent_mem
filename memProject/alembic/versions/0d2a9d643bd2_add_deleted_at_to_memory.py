"""add deleted_at to t_memory

Revision ID: 0d2a9d643bd2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0d2a9d643bd2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("t_memory", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_memory_deleted_at", "t_memory", ["deleted_at"])


def downgrade():
    op.drop_index("idx_memory_deleted_at", table_name="t_memory")
    op.drop_column("t_memory", "deleted_at")
