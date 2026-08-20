"""add user_id to t_scene (场景私有隔离)

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = "2b3c4d5e6f7a"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("t_scene", sa.Column("user_id", sa.String(128), nullable=True))
    op.create_index("ix_t_scene_user_id", "t_scene", ["user_id"])


def downgrade():
    op.drop_index("ix_t_scene_user_id", table_name="t_scene")
    op.drop_column("t_scene", "user_id")
