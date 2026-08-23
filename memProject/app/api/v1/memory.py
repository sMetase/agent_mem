# -*- coding: utf-8 -*-
"""
记忆核心 API — 对齐前端对接文档。

端点:
  POST /write       — 同步写入记忆
  POST /search      — 语义检索记忆（Qdrant + PostgreSQL）
  POST /list        — 分页列出记忆
  POST /delete-all  — 清除全部记忆
  POST /context     — 检索并格式化为 Prompt 上下文
  PUT  /update      — 更新单条记忆
  DELETE /delete    — 软删除单条记忆

支持三种数据类型（通过 interaction_type 区分）：
  - dialogue:     当前对话记录，messages 逐条落库
  - session:      历史会话数据，含会话时间/来源/摘要
  - task_process: 任务过程数据，含目标/进展/执行结果
"""

import asyncio
import time as time_module
from typing import Optional
from uuid import uuid4

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    DEFAULT_DEV_SCENE_ID,
    authorize_user_access,
    get_current_agent,
    get_current_user_id,
    get_current_scene_id,
    get_current_session_id,
    get_current_task_id,
)
from app.core.config import get_settings
from app.core.database import async_session_factory, get_db
from app.models.base import RetrievalRequest, RetrievalResult
from app.core.exceptions import ValidationError
from app.core.logger import get_logger
from app.schemas.common import error, ok
from app.schemas.memory import (
    ContextRequest,
    MemoryDeleteRequest,
    MemoryDeleteResponse,
    MemorySearchRequest,
    MemoryUpdateRequest,
    MemoryUpdateResponse,
    MemoryWriteRequest,
)
from app.services.mem0_client import mem0_client
from app.services.l0_store import (
    gen_record_ids,
    count_l0_records,
    build_l0_records,
    persist_l0,
    ensure_session_title,
)
from app.services.memory_store import memory_store
from app.services.validation_service import (
    validate_id_format,
    normalize_id,
    validate_write_request_by_type,
)

logger = get_logger("memory_api")
router = APIRouter()


# ============================================================
# Fire-and-Forget 检索日志（写 t_retrieval_request + t_retrieval_result）
# ============================================================

async def _log_retrieval(
    request_id: str,
    agent_id: Optional[str],
    user_id: str,
    scene_id: Optional[str],
    session_id: Optional[str],
    task_id: Optional[str],
    query_text: str,
    filter_conditions: dict,
    top_k: int,
    results: list[dict],
    elapsed_ms: int,
    retrieval_mode: str = "hybrid",
):
    """异步写检索日志，失败不阻塞主流程。"""
    try:
        async with async_session_factory() as log_db:
            log_db.add(RetrievalRequest(
                request_id=request_id,
                agent_id=agent_id,
                user_id=user_id,
                scene_id=scene_id,
                session_id=session_id,
                task_id=task_id,
                query_text=query_text,
                filter_conditions=filter_conditions,
                top_k=top_k,
                retrieval_mode=retrieval_mode,
            ))
            await log_db.flush()

            for rank, mem in enumerate(results):
                log_db.add(RetrievalResult(
                    request_id=request_id,
                    memory_id=mem.get("memory_id", ""),
                    rank=rank,
                    relevance_score=mem.get("relevance_score"),
                ))

            await log_db.commit()
    except Exception as e:
        logger.warning(f"Retrieval log write failed (non-fatal): {e}")


# Mock 提取器（从共享模块导入，供 memory.py 和 mq_consumer.py 共用）



# ============================================================
# 同步写入 — 对齐前端对接文档 一.1 节
# ============================================================

