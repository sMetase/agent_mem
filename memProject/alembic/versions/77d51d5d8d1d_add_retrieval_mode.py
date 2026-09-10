"""add retrieval_mode to t_retrieval_request

Revision ID: 77d51d5d8d1d
Revises: 16c007883fac
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "77d51d5d8d1d"
down_revision = "16c007883fac"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("t_retrieval_request", sa.Column("retrieval_mode", sa.String(32), nullable=True, index=True))


def downgrade():
    op.drop_index(op.f("ix_t_retrieval_request_retrieval_mode"), table_name="t_retrieval_request")
    op.drop_column("t_retrieval_request", "retrieval_mode")
