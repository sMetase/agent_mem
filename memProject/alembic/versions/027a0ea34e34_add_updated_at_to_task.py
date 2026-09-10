"""add updated_at to t_task

Revision ID: 027a0ea34e34
Revises: 77d51d5d8d1d
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "027a0ea34e34"
down_revision = "77d51d5d8d1d"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("t_task", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE t_task SET updated_at = started_at WHERE updated_at IS NULL")
    op.alter_column("t_task", "updated_at", nullable=False)


def downgrade():
    op.drop_column("t_task", "updated_at")
