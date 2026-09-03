"""Create the initial database schema.

Revision ID: 50bedfeed277
Revises:
Create Date: 2026-07-01

"""
from alembic import op

from app.core.database import Base
from app.models import base as _models  # noqa: F401

revision = "50bedfeed277"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.exec_driver_sql("CREATE SEQUENCE IF NOT EXISTS t_memory_seq_id_seq")
    Base.metadata.create_all(bind=bind)


def downgrade():
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
    bind.exec_driver_sql("DROP SEQUENCE IF EXISTS t_memory_seq_id_seq")
