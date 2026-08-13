# -*- coding: utf-8 -*-
"""
记忆 Service 层 — 封装 t_memory / t_interaction_record / t_retrieval_* 的 CRUD 业务逻辑。
所有函数接受 db: AsyncSession 作为第一参数。
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, MemoryWriteError
from app.core.logger import get_logger
from app.models.base import (
    Memory,
    InteractionRecord,
    RetrievalRequest,
    RetrievalResult,
    MemoryRelation,
    User,
    Agent,
    Session,
)

logger = get_logger("memory_service")


# ============================================================
# ID 生成
# ============================================================

def _now() -> datetime:
    return datetime.now(timezone.utc)


def gen_memory_id() -> str:
    return "mem_" + uuid.uuid4().hex[:28]


def gen_record_id() -> str:
    return "rec_" + uuid.uuid4().hex[:28]


def gen_request_id() -> str:
    return "req_" + uuid.uuid4().hex[:28]


# ============================================================
# 核心 CRUD
# ============================================================

async def get_memory_by_id(db: AsyncSession, memory_id: str) -> Optional[Memory]:
    result = await db.execute(
        select(Memory).where(Memory.memory_id == memory_id)
    )
    return result.scalar_one_or_none()


def snapshot_memory_history(db: AsyncSession, memory: Memory, action: str = "update") -> None:
    """将记忆当前内容快照到 t_memory_history（原地更新前调用）。"""
    from app.models.base import MemoryHistory
    db.add(MemoryHistory(
        memory_id=memory.memory_id,
        version=memory.version or 1,
        content=memory.content or "",
        summary=memory.summary,
        key_points=memory.key_points or [],
        tags=memory.tags or [],
        entities=memory.entities or [],
        importance=float(memory.importance or 0.5),
        confidence=float(memory.confidence or 0.5),
        action=action,
    ))


async def create_memory(db: AsyncSession, data: dict) -> Memory:
    """记忆创建 — 纯插入。去重已由 pipeline 的单层去重（process_candidates）完成。"""
    memory_type = data.get("memory_type", "fact")
    # 统一 task/task_state 为一个路由
    if memory_type == "task":
        memory_type = "task_state"
        data["memory_type"] = "task_state"
    return await _insert_memory(db, data)


# 任务关键词 — 四分类
_TASK_GOAL_KEYWORDS = {"目标", "目的", "诉求", "要做", "goal", "objective"}
_TASK_PENDING_KEYWORDS = {"待办", "需要", "下一步", "计划", "尚未", "还需", "将", "准备"}
_TASK_CONCLUSION_KEYWORDS = {"完成", "通过", "上线", "稳定", "结束", "验收", "交付", "已实现", "成功"}


def _classify_task(content: str, key_points: list) -> str:
    """返回 goal / pending / conclusion / progress"""
    text = content + " " + " ".join(key_points or [])
    if any(kw in text for kw in _TASK_GOAL_KEYWORDS):
        return "goal"
    if any(kw in text for kw in _TASK_PENDING_KEYWORDS):
        return "pending"
    if any(kw in text for kw in _TASK_CONCLUSION_KEYWORDS):
        return "conclusion"
    return "progress"


async def _insert_memory(db: AsyncSession, data: dict) -> Memory:
    """纯插入，不做任何类型逻辑。"""
    memory = Memory(
        id=uuid.uuid4().hex,
        memory_id=data.get("memory_id", gen_memory_id()),
        user_id=data.get("user_id"),
        agent_id=data.get("agent_id"),
        scene_id=data.get("scene_id"),
        session_id=data.get("session_id"),
        task_id=data.get("task_id"),
        content=data.get("content", ""),
        summary=data.get("summary"),
        key_points=data.get("key_points", []),
        memory_type=data.get("memory_type", "fact"),
        tags=data.get("tags", []),
        entities=data.get("entities", []),
        status=data.get("status", "active"),
        version=data.get("version", 1),
        importance=data.get("importance", 0.5),
        confidence=data.get("confidence", 0.5),
        source_type=data.get("source_type", "extracted"),
        source_record_ids=data.get("source_record_ids", []),
        memory_scope=data.get("memory_scope") or _infer_scope(data),
        vector_id=data.get("vector_id"),
        created_at=data.get("created_at", _now()),
        updated_at=data.get("updated_at", _now()),
    )
    db.add(memory)
    await db.flush()
    return memory


async def update_memory_fields(db: AsyncSession, memory_id: str, updates: dict) -> Memory:
    memory = await get_memory_by_id(db, memory_id)
    if not memory:
        raise NotFoundError(f"记忆 {memory_id} 不存在")

    allowed_fields = {"content", "summary", "status", "importance", "confidence", "tags"}
    for field in allowed_fields:
        if field in updates and updates[field] is not None:
            setattr(memory, field, updates[field])

    memory.version += 1
    memory.updated_at = _now()
    await db.flush()
    return memory


async def soft_delete_memory(db: AsyncSession, memory_id: str) -> tuple[str, str]:
    memory = await get_memory_by_id(db, memory_id)
    if not memory:
        raise NotFoundError(f"记忆 {memory_id} 不存在")

    previous_status = memory.status
    memory.status = "deleted"
    memory.deleted_at = _now()
    memory.updated_at = _now()
    await db.flush()
    return memory_id, previous_status


# ============================================================
# 批量写入辅助
# ============================================================

async def save_interaction_records(
    db: AsyncSession,
    messages: list,
    metadata: dict,
) -> list[InteractionRecord]:
    records = []
    for i, msg in enumerate(messages):
        rec = InteractionRecord(
            record_id=gen_record_id(),
            user_id=metadata.get("user_id", ""),
            agent_id=metadata.get("agent_id"),
            scene_id=metadata.get("scene_id"),
            session_id=metadata.get("session_id"),
            task_id=metadata.get("task_id"),
            turn_index=msg.get("turn_index", i),
            role=msg.get("role", "user"),
            content=msg.get("content", ""),
            content_type=msg.get("content_type", "text"),
            processed=False,
            recorded_at=_now(),
            extra_meta=metadata.get("extra_meta", {}),
        )
        db.add(rec)
        records.append(rec)
    await db.flush()
    return records


# ============================================================
# 查询构建
# ============================================================

def _apply_memory_filters(stmt, filters: dict):
    """在 select(Memory) 上叠加 where 条件，返回修改后的 stmt。"""
    if filters.get("user_id"):
        stmt = stmt.where(Memory.user_id == filters["user_id"])

    for attr in ("agent_id", "scene_id", "session_id", "task_id"):
        if filters.get(attr) is not None:
            stmt = stmt.where(getattr(Memory, attr) == filters[attr])

    if filters.get("memory_types"):
        stmt = stmt.where(Memory.memory_type.in_(filters["memory_types"]))

    include_inactive = filters.get("include_inactive", False)
    specified_status = filters.get("status")
    if specified_status:
        stmt = stmt.where(Memory.status == specified_status)
    elif not include_inactive:
        stmt = stmt.where(Memory.status != "deleted")

    if filters.get("time_start"):
        stmt = stmt.where(Memory.created_at >= filters["time_start"])
    if filters.get("time_end"):
        stmt = stmt.where(Memory.created_at <= filters["time_end"])

    return stmt


async def search_local(db: AsyncSession, filters: dict) -> list[Memory]:
    stmt = select(Memory)
    stmt = _apply_memory_filters(stmt, filters)
    stmt = stmt.order_by(Memory.importance.desc(), Memory.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_memories_filtered(
    db: AsyncSession, filters: dict, page: int, page_size: int
) -> tuple[list[Memory], int]:
    base_stmt = select(Memory)
    base_stmt = _apply_memory_filters(base_stmt, filters)

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    query_stmt = base_stmt.order_by(Memory.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await db.execute(query_stmt)
    items = list(result.scalars().all())

    return items, total


async def build_context_query(db: AsyncSession, filters: dict) -> list[Memory]:
    stmt = select(Memory)
    stmt = stmt.where(Memory.status != "deleted")

    if filters.get("user_id"):
        stmt = stmt.where(Memory.user_id == filters["user_id"])
    for attr in ("agent_id", "scene_id", "session_id", "task_id"):
        if filters.get(attr) is not None:
            stmt = stmt.where(getattr(Memory, attr) == filters[attr])

    include_map = filters.get("include_map", {})
    if include_map:
        type_conditions = []
        if include_map.get("preferences"):
            type_conditions.append(Memory.memory_type == "preference")
        if include_map.get("facts"):
            type_conditions.append(Memory.memory_type.in_(
                ["fact", "decision", "constraint", "process", "correction"]
            ))
        if include_map.get("task_state"):
            type_conditions.append(Memory.memory_type == "task_state")
        if type_conditions:
            from sqlalchemy import or_
            stmt = stmt.where(or_(*type_conditions))

    stmt = stmt.order_by(Memory.importance.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ============================================================
# 多层记忆聚合 — 用户/会话/任务三层结构化视图
# ============================================================


async def get_user_profile(db: AsyncSession, user_id: str) -> dict:
    """用户画像：聚合用户跨会话的偏好和事实，供 LLM 注入 prompt。"""
    all_memories = await search_local(db, {"user_id": user_id, "status": "active"})

    profile = {
        "user_id": user_id,
        "preferences": [],
        "facts": [],
    }
    for m in all_memories:
        if m.memory_type == "preference":
            profile["preferences"].append(m.content)
        elif m.memory_type == "fact":
            profile["facts"].append(m.content)
    return profile


async def get_session_context(db: AsyncSession, session_id: str) -> dict:
    """会话上下文：会话内所有记忆按类型分组 + 关键内容。"""
    all_memories = await search_local(db, {"session_id": session_id, "status": "active"})

    ctx: dict = {"session_id": session_id, "by_type": {}, "key_items": []}
    for m in all_memories:
        ctx["by_type"].setdefault(m.memory_type, []).append({
            "memory_id": m.memory_id, "content": m.content, "importance": m.importance,
        })
        if m.importance >= 0.7:
            ctx["key_items"].append({
                "memory_id": m.memory_id, "content": m.content, "memory_type": m.memory_type,
            })
    return ctx


async def get_task_view(db: AsyncSession, task_id: str) -> dict:
    """任务视图：当前目标 + 进展时间线。"""
    all_memories = await search_local(db, {
        "task_id": task_id, "status": "active",
    })
    all_memories.sort(key=lambda m: m.created_at or datetime.min)

    view: dict = {
        "task_id": task_id,
        "current_goal": None,
        "timeline": [],
        "constraints": [],
        "processes": [],
        "decisions": [],
        "facts": [],
    }
    for m in all_memories:
        entry = {
            "memory_id": m.memory_id,
            "content": m.content,
            "memory_type": m.memory_type,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        if m.memory_type == "task_state":
            sub_type = _classify_task(m.content or "", m.key_points or [])
            entry["sub_type"] = sub_type
            if sub_type == "goal":
                view["current_goal"] = {"memory_id": m.memory_id, "content": m.content}
            view["timeline"].append(entry)
        elif m.memory_type == "constraint":
            view["constraints"].append(entry)
        elif m.memory_type == "process":
            view["processes"].append(entry)
        elif m.memory_type == "decision":
            view["decisions"].append(entry)
        else:
            view["facts"].append(entry)

    return view


# ============================================================
# 检索日志
# ============================================================

async def log_retrieval_request(db: AsyncSession, data: dict) -> RetrievalRequest:
    req = RetrievalRequest(
        request_id=data.get("request_id", gen_request_id()),
        agent_id=data.get("agent_id"),
        user_id=data.get("user_id", ""),
        scene_id=data.get("scene_id"),
        session_id=data.get("session_id"),
        task_id=data.get("task_id"),
        query_text=data.get("query_text", ""),
        filter_conditions=data.get("filter_conditions", {}),
        top_k=data.get("top_k", 10),
        is_triggered=data.get("is_triggered", False),
        created_at=_now(),
    )
    db.add(req)
    await db.flush()
    return req


async def log_retrieval_results(
    db: AsyncSession, request_id: str, results: list[dict]
) -> None:
    for i, r in enumerate(results):
        entry = RetrievalResult(
            request_id=request_id,
            memory_id=r.get("memory_id", ""),
            rank=i + 1,
            relevance_score=r.get("relevance_score", 0.0),
            semantic_score=r.get("semantic_score"),
            keyword_score=r.get("keyword_score"),
            recency_score=r.get("recency_score"),
            created_at=_now(),
        )
        db.add(entry)
    await db.flush()


# ============================================================
# 统计 / 关系
# ============================================================

async def get_stats(db: AsyncSession) -> dict:
    total_memories = (
        await db.execute(
            select(func.count()).select_from(Memory).where(Memory.status != "deleted")
        )
    ).scalar() or 0

    total_users = (
        await db.execute(select(func.count()).select_from(User))
    ).scalar() or 0

    total_agents = (
        await db.execute(
            select(func.count()).select_from(Agent).where(Agent.is_active == True)
        )
    ).scalar() or 0

    total_sessions = (
        await db.execute(
            select(func.count()).select_from(Session).where(Session.status == "active")
        )
    ).scalar() or 0

    return {
        "total_memories": total_memories,
        "total_users": total_users,
        "total_agents": total_agents,
        "total_sessions": total_sessions,
    }


def _infer_scope(data: dict) -> str:
    """根据已有字段推断 memory_scope。"""
    scope = data.get("memory_scope", "")
    if scope in ("user", "session", "task", "agent"):
        return scope
    if data.get("task_id"):
        return "task"
    if data.get("session_id"):
        return "session"
    return "user"


_stats_cache: dict[str, tuple[float, dict]] = {}  # key → (timestamp, result)
_STATS_CACHE_TTL = 10  # 秒


async def get_memory_stats(db: AsyncSession, user_id: str, scene_id: str | None = None) -> dict:
    """层级统计：按 memory_scope 列 + user/session/task/agent 四级聚合（10秒缓存）。"""
    import time as _time

    cache_key = f"stats:{user_id}:{scene_id or ''}"
    if cache_key in _stats_cache:
        ts, cached = _stats_cache[cache_key]
        if _time.time() - ts < _STATS_CACHE_TTL:
            return cached

    query = (
        select(
            func.coalesce(Memory.memory_scope, "user").label("scope"),
            func.count().label("count"),
        )
        .where(Memory.user_id == user_id, Memory.status == "active")
    )
    if scene_id:
        query = query.where(Memory.scene_id == scene_id)
    query = query.group_by("scope")

    result = await db.execute(query)
    rows = {row[0]: row[1] for row in result.fetchall()}

    levels = ["user", "session", "task", "agent"]
    counts = {lv: rows.get(lv, 0) for lv in levels}
    total = sum(counts.values())

    data = {
        "total": total,
        "level_distribution": [
            {"level": lv, "count": counts[lv],
             "ratio": round(counts[lv] / total, 4) if total > 0 else 0.0}
            for lv in levels
        ],
    }

    _stats_cache[cache_key] = (_time.time(), data)
    return data


async def get_memory_relations(db: AsyncSession, memory_id: str) -> list[dict]:
    result = await db.execute(
        select(MemoryRelation).where(
            (MemoryRelation.source_memory_id == memory_id)
            | (MemoryRelation.target_memory_id == memory_id)
        )
    )
    relations = result.scalars().all()
    return [
        {
            "source_memory_id": r.source_memory_id,
            "target_memory_id": r.target_memory_id,
            "relation_type": r.relation_type,
            "description": r.description,
            "confidence": r.confidence,
        }
        for r in relations
    ]
