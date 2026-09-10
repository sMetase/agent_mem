"""Create the base tables used by the subsequent migrations.

Revision ID: 50bedfeed277
Revises:
Create Date: 2026-07-01

The project previously treated these tables as externally provisioned. That
works for an existing database, but a fresh Docker volume has no tables for
the first ALTER TABLE migration to modify.
"""
from alembic import op
import sqlalchemy as sa

from app.core.database import Base
from app.models import base as _models  # noqa: F401

revision = "50bedfeed277"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # These columns are introduced by later revisions. Keeping them out of
    # the baseline is important: later ALTER TABLE operations must remain
    # valid on a fresh database.
    later_columns = {
        "t_user": {"username", "password_hash"},
        "t_agent": {"llm_model", "llm_api_key"},
        "t_scene": {"user_id"},
        "t_session": {"title"},
        "t_task": {"updated_at"},
        "t_interaction_record": {"interaction_type", "status"},
        "t_memory": {"seq_id", "memory_scope", "deleted_at"},
        "t_retrieval_request": {"retrieval_mode"},
    }
    base_table_names = (
        "t_user",
        "t_agent",
        "t_scene",
        "t_session",
        "t_task",
        "t_interaction_record",
        "t_memory",
        "t_memory_relation",
        "t_retrieval_request",
        "t_retrieval_result",
        "t_api_log",
    )

    metadata = sa.MetaData()
    source_tables = Base.metadata.tables
    for table_name in base_table_names:
        source = source_tables[table_name]
        excluded = later_columns.get(table_name, set())
        table = sa.Table(
            table_name,
            metadata,
            *[
                column.copy()
                for column in source.columns
                if column.name not in excluded
            ],
        )
        if table_name == "t_memory":
            table.append_column(sa.Column("replaced_by", sa.String(64), nullable=True))
        available_columns = set(table.c.keys())
        for index in source.indexes:
            index_columns = [column.name for column in index.columns]
            if (
                set(index_columns) <= available_columns
                and index.name not in {item.name for item in table.indexes}
            ):
                sa.Index(
                    index.name,
                    *(table.c[column_name] for column_name in index_columns),
                    unique=index.unique,
                )

    metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade():
    pass
