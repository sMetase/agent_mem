"""add_status_column_and_indexes

Revision ID: 9d20e9cb00e2
Revises: 52c1d1f2e3a4
Create Date: 2026-07-14 12:18:21.244848
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '9d20e9cb00e2'
down_revision: Union[str, None] = '52c1d1f2e3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 添加 status 列（ORM 已定义但 DB 中不存在，先 ADD 而非 ALTER）
    op.add_column('t_interaction_record',
        sa.Column('status', sa.String(length=32), nullable=True,
                   server_default='pending_extract',
                   comment='记录状态: pending_extract / processed / failed')
    )
    # 回填已有记录
    op.execute("UPDATE t_interaction_record SET status = 'pending_extract' WHERE status IS NULL")

    # 2. 调整 interaction_type 列（已存在的列，ALTER 即可）
    op.alter_column('t_interaction_record', 'interaction_type',
        existing_type=sa.VARCHAR(length=32),
        nullable=True,
        comment=None,
        existing_comment='交互类型: dialogue / session / task_process')

    # 3. 创建 status 相关索引（interaction_type 相关索引已由 52c1d1f2e3a4 创建）
    op.create_index(op.f('ix_t_interaction_record_status'), 't_interaction_record',
        ['status'], unique=False)
    op.create_index('idx_interaction_status', 't_interaction_record',
        ['status', 'recorded_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_interaction_status', table_name='t_interaction_record')
    op.drop_index(op.f('ix_t_interaction_record_status'), table_name='t_interaction_record')
    op.drop_index(op.f('ix_t_interaction_record_interaction_type'), table_name='t_interaction_record')
    op.drop_index('idx_interaction_type_user', table_name='t_interaction_record')
    op.alter_column('t_interaction_record', 'interaction_type',
        existing_type=sa.VARCHAR(length=32),
        nullable=False,
        comment='交互类型: dialogue / session / task_process')
    op.drop_column('t_interaction_record', 'status')
