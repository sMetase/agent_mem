"""backfill last_seq_id for existing personas (NULL -> max active L1 seq_id)

Revision ID: 9c8d7e6f5a4b
Revises: 5a6b7c8d9e0f
Create Date: 2026-08-18
"""
from alembic import op

revision = "9c8d7e6f5a4b"
down_revision = "5a6b7c8d9e0f"
branch_labels = None
depends_on = None


def upgrade():
    # 回填存量画像的 last_seq_id（f5a6b7c8d9e0 只 add_column 没回填，
    # 导致 NULL 被当 0 → L3 触发计数永远认为"有记忆没消费"→ 每 15s 空转跳过）
    op.execute("""
        UPDATE t_persona p
        SET last_seq_id = COALESCE(
            (SELECT max(m.seq_id) FROM t_memory m
             WHERE m.user_id = p.user_id
               AND m.scene_id = p.scene_id
               AND m.status = 'active'), 0)
        WHERE p.last_seq_id IS NULL
    """)


def downgrade():
    # 数据回填无法干净回滚（分不清哪些是回填值），降级为 no-op
    pass
