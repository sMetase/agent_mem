"""add_interaction_type

Revision ID: 52c1d1f2e3a4
Revises: 50bedfeed277
Create Date: 2026-07-14 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '52c1d1f2e3a4'
down_revision: Union[str, None] = '50bedfeed277'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('t_interaction_record',
        sa.Column('interaction_type', sa.String(length=32), nullable=True, server_default='dialogue')
    )
    op.create_index('idx_interaction_type_user', 't_interaction_record',
        ['interaction_type', 'user_id'], unique=False
    )
    # backfill existing rows
    op.execute("UPDATE t_interaction_record SET interaction_type = 'dialogue' WHERE interaction_type IS NULL")


def downgrade() -> None:
    op.drop_index('idx_interaction_type_user', table_name='t_interaction_record')
    op.drop_column('t_interaction_record', 'interaction_type')
