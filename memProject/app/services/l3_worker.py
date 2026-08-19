# -*- coding: utf-8 -*-
"""
L3 画像 worker — 按「L1 新记忆条数」触发，消费变化场景生成画像。

设计（对应方案块 C 决策 C1）：
- 按「自上次画像以来的 L1 新记忆数」触发（memories_since_last_persona >= N）。
- 其他触发（主动请求/冷启动/恢复/首次）由 generate_persona 内部的增量逻辑兜底。
"""

import asyncio

from sqlalchemy import select, func

from app.core.database import async_session_factory
from app.core.logger import get_logger
from app.models.base import Memory, Persona
from app.services.l3_persona import generate_persona
from app.services.worker_stats import record

logger = get_logger("l3_worker")

L3_POLL_INTERVAL = 15  # 轮询间隔（秒）
L3_TRIGGER_N = 5       # 攒够 N 条新 L1 记忆才触发画像更新


async def l3_worker_loop(stop_event: asyncio.Event | None = None):
    """L3 画像主循环。"""
    logger.info(f"L3 画像 worker 启动: poll={L3_POLL_INTERVAL}s, trigger_n={L3_TRIGGER_N}")

    while True:
        if stop_event and stop_event.is_set():
            break

        try:
            async with async_session_factory() as db:
                # 查出有 active L1 记忆的 (scene_id, user_id) 组
                result = await db.execute(
                    select(Memory.scene_id, Memory.user_id)
                    .where(Memory.status == "active", Memory.scene_id.isnot(None))
                    .group_by(Memory.scene_id, Memory.user_id)
                )
                groups = result.all()

                for g in groups:
                    # 读该组 persona 的 last_seq_id（C1 触发计数游标）
                    p_result = await db.execute(
                        select(Persona).where(
                            Persona.user_id == g.user_id, Persona.scene_id == g.scene_id
                        )
                    )
                    persona = p_result.scalar_one_or_none()
                    last_seq = persona.last_seq_id if persona else 0

                    # 数「自上次画像以来」的新 L1 记忆（seq_id 差值）
                    cnt_stmt = select(func.count(Memory.memory_id)).where(
                        Memory.user_id == g.user_id,
                        Memory.scene_id == g.scene_id,
                        Memory.status == "active",
                        Memory.seq_id > (last_seq or 0),
                    )
                    cnt = (await db.execute(cnt_stmt)).scalar() or 0

                    if cnt >= L3_TRIGGER_N:
                        try:
                            res = await generate_persona(db, g.user_id, g.scene_id)
                            if res.get("error"):
                                record("l3", False)
                            elif (res.get("changed_scenes") or 0) > 0:
                                record("l3", True)
                        except Exception as e:
                            record("l3", False)
                            logger.error(
                                f"L3 画像生成失败: scene={g.scene_id}, user={g.user_id}, error={e}"
                            )
        except Exception as e:
            logger.error(f"L3 worker 循环异常: {e}")

        await asyncio.sleep(L3_POLL_INTERVAL)
