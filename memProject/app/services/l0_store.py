# -*- coding: utf-8 -*-
"""
L0 落库 —— write 降级路径与 mq_consumer 共用的幂等落库模块。

设计（对应《多智能体改造方案》块 A 升级：Kafka）：
- write 侧预生成 record_id（每条 L0 一个），随消息传递。
- consumer 与 write 降级路径都用同一批 record_id 落库，靠 record_id 唯一约束 + ON CONFLICT DO NOTHING 保证幂等。
- 抽取不走 Kafka，由 L1 worker 游标轮询消费 pending_extract 的 L0。
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.base import InteractionRecord

logger = get_logger("l0_store")


def gen_record_id() -> str:
    """生成单条 L0 记录 ID（预生成，保证 write 投递与降级落库幂等）。"""
    return f"rec_{uuid.uuid4().hex[:24]}"


def gen_record_ids(count: int) -> list[str]:
    return [gen_record_id() for _ in range(max(0, count))]


def count_l0_records(body: dict) -> int:
    """计算 body 将拆出的 L0 记录条数（用于预生成 record_id 数量）。"""
    itype = body.get("interaction_type", "dialogue")
    messages = body.get("messages") or []
    n = len(messages)

    if itype == "session" and body.get("session_summary"):
        n += 1
    elif itype == "task_process":
        n += sum(
            1 for key in ("task_goal", "task_progress", "task_result") if body.get(key)
        )
    return n


def build_l0_records(
    body: dict,
    *,
    user_id: str,
    agent_id: str | None,
    scene_id: str | None,
    session_id: str,
    task_id: str | None,
    record_ids: list[str],
) -> list[dict]:
    """把 write body 拆成 L0 记录字典列表（record_id 由调用方预生成，保证幂等）。

    body 为 MemoryWriteRequest.model_dump() 的字典，或 mq_consumer 收到的消息体。
    record_ids 数量须 >= count_l0_records(body)，不足时兜底生成（理论上不发生）。
    """
    itype = body.get("interaction_type", "dialogue")
    messages = body.get("messages") or []
    metadata = body.get("metadata") or {}

    base = {
        "user_id": user_id,
        "agent_id": agent_id,
        "scene_id": scene_id,
        "session_id": session_id,
        "task_id": task_id,
        "interaction_type": itype,
        "content_type": "text",
        "processed": False,
        "status": "pending_extract",
        "recorded_at": datetime.now(timezone.utc),
        "extra_meta": metadata,
    }

    rid_iter = iter(record_ids)

    def _next_rid() -> str:
        try:
            return next(rid_iter)
        except StopIteration:
            logger.warning("record_ids 数量不足，兜底生成新 record_id（幂等性可能受影响）")
            return gen_record_id()

    records: list[dict] = []

    if itype == "dialogue":
        for i, msg in enumerate(messages):
            records.append({
                **base,
                "record_id": _next_rid(),
                "turn_index": i,
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

    elif itype == "session":
        extra = dict(metadata)
        if body.get("session_time"):
            extra["session_time"] = body["session_time"]
        if body.get("session_source"):
            extra["session_source"] = body["session_source"]
        base["extra_meta"] = extra

        for i, msg in enumerate(messages):
            records.append({
                **base,
                "record_id": _next_rid(),
                "turn_index": i,
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })
        if body.get("session_summary"):
            records.append({
                **base,
                "record_id": _next_rid(),
                "turn_index": len(messages),
                "role": "session_summary",
                "content": body["session_summary"],
                "content_type": "session_summary",
            })

    elif itype == "task_process":
        for i, msg in enumerate(messages):
            records.append({
                **base,
                "record_id": _next_rid(),
                "turn_index": i,
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        turn_offset = len(messages)
        for j, role_name in enumerate(("task_goal", "task_progress", "task_result")):
            content = body.get(role_name)
            if content:
                records.append({
                    **base,
                    "record_id": _next_rid(),
                    "turn_index": turn_offset + j,
                    "role": role_name,
                    "content": content,
                    "content_type": "task_process",
                })

    return records


async def persist_l0(db: AsyncSession, records: list[dict]) -> int:
    """幂等落 L0：record_id 冲突跳过（ON CONFLICT DO NOTHING）。返回实际落库条数。"""
    if not records:
        return 0

    stmt = pg_insert(InteractionRecord).values(records).on_conflict_do_nothing(
        index_elements=[InteractionRecord.record_id]
    )
    result = await db.execute(stmt)
    return result.rowcount or 0
