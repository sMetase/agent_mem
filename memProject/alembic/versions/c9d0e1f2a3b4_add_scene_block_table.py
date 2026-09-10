"""add t_scene_block table

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "t_scene_block",
        sa.Column("scene_block_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("scene_id", sa.String(128), nullable=False),
        sa.Column("scene_name", sa.String(256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("memory_ids", sa.JSON(), nullable=True),
        sa.Column("heat", sa.Integer(), nullable=True, server_default="1"),
        sa.Column("status", sa.String(32), nullable=True, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("scene_block_id"),
    )
    op.create_index("idx_scene_block_user_scene", "t_scene_block", ["user_id", "scene_id"])


def downgrade():
    op.drop_index("idx_scene_block_user_scene", table_name="t_scene_block")
    op.drop_table("t_scene_block")
