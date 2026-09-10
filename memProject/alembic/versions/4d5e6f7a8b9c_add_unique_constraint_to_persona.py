"""add unique constraint (user_id, scene_id) to t_persona

Revision ID: 4d5e6f7a8b9c
Revises: 3c4d5e6f7a8b
Create Date: 2026-08-21
"""
from alembic import op

revision = "4d5e6f7a8b9c"
down_revision = "3c4d5e6f7a8b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_t_persona_user_scene", "t_persona", ["user_id", "scene_id"]
    )


def downgrade():
    op.drop_constraint("uq_t_persona_user_scene", "t_persona", type_="unique")