@router.post("/write", summary="写入记忆（同步）", status_code=200)
async def memory_write(
    request: Request,
    body: MemoryWriteRequest,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
    user_id_header: str = Depends(get_current_user_id),
    scene_id: str | None = Depends(get_current_scene_id),
    session_id_header: str | None = Depends(get_current_session_id),
    task_id_header: str | None = Depends(get_current_task_id),
):
    """
    同步写入记忆数据，支持三种数据类型：

    - dialogue (对话记录): messages 数组逐条落库，每轮标记 turn_index
    - session (历史会话): 导入历史会话内容、时间、来源信息
    - task_process (任务过程): 写入任务目标、进展、执行结果

    延迟: 毫秒级（异步投递 Kafka，L1 抽取由后台 worker 异步做）。
    """
    start = time_module.perf_counter()
    itype = body.interaction_type
    settings = get_settings()

    # 合并 ID 来源（Header > Body，开发模式自动补默认值）
    effective_user_id = normalize_id(user_id_header or body.user_id)
    effective_scene_id = scene_id or body.scene_id or DEFAULT_DEV_SCENE_ID
    effective_session_id = session_id_header or body.session_id
    effective_task_id = task_id_header or body.task_id

    # 业务级校验（ID 格式 + 类型感知校验）
    if effective_user_id:
        err = validate_id_format("user_id", effective_user_id)
        if err:
            raise ValidationError(message=err)

    # 类型感知校验：确保每种 interaction_type 有足够的输入数据
    type_validation = validate_write_request_by_type(
        interaction_type=itype,
        messages=body.messages,
        session_summary=body.session_summary,
        session_time=body.session_time,
        task_goal=body.task_goal,
        task_progress=body.task_progress,
        task_result=body.task_result,
    )
    type_validation.raise_if_invalid()

    # --- 预生成 record_id（幂等键），投递 Kafka（带全量 + record_ids）---
    body_dict = body.model_dump()
    body_dict["user_id"] = effective_user_id
    body_dict["agent_id"] = agent_id
    body_dict["scene_id"] = effective_scene_id
    body_dict["session_id"] = effective_session_id
    body_dict["task_id"] = effective_task_id
    record_ids = gen_record_ids(count_l0_records(body_dict))
    body_dict["record_ids"] = record_ids

    from app.services.mq_producer import mq_producer
    request_id = f"req_{uuid4().hex[:16]}"
    published = await mq_producer.publish_memory_write(
        request_id=request_id,
        user_id=effective_user_id,
        agent_id=agent_id,
        body_dict=body_dict,
    )

    if published:
        elapsed = round((time_module.perf_counter() - start) * 1000, 2)
        logger.info(
            f"[Write] Kafka 投递成功: type={itype}, user_id={effective_user_id}, "
            f"session_id={effective_session_id}, l0_count={len(record_ids)}, elapsed={elapsed}ms"
        )
        return ok({
            "accepted": True,
            "session_id": effective_session_id,
            "l0_count": len(record_ids),
            "record_ids": record_ids,
        })

    # 降级：Kafka 不可用 → 同步落 L0（pending_extract，供 L1 worker 轮询兜底）
    records = build_l0_records(
        body_dict,
        user_id=effective_user_id,
        agent_id=agent_id,
        scene_id=effective_scene_id,
        session_id=effective_session_id,
        task_id=effective_task_id,
        record_ids=record_ids,
    )
    await persist_l0(db, records)
    # 首次落 L0 时生成会话 title（title 为空才设置）
    await ensure_session_title(db, effective_session_id, body.messages)
    await db.commit()

    elapsed = round((time_module.perf_counter() - start) * 1000, 2)
    logger.warning(
        f"[Write] Kafka 不可用，降级同步落 L0: type={itype}, user_id={effective_user_id}, "
        f"session_id={effective_session_id}, l0_count={len(record_ids)}, elapsed={elapsed}ms"
    )
    return ok({
        "accepted": True,
        "session_id": effective_session_id,
        "l0_count": len(record_ids),
        "record_ids": record_ids,
        "degraded": True,
    })


# ============================================================
# 检索 — 对齐前端对接文档 一.2 节
# ============================================================

