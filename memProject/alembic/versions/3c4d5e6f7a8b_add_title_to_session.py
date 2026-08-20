"""add title to t_session (会话可读标题)

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = "3c4d5e6f7a8b"
down_revision = "2b3c4d5e6f7a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("t_session", sa.Column("title", sa.String(512), nullable=True))


def downgrade():
    op.drop_column("t_session", "title")
