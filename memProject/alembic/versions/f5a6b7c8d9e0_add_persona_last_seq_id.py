"""add last_seq_id to t_persona (L3 触发计数用)

Revision ID: f5a6b7c8d9e0
Revises: e3f4a5b6c7d8
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "f5a6b7c8d9e0"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("t_persona", sa.Column("last_seq_id", sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column("t_persona", "last_seq_id")