@router.post("/search", summary="检索记忆")
async def memory_search(
    body: MemorySearchRequest,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
):
    """
    语义检索历史记忆 — mem0 三路混合检索（语义 + BM25 + 实体）+ Qdrant 层全字段过滤（已启用 v2）。

    mem0 在 Qdrant 层完成所有过滤（user_id / scene_id / task_id / session_id /
    memory_type / status / created_at 时间范围），无需 PG 后过滤。

    当 mem0 不可用时，降级为 memory_store 路径。
    """
    t0 = time_module.perf_counter()

    # ── 构建 mem0 filters ──
    filters: dict = {}

    if body.scene_id:
        filters["scene_id"] = body.scene_id
    if body.task_id:
        filters["task_id"] = body.task_id
    if body.session_id:
        filters["session_id"] = body.session_id
    if body.memory_types:
        filters["memory_type"] = {"in": body.memory_types}
    if body.status:
        filters["status"] = {"in": body.status}

    # 时间范围过滤
    time_filter: dict = {}
    if body.time_start:
        time_filter["gte"] = body.time_start.isoformat() if hasattr(body.time_start, "isoformat") else str(body.time_start)
    if body.time_end:
        time_filter["lte"] = body.time_end.isoformat() if hasattr(body.time_end, "isoformat") else str(body.time_end)
    if time_filter:
        filters["created_at"] = time_filter

    try:
        # ── 主路径: 向量检索（vector_store 抽象，无桥接表）→ T_MEMORY ──
        from app.services.vector_store import vector_store
        from app.services.embedding_client import embedding_client as _emb
        from app.models.base import Memory
        import math as _math

        # Step 1: 向量化 query
        query_vector = await _emb.embed_single(body.query)

        # Step 2: 向量检索 + payload 预过滤
        payload_filters = {}
        if body.scene_id:
            payload_filters["scene_id"] = body.scene_id
        if body.task_id:
            payload_filters["task_id"] = body.task_id
        if body.session_id:
            payload_filters["session_id"] = body.session_id
        if body.agent_id:
            payload_filters["agent_id"] = body.agent_id

        hits = await vector_store.hybrid_search(
            query_vector=query_vector,
            query_text=body.query,
            user_id=body.user_id,
            top_k=max(body.top_k * 3, 30),
            filters=payload_filters if payload_filters else None,
        )

        if not hits:
            return ok({"query": body.query, "results": [], "total_candidates": 0, "elapsed_ms": 0})

        # memory_id → qdrant_score（vector_store 已返回 memory_id，无需桥接表）
        id_map = {h["memory_id"]: h["score"] for h in hits}

        # Step 3: T_MEMORY 取权威数据 + 后过滤
        from sqlalchemy import select as _sel
        mem_query = _sel(Memory).where(Memory.memory_id.in_(list(id_map.keys())))
        if body.memory_types:
            mem_query = mem_query.where(Memory.memory_type.in_(body.memory_types))
        if body.agent_id:
            mem_query = mem_query.where(Memory.agent_id == body.agent_id)
        if body.status:
            mem_query = mem_query.where(Memory.status.in_(body.status))
        else:
            mem_query = mem_query.where(Memory.status == "active")
        # 状态类记忆（process/correction）是 agent 私有，额外按 agent_id 过滤；普通记忆跨 agent 共享
        mem_query = mem_query.where(
            Memory.memory_type.notin_(["process", "correction"]) | (Memory.agent_id == agent_id)
        )

        mem_result = await db.execute(mem_query)
        db_memories = {m.memory_id: m for m in mem_result.scalars().all()}

        now_dt = datetime.now(timezone.utc)
        HALF_LIFE_DAYS = 30

        results = []
        for memory_id, mem_score in id_map.items():
            mem = db_memories.get(memory_id)
            if not mem:
                continue

            content = mem.content or ""
            if body.max_content_length and len(content) > body.max_content_length:
                content = content[:body.max_content_length]

            # 时间新近性
            recency = 0.5
            if mem.created_at:
                try:
                    created_dt = mem.created_at.replace(tzinfo=None) if mem.created_at.tzinfo else mem.created_at
                    age_seconds = max(0, (now_dt.replace(tzinfo=None) - created_dt).total_seconds())
                    age_days = age_seconds / 86400
                    recency = _math.pow(0.5, age_days / HALF_LIFE_DAYS)
                except Exception:
                    pass

            final_score = round(
                (mem_score or 0) * 0.6
                + recency * 0.15
                + (mem.importance or 0.5) * 0.15
                + (mem.confidence or 0.5) * 0.1, 4
            )

            results.append({
                "memory_id": mem.memory_id,
                "content": content,
                "summary": mem.summary or content[:200],
                "memory_type": mem.memory_type or "",
                "scene_id": mem.scene_id or "",
                "task_id": mem.task_id or "",
                "session_id": mem.session_id or "",
                "status": mem.status or "active",
                "importance": mem.importance or 0.5,
                "confidence": mem.confidence or 0.5,
                "relevance_score": final_score,
                "created_at": mem.created_at.isoformat() if mem.created_at else "",
                "updated_at": mem.updated_at.isoformat() if mem.updated_at else "",
            })

        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        results = results[:body.top_k]

        elapsed_ms = round((time_module.perf_counter() - t0) * 1000)
        total_candidates = len(hits)
        result = {
            "query": body.query,
            "results": results,
            "total_candidates": total_candidates,
            "elapsed_ms": elapsed_ms,
        }

        logger.info(
            f"Search(mem0): user={body.user_id}, query='{body.query[:50]}...', "
            f"found={len(results)}, elapsed={elapsed_ms}ms"
        )

        # Fire-and-forget 检索日志
        req_id = str(uuid4())
        asyncio.create_task(_log_retrieval(
            request_id=req_id,
            agent_id=agent_id,
            user_id=body.user_id,
            scene_id=body.scene_id,
            session_id=body.session_id,
            task_id=body.task_id,
            query_text=body.query,
            filter_conditions={
                "memory_types": body.memory_types,
                "status": body.status,
                "filters": filters,
            },
            top_k=body.top_k,
            results=results,
            elapsed_ms=elapsed_ms,
            retrieval_mode="hybrid",
        ))

        return ok(result)

    except Exception as e:
        import traceback as _tb
        logger.error(f"mem0 search FAILED: {type(e).__name__}: {e}\n{_tb.format_exc()}")
        try:
            # ── 降级: memory_store (PG 后过滤) ──
            result = await memory_store.search(
                query=body.query,
                user_id=body.user_id,
                db=db,
                agent_id=agent_id,
                scene_id=body.scene_id,
                task_id=body.task_id,
                session_id=body.session_id,
                memory_types=body.memory_types,
                status=body.status,
                max_content_length=body.max_content_length,
                time_start=body.time_start,
                time_end=body.time_end,
                top_k=body.top_k,
                rerank=body.rerank,
            )
            return ok(result)
        except Exception as e2:
            logger.error(f"Search failed (both paths): {e2}")
            return error(
                message="检索服务暂时不可用",
                code=-1,
                data={
                    "query": body.query,
                    "results": [],
                    "total_candidates": 0,
                    "elapsed_ms": 0,
                },
                error_code="SEARCH_FAILED",
            )


