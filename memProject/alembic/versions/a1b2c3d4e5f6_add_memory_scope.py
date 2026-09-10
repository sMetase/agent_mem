"""add_memory_scope — 记忆层级字段、约束、索引及历史数据回填

Revision ID: a1b2c3d4e5f6
Revises: 9d20e9cb00e2
Create Date: 2026-07-19 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9d20e9cb00e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 新增 memory_scope 列（先 nullable，回填后再设 NOT NULL）
    op.add_column('t_memory',
        sa.Column('memory_scope', sa.String(length=16), nullable=True,
                  comment='记忆层级/复用边界: user / session / task / agent')
    )

    # 2. 添加 CHECK 约束（使用 raw SQL 确保兼容性）
    op.execute(
        "ALTER TABLE t_memory ADD CONSTRAINT ck_t_memory_memory_scope "
        "CHECK (memory_scope IN ('user', 'session', 'task', 'agent'))"
    )

    # 3. 历史数据回填（保守规则，参见交接文档第 6.2 节）
    #    规则：
    #      1) 有 task_id → task
    #      2) 无 task_id 但有 session_id → session
    #      3) 其余 → user
    #    agent 不在此处自动推断（agent_id 仅表示生产者/调用者）
    conn = op.get_bind()
    total = conn.execute(
        sa.text("SELECT COUNT(*) FROM t_memory WHERE memory_scope IS NULL")
    ).scalar()

    if total and total > 0:
        conn.execute(
            sa.text("""
                UPDATE t_memory
                SET memory_scope = CASE
                    WHEN NULLIF(task_id, '') IS NOT NULL THEN 'task'
                    WHEN NULLIF(session_id, '') IS NOT NULL THEN 'session'
                    ELSE 'user'
                END
                WHERE memory_scope IS NULL
            """)
        )
        # 统计各层级回填数量
        scope_counts = conn.execute(
            sa.text("""
                SELECT memory_scope, COUNT(*) AS cnt
                FROM t_memory
                GROUP BY memory_scope
                ORDER BY memory_scope
            """)
        ).fetchall()
        print(f"[migration] 已回填 {total} 条记录的 memory_scope:")
        for row in scope_counts:
            if row.memory_scope:
                print(f"  - {row.memory_scope}: {row.cnt}")

    # 4. 创建统计索引
    op.create_index('idx_memory_user_status_scope', 't_memory',
                    ['user_id', 'status', 'memory_scope'], unique=False)
    op.create_index('idx_memory_user_scene_status_scope', 't_memory',
                    ['user_id', 'scene_id', 'status', 'memory_scope'], unique=False)

    # 5. 设置 NOT NULL（回填已完成）
    op.alter_column('t_memory', 'memory_scope',
                    existing_type=sa.String(length=16),
                    nullable=False)


def downgrade() -> None:
    op.drop_index('idx_memory_user_scene_status_scope', table_name='t_memory')
    op.drop_index('idx_memory_user_status_scope', table_name='t_memory')
    op.execute("ALTER TABLE t_memory DROP CONSTRAINT IF EXISTS ck_t_memory_memory_scope")
    op.drop_column('t_memory', 'memory_scope')
