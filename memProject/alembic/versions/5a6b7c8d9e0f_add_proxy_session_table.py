"""add t_proxy_session table (Proxy sessionKey → session_id 映射，落 DB)

Revision ID: a1b2c3d4e5f6
Revises: f5a6b7c8d9e0
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "5a6b7c8d9e0f"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "t_proxy_session",
        sa.Column("space_id", sa.String(128), nullable=False),
        sa.Column("session_key", sa.String(256), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("space_id", "session_key"),
    )


def downgrade():
    op.drop_table("t_proxy_session")
