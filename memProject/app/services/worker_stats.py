# -*- coding: utf-8 -*-
"""
worker 可观测统计 — 积压数 + 失败率 + 产出速率（P1-监控）。

- 成功/失败计数：worker 内累加（进程内，单机单进程，重启归零——只反映当前进程运行期）。
- 积压（backlog）、产出速率（rate_per_min）：从 DB 实时查。
"""
from datetime import datetime, timezone

from sqlalchemy import func, select, text

from app.core.database import async_session_factory
from app.models.base import InteractionRecord, Memory, Persona, SceneBlock

_started_at = datetime.now(timezone.utc)

_counters = {
    "l1_success": 0, "l1_failed": 0,
    "l2_success": 0, "l2_failed": 0,
    "l3_success": 0, "l3_failed": 0,
}


def record(layer: str, ok: bool) -> None:
    """worker 内调用：累加某层成功/失败计数。"""
    key = f"{layer}_{'success' if ok else 'failed'}"
    _counters[key] += 1


def _failure_rate(success: int, failed: int) -> float:
    total = success + failed
    return round(failed / total, 4) if total else 0.0


async def _count_l1_backlog(db) -> int:
    """L1 积压：待抽取的 L0（status=pending_extract）。"""
    return (await db.execute(
        select(func.count()).select_from(InteractionRecord)
        .where(InteractionRecord.status == "pending_extract")
    )).scalar() or 0


async def _count_l2_backlog(db) -> int:
    """L2 积压：active L1 且 seq_id > 该组 l2 游标（未聚合的新记忆）。"""
    return (await db.execute(text("""
        SELECT count(*) FROM t_memory m
        WHERE m.status = 'active' AND m.scene_id IS NOT NULL
          AND m.seq_id > COALESCE(
            (SELECT c.last_processed_id FROM t_memory_cursor c
             WHERE c.cursor_key = 'l2:' || m.scene_id || ':' || m.user_id), 0)
    """))).scalar() or 0


async def _count_l3_backlog(db) -> int:
    """L3 积压：active L1 且 seq_id > 该组 persona.last_seq_id（未入画像的新记忆）。"""
    return (await db.execute(text("""
        SELECT count(*) FROM t_memory m
        WHERE m.status = 'active' AND m.scene_id IS NOT NULL
          AND m.seq_id > COALESCE(
            (SELECT p.last_seq_id FROM t_persona p
             WHERE p.user_id = m.user_id AND p.scene_id = m.scene_id), 0)
    """))).scalar() or 0


async def _rate_per_min(db, model, col) -> int:
    """最近 60 秒该表产出/更新条数。"""
    return (await db.execute(
        select(func.count()).select_from(model)
        .where(col >= text("now() - interval '1 minute'"))
    )).scalar() or 0


async def snapshot() -> dict:
    """汇总各层指标，返回可观测快照。"""
    async with async_session_factory() as db:
        l1_backlog = await _count_l1_backlog(db)
        l2_backlog = await _count_l2_backlog(db)
        l3_backlog = await _count_l3_backlog(db)
        l1_rate = await _rate_per_min(db, Memory, Memory.created_at)
        l2_rate = await _rate_per_min(db, SceneBlock, SceneBlock.updated_at)
        l3_rate = await _rate_per_min(db, Persona, Persona.updated_at)

    c = _counters
    uptime = int((datetime.now(timezone.utc) - _started_at).total_seconds())
    return {
        "uptime_seconds": uptime,
        "layers": {
            "l1": {
                "success": c["l1_success"], "failed": c["l1_failed"],
                "failure_rate": _failure_rate(c["l1_success"], c["l1_failed"]),
                "backlog": l1_backlog, "rate_per_min": l1_rate,
            },
            "l2": {
                "success": c["l2_success"], "failed": c["l2_failed"],
                "failure_rate": _failure_rate(c["l2_success"], c["l2_failed"]),
                "backlog": l2_backlog, "rate_per_min": l2_rate,
            },
            "l3": {
                "success": c["l3_success"], "failed": c["l3_failed"],
                "failure_rate": _failure_rate(c["l3_success"], c["l3_failed"]),
                "backlog": l3_backlog, "rate_per_min": l3_rate,
            },
        },
    }
