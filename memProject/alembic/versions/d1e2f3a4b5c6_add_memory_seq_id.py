"""add seq_id to t_memory (单调自增，L2 增量游标用)

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("t_memory", sa.Column("seq_id", sa.BigInteger(), nullable=True))
    # 回填：按 created_at + id 排序，赋单调递增序号
    op.execute("""
        UPDATE t_memory SET seq_id = sub.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS rn FROM t_memory
        ) AS sub
        WHERE t_memory.id = sub.id
    """)
    op.alter_column("t_memory", "seq_id", nullable=False)
    # 自增序列 + 默认值
    op.execute("CREATE SEQUENCE t_memory_seq_id_seq")
    op.execute("ALTER TABLE t_memory ALTER COLUMN seq_id SET DEFAULT nextval('t_memory_seq_id_seq')")
    op.execute("SELECT setval('t_memory_seq_id_seq', COALESCE((SELECT MAX(seq_id) FROM t_memory), 1))")
    op.create_index("idx_memory_seq_id", "t_memory", ["seq_id"])


def downgrade():
    op.drop_index("idx_memory_seq_id", table_name="t_memory")
    op.execute("ALTER TABLE t_memory ALTER COLUMN seq_id DROP DEFAULT")
    op.execute("DROP SEQUENCE t_memory_seq_id_seq")
    op.drop_column("t_memory", "seq_id")