# ============================================================
# 上下文 — 对齐前端对接文档 二.1 节
# ============================================================

# Context assembly helpers
GROUP_TITLES = {
    "preference": "## User Preferences",
    "fact": "## Key Facts",
    "task_state": "## Task State",
    "process": "## Process Experience",
}
TYPE_PRIORITY = {"preference": 1, "fact": 2, "task_state": 3, "process": 4}
CONTENT_MAX_LEN = 200
SCORE_MIN_THRESHOLD = 0.5
MAX_MEMORY_COUNT = 10


@router.post("/context", summary="Prompt context fragment")
async def memory_context(
    body: ContextRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
):
    """Prompt context: search -> group by type -> assemble within capacity budget."""
    try:
        from app.services.vector_store import vector_store
        from app.services.embedding_client import embedding_client as _emb
        from app.models.base import Memory
        from sqlalchemy import select as _sel
        import math as _math

        # Step 1: Search
        query_vector = await _emb.embed_single(body.query)
        payload_filters = {}
        if body.scene_id:
            payload_filters["scene_id"] = body.scene_id
        if body.task_id:
            payload_filters["task_id"] = body.task_id
        if body.session_id:
            payload_filters["session_id"] = body.session_id

        top_k = body.top_k or 10
        hits = await vector_store.hybrid_search(
            query_vector=query_vector,
            query_text=body.query,
            user_id=body.user_id,
            top_k=max(top_k * 3, 30),
            filters=payload_filters if payload_filters else None,
        )
        if not hits:
            return ok({"formatted_text": "", "memory_count": 0, "estimated_tokens": 0})

        # memory_id → score（无桥接表，hybrid 已融合 dense + sparse）
        id_map = {h["memory_id"]: h["score"] for h in hits}

        mem_query = _sel(Memory).where(Memory.memory_id.in_(list(id_map.keys())))
        if body.memory_types:
            mem_query = mem_query.where(Memory.memory_type.in_(body.memory_types))
        if body.status:
            mem_query = mem_query.where(Memory.status.in_(body.status))
        else:
            mem_query = mem_query.where(Memory.status == "active")
        # 状态类记忆（process/correction）是 agent 私有，额外按 agent_id 过滤；普通记忆跨 agent 共享
        mem_query = mem_query.where(
            Memory.memory_type.notin_(["process", "correction"]) | (Memory.agent_id == agent_id)
        )
        mem_result = await db.execute(mem_query)
        db_memories = {m.memory_id: m for m in mem_result.scalars().all()}

        # Step 3: Re-rank + filter
        now_dt = datetime.now(timezone.utc)
        HALF_LIFE_DAYS = 30
        scored = []
        for memory_id, mem_score in id_map.items():
            mem = db_memories.get(memory_id)
            if not mem:
                continue
            ms = mem_score or 0
            recency_val = 0.5
            if mem.created_at:
                try:
                    cd = mem.created_at.replace(tzinfo=None) if mem.created_at.tzinfo else mem.created_at
                    age_seconds = max(0, (now_dt.replace(tzinfo=None) - cd).total_seconds())
                    age_days = age_seconds / 86400
                    recency_val = _math.pow(0.5, age_days / HALF_LIFE_DAYS)
                except Exception:
                    pass
            final_score = round(
                (ms or 0) * 0.6 + recency_val * 0.15
                + (mem.importance or 0.5) * 0.15 + (mem.confidence or 0.5) * 0.1, 4
            )
            if final_score < SCORE_MIN_THRESHOLD:
                continue
            scored.append({
                "memory_id": mem.memory_id,
                "content": mem.content or "",
                "summary": mem.summary or "",
                "memory_type": mem.memory_type or "fact",
                "relevance_score": final_score,
            })
        if not scored:
            return ok({"formatted_text": "", "memory_count": 0, "estimated_tokens": 0})

        # Step 4: Group by type + sort
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        scored = [item for item in scored if item["memory_type"] != "correction"]

        if body.group_by_type:
            groups = {}
            for item in scored:
                groups.setdefault(item["memory_type"], []).append(item)
            sorted_types = sorted(
                [t for t in groups if t in TYPE_PRIORITY],
                key=lambda t: TYPE_PRIORITY[t],
            )
        else:
            # 平铺：不按类型分组，直接按相关性排序
            groups = {"_flat": scored}
            sorted_types = ["_flat"]

        # Step 5: Assemble within budget
        max_tokens = body.max_tokens or 3000
        lines = []
        token_estimate = 0
        memory_count = 0
        for mt in sorted_types:
            if memory_count >= MAX_MEMORY_COUNT:
                break
            if mt != "_flat":
                title = GROUP_TITLES.get(mt, f"## {mt}")
                lines.append(title)
                token_estimate += len(title) // 2
            for item in groups[mt]:
                if memory_count >= MAX_MEMORY_COUNT:
                    break
                text = item["content"]
                if len(text) > CONTENT_MAX_LEN and item["summary"]:
                    text = item["summary"]
                line = f"- {text}"
                est = len(line) // 2
                if token_estimate + est > max_tokens:
                    break
                lines.append(line)
                token_estimate += est
                memory_count += 1
            if token_estimate >= max_tokens:
                break

        formatted_text = "\n".join(lines) if lines else ""

        # 设置 context_snapshot（供 dashboard latest_context 使用，非空才记录）
        if formatted_text:
            request.state.context_snapshot = {
                "version": 1,
                "formatted_text": formatted_text,
                "memory_count": memory_count,
                "query": body.query,
                "user_id": body.user_id,
                "scene_id": body.scene_id,
                "session_id": body.session_id,
                "task_id": body.task_id,
                "agent_id": agent_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        return ok({
            "formatted_text": formatted_text,
            "memory_count": memory_count,
            "estimated_tokens": token_estimate,
            "fragments": scored,
        })

    except Exception as e:
        logger.error(f"Context generation failed: {e}")
        return error(
            message="Context generation failed",
            code=-2,
            data={"formatted_text": "", "memory_count": 0, "estimated_tokens": 0},
            error_code="CONTEXT_FAILED",
        )


@router.put("/update", summary="更新单条记忆")
async def memory_update(
    body: MemoryUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """更新单条记忆的内容、重要性、标签等字段。"""
    result = await memory_store.update_memory(
        memory_id=body.memory_id,
        db=db,
        content=body.content,
        summary=body.summary,
        status=body.status,
        importance=body.importance,
        confidence=body.confidence,
        tags=body.tags,
    )
    if result["updated"]:
        return ok(MemoryUpdateResponse(
            memory_id=body.memory_id,
            updated=True,
            version=result.get("version", 1),
        ).model_dump())
    else:
        return ok(MemoryUpdateResponse(
            memory_id=body.memory_id,
            updated=False,
            version=0,
        ).model_dump())


# ============================================================
# 删除（软删除） — 对齐前端对接文档 二.3 节
# ============================================================

@router.delete("/delete", summary="删除记忆（软删除）")
async def memory_delete(
    body: MemoryDeleteRequest,
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """软删除单条记忆（状态置为 deleted，从 Qdrant 移除向量）。"""
    result = await memory_store.soft_delete(
        memory_id=body.memory_id,
        db=db,
        reason=body.reason,
    )
    return ok(MemoryDeleteResponse(
        memory_id=body.memory_id,
        deleted=result["deleted"],
        previous_status=result.get("previous_status", "active"),
    ).model_dump())


# ============================================================
# 列出全部 — 对齐前端对接文档 一.3 节
# ============================================================

def _parse_iso_time(value: str | None) -> datetime | None:
    """解析 ISO 8601 时间字符串（容忍 Z 后缀），失败返回 None。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


@router.post("/list", summary="列出全部记忆")
async def memory_list(
    user_id: str = Query(...),
    scene_id: str | None = Query(None),
    task_id: str | None = Query(None),
    session_id: str | None = Query(None),
    agent_id: str | None = Query(None, description="智能体标识"),
    memory_type: str | None = Query(None, description="记忆类型"),
    memory_scope: str | None = Query(None),
    time_start: str | None = Query(None, description="时间范围起点 ISO 8601"),
    time_end: str | None = Query(None, description="时间范围终点 ISO 8601"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """
    分页列出用户全部记忆。

    支持按 scene/task/session/agent/memory_type/memory_scope/time 过滤，
    优先使用 MemoryStore 直查 PostgreSQL；查询为空时降级到 MCP 路径。
    """
    try:
        result = await memory_store.list_memories(
            user_id=user_id,
            db=db,
            scene_id=scene_id,
            task_id=task_id,
            session_id=session_id,
            agent_id=agent_id,
            memory_types=[memory_type] if memory_type else None,
            memory_scope=memory_scope,
            time_start=_parse_iso_time(time_start),
            time_end=_parse_iso_time(time_end),
            page=page,
            page_size=page_size,
        )

        if result["total"] > 0:
            return ok(result)

        logger.info(f"MemoryStore empty for user={user_id}, falling back to MCP")
        from app.mcp_client import mcp_client
        mcp_result = await mcp_client.list_memories(user_id=user_id)
        return ok(mcp_result)

    except Exception as e:
        logger.error(f"List failed: {e}")
        from app.mcp_client import mcp_client
        try:
            mcp_result = await mcp_client.list_memories(user_id=user_id)
            return ok(mcp_result)
        except Exception:
            return ok({"items": [], "total": 0, "page": page, "page_size": page_size})


# ============================================================
# 清除全部 — 对齐前端对接文档 一.4 节
# ============================================================

@router.post("/delete-all", summary="清除全部记忆")
async def memory_delete_all(
    user_id: str = Query(...),
    scene_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """
    清除用户全部记忆 — PostgreSQL + Qdrant 双清。
    同时清理 MCP/mem0 中的记忆（如果可用）。
    """
    store_result = await memory_store.delete_all_memories(
        user_id=user_id,
        db=db,
        scene_id=scene_id,
    )

    try:
        from app.mcp_client import mcp_client
        await mcp_client.delete_all_memories(user_id=user_id)
        logger.info(f"MCP memories also cleared for user={user_id}")
    except Exception as e:
        logger.warning(f"MCP delete-all failed (non-fatal): {e}")

    return ok({
        "message": store_result["message"],
        "deleted_count": store_result["deleted_count"],
    })


# ============================================================
# 记忆层级分布统计 — 对齐记忆层级统计接口交接文档
# ============================================================

SCOPE_LEVELS = ("user", "session", "task", "agent")
CLASSIFICATION_VERSION = "memory_scope_v1"


@router.get("/stats", summary="记忆层级分布统计")
async def memory_stats(
    request: Request,
    user_id: str = Query(..., min_length=1, description="用户标识"),
    scene_id: str | None = Query(None, description="场景过滤条件（可选）"),
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
):
    """
    统计指定用户在各记忆层级（user/session/task/agent）的分布。

    返回 total、level_distribution（四项固定）、generated_at、classification_version。
    统计条件与 /memory/list 保持一致，确保 stats.total == list.total。
    默认只统计 status=active 的记录（与列表口径一致）。
    """
    start = time_module.perf_counter()
    trace_id = f"trace_{uuid4().hex[:24]}"

    try:
        # 授权校验：agent 已在 get_current_agent 中通过 X-API-Key 认证
        # 数据隔离由 agent 绑定的 scene_id 保障
        await authorize_user_access(
            requested_user_id=user_id,
            agent_id=agent_id,
            request=request,
        )

        # 聚合查询：单次 GROUP BY 完成，不循环查四次
        # status="active" 与 /memory/list 默认口径一致，确保 stats.total == list.total
        counts = await memory_store.count_by_scope(
            user_id=user_id,
            db=db,
            scene_id=scene_id,
            status="active",
        )

        # 补齐四项并计算 total / ratio
        total = sum(counts.get(level, 0) for level in SCOPE_LEVELS)
        distribution = [
            {
                "level": level,
                "count": counts.get(level, 0),
                "ratio": round(counts.get(level, 0) / total, 4) if total else 0,
            }
            for level in SCOPE_LEVELS
        ]

        elapsed_ms = int((time_module.perf_counter() - start) * 1000)

        logger.info(
            f"Stats: user={user_id}, scene={scene_id or '(none)'}, "
            f"total={total}, elapsed={elapsed_ms}ms, trace_id={trace_id}"
        )

        return ok({
            "total": total,
            "level_distribution": distribution,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "classification_version": CLASSIFICATION_VERSION,
        })

    except Exception as e:
        elapsed_ms = int((time_module.perf_counter() - start) * 1000)
        logger.error(
            f"Stats query failed: user={user_id}, scene={scene_id or '(none)'}, "
            f"elapsed={elapsed_ms}ms, trace_id={trace_id}, error={e}"
        )
        return error(
            message="统计查询异常",
            code=-1,
            data={
                "total": 0,
                "level_distribution": [
                    {"level": level, "count": 0, "ratio": 0}
                    for level in SCOPE_LEVELS
                ],
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "classification_version": CLASSIFICATION_VERSION,
            },
            error_code="STATS_FAILED",
        )
# -*- coding: utf-8 -*-
"""User profile endpoint — appended to memory.py"""


class ProfileRequest(BaseModel):
    user_id: str = Field(..., description="用户标识")
    scene_id: Optional[str] = Field(None, description="场景标识（可选，不传则返回全部场景画像）")
    max_memories: int = Field(default=50, description="最多加载的偏好+事实记忆数")


@router.post("/profile", summary="用户画像报告")
async def memory_profile(
    body: ProfileRequest,
    db: AsyncSession = Depends(get_db),
):
    """返回用户画像。传 scene_id 查单场景；不传则返回该用户全部场景的画像列表。"""
    try:
        from sqlalchemy import select as _sel
        from app.models.base import Persona, Scene
        from app.services.l3_persona import generate_persona

        if body.scene_id:
            # 指定场景：生成/查该场景画像
            result = await generate_persona(db, body.user_id, body.scene_id)
            return ok({
                "persona": result.get("content", ""),
                "scene_id": body.scene_id,
                "changed_scenes": result.get("changed_scenes", 0),
            })

        # 全部场景：查该用户所有 persona + scene_name
        personas_result = await db.execute(
            _sel(Persona).where(Persona.user_id == body.user_id)
        )
        personas = list(personas_result.scalars().all())

        scene_names: dict[str, str] = {}
        scene_ids = [p.scene_id for p in personas if p.scene_id]
        if scene_ids:
            scenes_result = await db.execute(
                _sel(Scene.scene_id, Scene.scene_name).where(Scene.scene_id.in_(scene_ids))
            )
            scene_names = {s.scene_id: s.scene_name for s in scenes_result.all()}

        return ok({
            "personas": [
                {
                    "scene_id": p.scene_id,
                    "scene_name": scene_names.get(p.scene_id, p.scene_id or ""),
                    "content": p.content,
                }
                for p in personas
            ],
            "total": len(personas),
        })
    except Exception as e:
        logger.error(f"Profile failed: {e}")
        return error(message="画像生成失败", code=-2, error_code="PROFILE_FAILED")

