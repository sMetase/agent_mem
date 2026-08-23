# -*- coding: utf-8 -*-
"""
L2 场景聚合 worker — 后台定时扫描 L1 增量，聚合成场景块。

设计（对应方案块 B 决策 3）：
- 级联触发（L1 完成后，L2 定时扫描 L1 增量）。
- 固定 delay（轻量版简化三级 timer）。
- 增量消费：只消费「新产生」的 L1 记忆（seq_id > l2_cursor），不消费 update 过的（避免重复聚合）。
- 按 (scene_id, user_id) 分组，跨 agent。
"""

import asyncio

from sqlalchemy import select, func

from app.core.database import async_session_factory
from app.core.logger import get_logger
from app.models.base import Memory, MemoryCursor, SceneBlock
from app.services.l2_scene import aggregate_scenes, apply_scene_operations
from app.services.llm_config import resolve_llm_config
from app.services.worker_stats import record

logger = get_logger("l2_worker")

L2_POLL_INTERVAL = 10   # 轮询间隔（秒）
L2_BATCH_LIMIT = 50     # 每组最多读多少条新 L1 记忆


def _l2_cursor_key(scene_id: str, user_id: str) -> str:
    return f"l2:{scene_id}:{user_id}"


async def _read_l1_groups(db, limit: int = 200):
    """查出有 active L1 记忆的 (scene_id, user_id) 组。"""
    stmt = (
        select(Memory.scene_id, Memory.user_id)
        .where(Memory.status == "active", Memory.scene_id.isnot(None))
        .group_by(Memory.scene_id, Memory.user_id)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.all()


async def _process_group(scene_id: str, user_id: str) -> int:
    """处理一个 (scene_id, user_id) 组：读新 L1 记忆 → 聚合 → 落库 → 推进游标。"""
    cursor_key = _l2_cursor_key(scene_id, user_id)
    async with async_session_factory() as db:
        cursor_result = await db.execute(
            select(MemoryCursor).where(MemoryCursor.cursor_key == cursor_key)
        )
        cursor = cursor_result.scalar_one_or_none()
        last_seq = cursor.last_processed_id if cursor else 0

        stmt = (
            select(Memory)
            .where(
                Memory.scene_id == scene_id,
                Memory.user_id == user_id,
                Memory.status == "active",
                Memory.seq_id > last_seq,
            )
            .order_by(Memory.seq_id)
            .limit(L2_BATCH_LIMIT)
        )
        result = await db.execute(stmt)
        new_memories = list(result.scalars().all())

        if not new_memories:
            return 0

        new_memory_dicts = [
            {"memory_id": m.memory_id, "content": m.content, "memory_type": m.memory_type}
            for m in new_memories
        ]

        block_result = await db.execute(
            select(SceneBlock).where(
                SceneBlock.user_id == user_id, SceneBlock.scene_id == scene_id
            )
        )
        existing_blocks = [
            {"scene_block_id": b.scene_block_id, "scene_name": b.scene_name, "content": b.content}
            for b in block_result.scalars().all()
        ]

        model, api_key = await resolve_llm_config(db, agent_id=None)
        operations = await aggregate_scenes(
            user_id, scene_id, new_memory_dicts, existing_blocks,
            model=model, api_key=api_key,
        )
        if not operations:
            # LLM 聚合失败：不推进游标（下轮重试）
            record("l2", False)
            return 0

        await apply_scene_operations(db, user_id, scene_id, operations)

        # 推进 L2 游标（本批最大 seq_id）
        new_last_seq = new_memories[-1].seq_id
        if cursor:
            cursor.last_processed_id = new_last_seq
        else:
            db.add(MemoryCursor(cursor_key=cursor_key, last_processed_id=new_last_seq))
        await db.commit()

        logger.info(
            f"L2 聚合完成: scene={scene_id}, user={user_id}, "
            f"new_memories={len(new_memories)}, ops={len(operations)}, cursor={new_last_seq}"
        )
        record("l2", True)
        return len(new_memories)


async def l2_worker_loop(stop_event: asyncio.Event | None = None):
    """L2 场景聚合主循环。"""
    logger.info(f"L2 场景聚合 worker 启动: poll={L2_POLL_INTERVAL}s, batch={L2_BATCH_LIMIT}")

    while True:
        if stop_event and stop_event.is_set():
            break

        try:
            async with async_session_factory() as db:
                groups = await _read_l1_groups(db)

            for g in groups:
                try:
                    await _process_group(g.scene_id, g.user_id)
                except Exception as e:
                    logger.error(
                        f"L2 处理组失败: scene={g.scene_id}, user={g.user_id}, error={e}"
                    )
        except Exception as e:
            logger.error(f"L2 worker 循环异常: {e}")

        await asyncio.sleep(L2_POLL_INTERVAL)
