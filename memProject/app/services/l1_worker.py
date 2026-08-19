# -*- coding: utf-8 -*-
"""
L1 异步抽取 worker — 后台定时扫描 L0 增量，异步抽 L1。

设计（对应方案块 A）：
- 游标落 DB（t_memory_cursor），key = `${user_id}:${agent_id}:${session_id}`，值 = 最后处理的 L0 自增 id。
- over-fetch：读 20 处理 10，满批（读满 20）立即续跑，读不满走 idle timer。
- 失败不推进游标（下轮重抽同一批，保证不丢）。
- 并发：asyncio.Semaphore 限制 20-30 并发协程。
- 抽取按 (user, agent, session) 分组；scene_id/task_id 从 L0 记录取（不依赖 session，避免 scene_id=None）。
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.core.database import async_session_factory
from app.core.logger import get_logger
from app.models.base import InteractionRecord, MemoryCursor
from app.services.memory_pipeline import memory_pipeline
from app.services.worker_stats import record

logger = get_logger("l1_worker")

# 方案 Q5 / Q2 参数
L1_BATCH_QUERY = 20     # over-fetch：读 20
L1_BATCH_PROCESS = 10   # 处理 10
WORKER_CONCURRENCY = 25  # 20-30 并发
POLL_INTERVAL_SECONDS = 5  # idle 轮询间隔


def _cursor_key(user_id: str, agent_id: str, session_id: str) -> str:
    return f"{user_id}:{agent_id}:{session_id}"


async def _read_pending_groups(db, limit: int = 200):
    """查出有 pending_extract L0 的 (user_id, agent_id, session_id) 组。"""
    from sqlalchemy import func
    stmt = (
        select(
            InteractionRecord.user_id,
            InteractionRecord.agent_id,
            InteractionRecord.session_id,
        )
        .where(InteractionRecord.status == "pending_extract")
        .group_by(
            InteractionRecord.user_id,
            InteractionRecord.agent_id,
            InteractionRecord.session_id,
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.all()


async def _process_group(user_id, agent_id, session_id) -> bool:
    """处理一个 session 组：读增量 L0 → 拼 text → 抽 L1 → 推进游标。

    Returns:
        True 表示本轮读满（有积压，需立即续跑）；False 表示读不满（小尾巴）。
    """
    async with async_session_factory() as db:
        cursor_key = _cursor_key(user_id, agent_id, session_id)

        # 读游标
        cursor_result = await db.execute(
            select(MemoryCursor).where(MemoryCursor.cursor_key == cursor_key)
        )
        cursor = cursor_result.scalar_one_or_none()
        last_id = cursor.last_processed_id if cursor else 0

        # 读增量 L0（over-fetch 20）
        stmt = (
            select(InteractionRecord)
            .where(
                InteractionRecord.user_id == user_id,
                InteractionRecord.agent_id == agent_id,
                InteractionRecord.session_id == session_id,
                InteractionRecord.id > last_id,
                InteractionRecord.status == "pending_extract",
            )
            .order_by(InteractionRecord.id)
            .limit(L1_BATCH_QUERY)
        )
        result = await db.execute(stmt)
        records = list(result.scalars().all())

        if not records:
            return False

        full_batch = len(records) >= L1_BATCH_QUERY  # 读满 = 有积压
        process_records = records[:L1_BATCH_PROCESS]

        # Q3：拼 text，[record_id] [role]: content（带 record_id 供 source_record_ids 追溯）
        text = "\n".join(f"[{r.record_id}] [{r.role}]: {r.content}" for r in process_records)
        scene_id = process_records[0].scene_id
        if scene_id is None:
            # 兜底：agent 1:1 绑 scene，从 agent 推导。L0.scene_id 不能 None（否则 L1→L2 归属链断）
            from app.models.base import Agent
            ar = await db.execute(select(Agent.scene_id).where(Agent.agent_id == agent_id))
            scene_id = ar.scalar_one_or_none()
        task_id = process_records[0].task_id
        source_record_ids = [r.record_id for r in process_records]

        try:
            await memory_pipeline.run(
                text=text,
                user_id=user_id,
                agent_id=agent_id,
                scene_id=scene_id,
                session_id=session_id,
                task_id=task_id,
                source_record_ids=source_record_ids,
                db=db,
            )
        except Exception as e:
            # 失败：rollback 回滚，status 保持 pending_extract 不改、游标不推进
            # → 下轮两个机制（status='pending_extract' 发现 pending + id > cursor 读增量）都能再次找到，自然重抽
            await db.rollback()
            logger.error(
                f"L1 抽取失败（status 保持 pending_extract，游标不推进，下轮重抽）: cursor_key={cursor_key}, "
                f"batch={len(process_records)}, error={e}"
            )
            record("l1", False)
            return full_batch

        # 成功：推进游标 + 标记 processed（status 管单条状态，辅助）
        new_last_id = process_records[-1].id
        if cursor:
            cursor.last_processed_id = new_last_id
            cursor.updated_at = datetime.now(timezone.utc)
        else:
            db.add(MemoryCursor(cursor_key=cursor_key, last_processed_id=new_last_id))

        process_ids = [r.id for r in process_records]
        await db.execute(
            update(InteractionRecord)
            .where(InteractionRecord.id.in_(process_ids))
            .values(status="processed", processed=True)
        )
        await db.commit()

        logger.info(
            f"L1 抽取完成: cursor_key={cursor_key}, processed={len(process_records)}, "
            f"new_last_id={new_last_id}"
        )
        record("l1", True)
        return full_batch


async def l1_worker_loop(stop_event: asyncio.Event | None = None):
    """L1 抽取主循环：定时轮询 + over-fetch 满批续跑。"""
    semaphore = asyncio.Semaphore(WORKER_CONCURRENCY)
    logger.info(f"L1 worker 启动: 并发={WORKER_CONCURRENCY}, 批处理={L1_BATCH_PROCESS}, 查询={L1_BATCH_QUERY}")

    while True:
        if stop_event and stop_event.is_set():
            break

        try:
            async with async_session_factory() as db:
                groups = await _read_pending_groups(db)

            if groups:
                async def _run(g):
                    async with semaphore:
                        try:
                            return await _process_group(g.user_id, g.agent_id, g.session_id)
                        except Exception as e:
                            logger.error(
                                f"处理 group 失败: user={g.user_id}, session={g.session_id}, error={e}"
                            )
                            return False

                results = await asyncio.gather(*[_run(g) for g in groups])
                # 有满批（积压）→ 立即续跑，不等 timer
                if any(results):
                    continue
        except Exception as e:
            logger.error(f"L1 worker 循环异常: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
