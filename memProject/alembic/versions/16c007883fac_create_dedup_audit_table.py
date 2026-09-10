"""create t_dedup_audit table

Revision ID: 16c007883fac
Revises: 0d2a9d643bd2
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "16c007883fac"
down_revision = "0d2a9d643bd2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "t_dedup_audit",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("audit_id", sa.String(64), nullable=False),
        sa.Column("candidate_content", sa.Text(), nullable=True),
        sa.Column("candidate_memory_type", sa.String(64), nullable=True),
        sa.Column("matched_memory_id", sa.String(64), nullable=True),
        sa.Column("matched_content", sa.Text(), nullable=True),
        sa.Column("vector_score", sa.Float(), nullable=True),
        sa.Column("keyword_overlap", sa.Float(), nullable=True),
        sa.Column("identity_match", sa.Boolean(), server_default="false", nullable=True),
        sa.Column("composite_score", sa.Float(), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("before_content", sa.Text(), nullable=True),
        sa.Column("after_content", sa.Text(), nullable=True),
        sa.Column("old_status", sa.String(32), nullable=True),
        sa.Column("new_status", sa.String(32), nullable=True),
        sa.Column("old_version", sa.Integer(), nullable=True),
        sa.Column("new_version", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.String(128), nullable=True),
        sa.Column("task_id", sa.String(128), nullable=True),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_dedup_audit_matched", "t_dedup_audit", ["matched_memory_id", "created_at"])
    op.create_index("idx_dedup_audit_action", "t_dedup_audit", ["action", "created_at"])
    op.create_index("idx_dedup_audit_user", "t_dedup_audit", ["user_id", "created_at"])
    op.create_index(op.f("ix_t_dedup_audit_audit_id"), "t_dedup_audit", ["audit_id"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_t_dedup_audit_audit_id"), table_name="t_dedup_audit")
    op.drop_index("idx_dedup_audit_user", table_name="t_dedup_audit")
    op.drop_index("idx_dedup_audit_action", table_name="t_dedup_audit")
    op.drop_index("idx_dedup_audit_matched", table_name="t_dedup_audit")
    op.drop_table("t_dedup_audit")
