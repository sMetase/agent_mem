"""Integration tests for the L3 persona schema and upsert behavior."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, inspect, select, text


def _sync_engine():
    from sqlalchemy import create_engine
    from app.core.config import get_settings

    settings = get_settings()
    return create_engine(settings.database.sync_url)


def _database_is_available() -> bool:
    engine = _sync_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_l3_persona_upsert_requires_unique_schema(monkeypatch):
    """Verify the migration contract and that L3 updates, rather than duplicates."""
    if not _database_is_available():
        pytest.skip("PostgreSQL 不可用，跳过 L3 集成测试")

    from app.core.database import async_session_factory
    from app.models.base import Persona, SceneBlock
    from app.services import l3_persona

    engine = _sync_engine()
    user_id = f"test_l3_{uuid4().hex}"
    scene_id = f"scene_{uuid4().hex}"
    scene_block_id = f"block_{uuid4().hex}"

    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert "t_interaction_record" in inspector.get_table_names()
            assert "t_persona" in inspector.get_table_names()
            unique_constraints = inspector.get_unique_constraints("t_persona")
            assert any(
                constraint["name"] == "uq_t_persona_user_scene"
                and constraint["column_names"] == ["user_id", "scene_id"]
                for constraint in unique_constraints
            )

        async with async_session_factory() as db:
            db.add(
                SceneBlock(
                    scene_block_id=scene_block_id,
                    user_id=user_id,
                    scene_id=scene_id,
                    scene_name="技术偏好",
                    content="用户确定后端使用 PostgreSQL。",
                    status="active",
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

            async def fake_resolve_llm_config(db, agent_id=None):
                return "test-model", "test-key"

            responses = iter(
                [
                    "用户偏好使用 PostgreSQL 作为后端数据库。",
                    "用户明确选择 PostgreSQL，并重视关系型数据一致性。",
                ]
            )

            async def fake_chat_completion(**kwargs):
                return next(responses)

            monkeypatch.setattr(
                l3_persona, "resolve_llm_config", fake_resolve_llm_config
            )
            monkeypatch.setattr(
                l3_persona.llm_client, "chat_completion", fake_chat_completion
            )

            first = await l3_persona.generate_persona(db, user_id, scene_id)
            assert first["content"].startswith("用户偏好使用 PostgreSQL")

            persona_before = await db.scalar(
                select(Persona).where(
                    Persona.user_id == user_id,
                    Persona.scene_id == scene_id,
                )
            )
            assert persona_before is not None

            block = await db.scalar(
                select(SceneBlock).where(SceneBlock.scene_block_id == scene_block_id)
            )
            block.updated_at = datetime.now(timezone.utc)
            await db.commit()

            second = await l3_persona.generate_persona(db, user_id, scene_id)
            assert "关系型数据一致性" in second["content"]
            assert second["persona_id"] == persona_before.persona_id

            count = await db.scalar(
                select(func.count()).select_from(Persona).where(
                    Persona.user_id == user_id,
                    Persona.scene_id == scene_id,
                )
            )
            assert count == 1
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM t_persona WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            connection.execute(
                text("DELETE FROM t_scene_block WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
        engine.dispose()