"""add user_id to t_agent (智能体归属注册者，控制台按 user_id 过滤)

背景：t_agent 此前没有 user_id，智能体归属完全靠 scene_id → t_scene.user_id 间接决定。
API 注册时若没把注册者 user_id 落库，控制台「智能体管理」就查不到该智能体（用户反馈）。
本迁移：
  1. t_agent 增加 user_id 列 + 索引
  2. 回填：历史智能体的 user_id 回填为其场景 owner（无主场景保持 NULL，
     由列表查询的「场景归属兜底」逻辑保证仍可见）

Revision ID: 7a8b9c0d1e2f
Revises: 6f7a8b9c0d1e
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa

revision = "7a8b9c0d1e2f"
down_revision = "6f7a8b9c0d1e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("t_agent", sa.Column("user_id", sa.String(128), nullable=True))
    op.create_index("ix_t_agent_user_id", "t_agent", ["user_id"])

    # 回填：智能体归属其场景 owner（Oracle 相关子查询 UPDATE；无主场景保持 NULL）
    op.execute(
        """
        UPDATE t_agent a
        SET a.user_id = (
            SELECT s.user_id FROM t_scene s WHERE s.scene_id = a.scene_id
        )
        WHERE a.user_id IS NULL
        """
    )


def downgrade():
    op.drop_index("ix_t_agent_user_id", table_name="t_agent")
    op.drop_column("t_agent", "user_id")
