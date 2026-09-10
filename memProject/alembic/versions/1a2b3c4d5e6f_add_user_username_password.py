"""add username/password_hash to t_user (控制台登录即注册)

Revision ID: 1a2b3c4d5e6f
Revises: f5a6b7c8d9e0
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "1a2b3c4d5e6f"
down_revision = "9c8d7e6f5a4b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("t_user", sa.Column("username", sa.String(128), nullable=True))
    op.add_column("t_user", sa.Column("password_hash", sa.String(256), nullable=True))
    op.create_index("ix_t_user_username", "t_user", ["username"], unique=True)


def downgrade():
    op.drop_index("ix_t_user_username", table_name="t_user")
    op.drop_column("t_user", "password_hash")
    op.drop_column("t_user", "username")
