# -*- coding: utf-8 -*-
"""
记忆核心 API — 对齐前端对接文档。

端点:
  POST /write       — 同步写入记忆
  POST /async_write — 异步写入（即刻返回 request_id）
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
from sqlalchemy import insert
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
from app.models.base import InteractionRecord, RetrievalRequest, RetrievalResult
from app.core.exceptions import ValidationError
from app.core.logger import get_logger
from app.schemas.common import error, ok
from app.schemas.memory import (
    AsyncWriteRequest,
    AsyncWriteResponse,
    ContextRequest,
    MemoryDeleteRequest,
    MemoryDeleteResponse,
    MemoryEvent,
    MemorySearchRequest,
    MemoryUpdateRequest,
    MemoryUpdateResponse,
    MemoryWriteRequest,
    MemoryWriteResponse,
    WriteResultItem,
)
from app.services.mem0_client import mem0_client
from app.services.memory_pipeline import memory_pipeline
from app.services.memory_store import memory_store
from app.services.memory_service import (
    get_user_profile,
    get_session_context,
    get_task_view,
)
from app.services.mq_producer import mq_producer
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

    延迟: 5-15s（LLM抽取+生成+去重+存储）。
    """
    start = time_module.perf_counter()
    itype = body.interaction_type
    settings = get_settings()

    # 合并 ID 来源（Header > Body，开发模式自动补默认值）
    effective_user_id = normalize_id(user_id_header or body.user_id)
    effective_scene_id = scene_id or body.scene_id or DEFAULT_DEV_SCENE_ID
    effective_session_id = session_id_header or body.session_id or f"sess_{uuid4().hex[:12]}"
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

    # --- 写入原始交互记录（批量 insert）---
    await _batch_write_records(body, db, effective_user_id, agent_id,
                                effective_scene_id, effective_session_id,
                                effective_task_id)
    await db.commit()

    # ============================================================
    # 根据配置选择处理模式
    # ============================================================

    # Direct Pipeline
    conversation_text = body.get_content_text()

    try:
        pipeline_result = await memory_pipeline.run(
            text=conversation_text,
            user_id=effective_user_id,
            agent_id=agent_id,
            scene_id=effective_scene_id,
            session_id=effective_session_id,
            task_id=body.task_id,
            source_record_ids=None,
            extraction_types=["key_fact", "task_state", "preference", "process", "feedback"],
            task_context=body.metadata,
            db=db,
        )
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        # 明确标记降级：结果为占位 SKIP，不代表真实去重判定
        return ok(MemoryWriteResponse(
            results=[
                WriteResultItem(
                    id="",
                    memory=m.content[:80] if hasattr(m, 'content') else "",
                    event=MemoryEvent.SKIP,
                )
                for m in body.messages
            ],
            mode="degraded",
        ).model_dump())

    # --- 将 PipelineResult 映射为前端 results 格式 ---
    results = _pipeline_to_write_results(pipeline_result)

    elapsed = round((time_module.perf_counter() - start) * 1000, 2)
    logger.info(
        f"[Pipeline] 同步写入完成: type={itype}, user_id={effective_user_id}, "
        f"messages={len(body.messages)}, "
        f"memories={pipeline_result.new_count + pipeline_result.merged_count}, "
        f"discarded={pipeline_result.discarded_count}, elapsed={elapsed}ms"
    )

    return ok(MemoryWriteResponse(results=results, mode="pipeline").model_dump())


# ============================================================
# 写入辅助函数 — 批量 insert
# ============================================================

async def _batch_write_records(
    body: MemoryWriteRequest, db, user_id: str, agent_id: str,
    scene_id: str | None, session_id: str, task_id: str | None = None
) -> None:
    """批量写入交互记录（使用单条 INSERT ... VALUES 多条）"""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    itype = body.interaction_type
    records = []

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
        "recorded_at": now,
        "extra_meta": body.metadata or {},
    }

    extra = dict(body.metadata or {})

    if itype == "dialogue":
        for i, msg in enumerate(body.messages):
            records.append({
                **base,
                "record_id": f"rec_{uuid4().hex[:24]}",
                "turn_index": i,
                "role": msg.role,
                "content": msg.content,
            })

    elif itype == "session":
        if body.session_time:
            extra["session_time"] = body.session_time
        if body.session_source:
            extra["session_source"] = body.session_source
        base["extra_meta"] = extra

        for i, msg in enumerate(body.messages):
            records.append({
                **base,
                "record_id": f"rec_{uuid4().hex[:24]}",
                "turn_index": i,
                "role": msg.role,
                "content": msg.content,
            })

        if body.session_summary:
            records.append({
                **base,
                "record_id": f"rec_{uuid4().hex[:24]}",
                "turn_index": len(body.messages),
                "role": "session_summary",
                "content": body.session_summary,
                "content_type": "session_summary",
            })

    elif itype == "task_process":
        base["extra_meta"] = extra
        for i, msg in enumerate(body.messages):
            records.append({
                **base,
                "record_id": f"rec_{uuid4().hex[:24]}",
                "turn_index": i,
                "role": msg.role,
                "content": msg.content,
            })

        turn_offset = len(body.messages)
        task_fields = [
            ("task_goal", body.task_goal),
            ("task_progress", body.task_progress),
            ("task_result", body.task_result),
        ]
        for j, (role_name, content) in enumerate(task_fields):
            if content:
                records.append({
                    **base,
                    "record_id": f"rec_{uuid4().hex[:24]}",
                    "turn_index": turn_offset + j,
                    "role": role_name,
                    "content": content,
                    "content_type": "task_process",
                })

    if records:
        await db.execute(insert(InteractionRecord), records)


# ============================================================
# Pipeline 结果映射
# ============================================================

def _pipeline_to_write_results(pipeline_result) -> list[WriteResultItem]:
    """
    将 PipelineResult.details 转换为前端 WriteResultItem 格式。

    映射规则:
      keep_new        → ADD      (新记忆创建)
      merge           → MERGE    (合并到已有)
      update_existing → UPDATE   (更新已有记忆)
      discard         → SKIP     (重复或不包含新信息)
      conflict        → CONFLICT (冲突需人工确认)
    """
    results = []
    for d in pipeline_result.details:
        action = d.get("action", "keep_new")
        memory_id = d.get("memory_id", "") or ""
        content = d.get("content_preview", "") or ""

        if action == "discard":
            results.append(WriteResultItem(
                id="",
                memory=content,
                event=MemoryEvent.SKIP,
            ))
        elif action == "merge":
            results.append(WriteResultItem(
                id=memory_id,
                memory=content,
                event=MemoryEvent.MERGE,
            ))
        elif action == "conflict":
            # 冲突：返回给前端标记为冲突，等待人工处理
            results.append(WriteResultItem(
                id=memory_id,
                memory=f"[冲突] {content}",
                event=MemoryEvent.ADD,  # 仍写入但标记为 pending
            ))
        elif action == "update_existing":
            results.append(WriteResultItem(
                id=memory_id,
                memory=content,
                event=MemoryEvent.UPDATE,
            ))
        else:  # keep_new
            results.append(WriteResultItem(
                id=memory_id,
                memory=content,
                event=MemoryEvent.ADD,
            ))

    return results


# ============================================================
# 异步写入 — 对齐前端对接文档 一.1 附节
# ============================================================

@router.post("/async_write", summary="异步写入记忆", status_code=202)
async def memory_async_write(
    body: AsyncWriteRequest,
    request: Request,
    agent_id: str = Depends(get_current_agent),
    user_id_header: str = Depends(get_current_user_id),
):
    """
    异步写入 — 即刻返回 request_id，后台处理。

    处理管线:
      1. 鉴权（开发阶段跳过）
      2. 投递到 Kafka MQ
      3. Consumer 异步处理 → 落库
      4. 失败时降级为同步写入（status=pending_extract）
    """
    request_id = f"async_{uuid4().hex[:24]}"
    effective_user_id = normalize_id(user_id_header or body.user_id)
    body_dict = body.model_dump()

    mq_ok = await _try_deliver_to_mq(request_id, effective_user_id, agent_id, body_dict)

    if mq_ok:
        logger.info(f"异步写入已投递 MQ: request_id={request_id}")
    else:
        logger.warning(f"MQ 不可用，降级同步写入: request_id={request_id}")
        await _fallback_sync_write(request_id, effective_user_id, agent_id, body)

    return ok(AsyncWriteResponse(
        request_id=request_id,
        status="accepted",
    ).model_dump())


async def _try_deliver_to_mq(
    request_id: str, user_id: str, agent_id: str, body_dict: dict
) -> bool:
    """尝试投递到 Kafka MQ。返回 True 投递成功，False 失败。"""
    if not mq_producer.is_available:
        logger.debug("MQ Producer 未初始化，跳过投递")
        return False

    return await mq_producer.publish_memory_write(
        request_id=request_id,
        user_id=user_id,
        agent_id=agent_id,
        body_dict=body_dict,
    )


async def _fallback_sync_write(
    request_id: str, user_id: str, agent_id: str, body: AsyncWriteRequest
) -> None:
    """MQ 不可用时降级为同步写入原始记录（status=pending_extract，后续可补处理）"""
    from app.core.database import async_session_factory
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    itype = body.interaction_type
    extra_meta = dict(body.metadata or {})

    if itype == "session":
        if body.session_time:
            extra_meta["session_time"] = body.session_time
        if body.session_source:
            extra_meta["session_source"] = body.session_source

    records = []
    base = {
        "user_id": user_id,
        "agent_id": agent_id,
        "scene_id": body.scene_id,
        "session_id": body.session_id or f"sess_{uuid4().hex[:12]}",
        "task_id": body.task_id,
        "interaction_type": itype,
        "content_type": "text",
        "processed": False,
        "status": "pending_extract",
        "recorded_at": now,
        "extra_meta": extra_meta,
    }

    async with async_session_factory() as session:
        for i, msg in enumerate(body.messages):
            records.append({
                **base,
                "record_id": f"rec_{uuid4().hex[:24]}",
                "turn_index": i,
                "role": msg.role,
                "content": msg.content,
            })

        if itype == "session" and body.session_summary:
            records.append({
                **base,
                "record_id": f"rec_{uuid4().hex[:24]}",
                "turn_index": len(body.messages),
                "role": "session_summary",
                "content": body.session_summary,
                "content_type": "session_summary",
            })

        if itype == "task_process":
            turn_offset = len(body.messages)
            task_fields = [
                ("task_goal", body.task_goal),
                ("task_progress", body.task_progress),
                ("task_result", body.task_result),
            ]
            for j, (role_name, content) in enumerate(task_fields):
                if content:
                    records.append({
                        **base,
                        "record_id": f"rec_{uuid4().hex[:24]}",
                        "turn_index": turn_offset + j,
                        "role": role_name,
                        "content": content,
                        "content_type": "task_process",
                    })

        if records:
            await session.execute(insert(InteractionRecord), records)
        await session.commit()

    logger.info(
        f"降级同步写入完成: request_id={request_id}, "
        f"records={len(records)}, status=pending_extract"
    )


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
        # ── 主路径: Qdrant 向量检索 → T_MEMORY_VECTOR 桥接 → T_MEMORY ──
        from app.core.qdrant_client import qdrant_client as _qd
        from app.services.embedding_client import embedding_client as _emb
        from app.models.base import MemoryVector, Memory
        import math as _math

        # Step 1: 向量化 query
        query_vector = await _emb.embed_single(body.query)

        # Step 2: Qdrant 向量检索 + payload 预过滤
        payload_filters = {}
        if body.scene_id:
            payload_filters["scene_id"] = body.scene_id
        if body.task_id:
            payload_filters["task_id"] = body.task_id
        if body.session_id:
            payload_filters["session_id"] = body.session_id

        hits = _qd.search_similar(
            query_vector=query_vector,
            user_id=body.user_id,
            top_k=max(body.top_k * 3, 30),
            payload_filters=payload_filters if payload_filters else None,
        )

        if not hits:
            return ok({"query": body.query, "results": [], "total_candidates": 0, "elapsed_ms": 0})

        # Step 3: T_MEMORY_VECTOR 桥接 → memory_id + score
        from sqlalchemy import select as _sel
        # 构建 Qdrant point_id → score 映射（normalize UUID 格式）
        point_scores = {str(h["id"]): float(h["score"]) if h["score"] is not None else 0.0 for h in hits}
        mv_result = await db.execute(
            _sel(MemoryVector).where(MemoryVector.vector_store_id.in_(list(point_scores.keys())))
        )
        id_map = {}      # memory_id → qdrant_score
        for mv in mv_result.scalars().all():
            id_map[mv.memory_id] = point_scores.get(mv.vector_store_id, 0.0)

        if not id_map:
            return ok({"query": body.query, "results": [], "total_candidates": len(hits), "elapsed_ms": 0})

        # Step 4: T_MEMORY 取权威数据 + 后过滤
        mem_query = _sel(Memory).where(Memory.memory_id.in_(list(id_map.keys())))
        if body.memory_types:
            mem_query = mem_query.where(Memory.memory_type.in_(body.memory_types))
        if body.status:
            mem_query = mem_query.where(Memory.status.in_(body.status))
        else:
            mem_query = mem_query.where(Memory.status == "active")

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
# 层级统计 — 通用记忆建模与多层记忆管理
# ============================================================

@router.get("/stats", summary="层级记忆统计")
async def memory_stats(
    user_id: str = Query(...),
    scene_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """按 user/session/task/agent 四级统计。利用现有字段推断，不需要新增列。"""
    from app.services.memory_service import get_memory_stats as _stats
    from datetime import datetime as _dt, timezone as _tz

    result = await _stats(db, user_id=user_id, scene_id=scene_id)
    result["generated_at"] = _dt.now(_tz.utc).isoformat()
    result["classification_version"] = "memory_scope_v1"
    return ok(result)


# ============================================================
# 上下文 — 对齐前端对接文档 二.1 节
# ============================================================

@router.post("/context", summary="Prompt 上下文片段")
async def memory_context(
    body: ContextRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
):
    """
    Prompt 上下文。

    三层聚合 — 不混入原始记忆碎片，仅返回结构化聚合结果 + LLM 总结。
    """
    try:
        aggregation = {}
        scope_type = None

        if body.task_id:
            scope_type = "task_view"
            task_view = await get_task_view(db, body.task_id)
            aggregation = {
                "type": "task_view",
                "task_id": body.task_id,
                "goal": task_view["current_goal"]["content"] if task_view.get("current_goal") else "",
                "timeline": [
                    {"stage": item.get("sub_type", "progress"), "content": item["content"]}
                    for item in task_view.get("timeline", [])
                ],
                "constraints": [item["content"] for item in task_view.get("constraints", [])],
                "processes": [item["content"] for item in task_view.get("processes", [])],
                "decisions": [item["content"] for item in task_view.get("decisions", [])],
                "facts": [item["content"] for item in task_view.get("facts", [])],
            }

        elif body.session_id:
            scope_type = "session_context"
            sess_ctx = await get_session_context(db, body.session_id)
            by_type_clean = {
                k: [item["content"] for item in v]
                for k, v in sess_ctx.get("by_type", {}).items()
            }
            aggregation = {
                "type": "session_context",
                "session_id": body.session_id,
                "by_type": by_type_clean,
                "key_items": [
                    {"type": item["memory_type"], "content": item["content"]}
                    for item in sess_ctx.get("key_items", [])
                ],
            }

        elif body.include_preferences or body.include_facts:
            scope_type = "user_profile"
            profile = await get_user_profile(db, body.user_id)
            aggregation = {
                "type": "user_profile",
                "user_id": body.user_id,
                "preferences": profile.get("preferences", []),
                "facts": profile.get("facts", []),
            }

        # LLM 总结
        formatted_text = ""
        contents = []
        for key, val in aggregation.items():
            if key in ("preferences", "facts") and isinstance(val, list):
                contents.extend(val)
            elif key == "goal" and val:
                contents.append(val)
            elif key == "timeline" and isinstance(val, list):
                contents.extend(item["content"] for item in val)
            elif key == "by_type" and isinstance(val, dict):
                for items in val.values():
                    contents.extend(items)
            elif key == "key_items" and isinstance(val, list):
                contents.extend(item["content"] for item in val)

        if contents:
            try:
                from app.services.llm_client import llm_client as _llm
                memory_count = min(len(contents), 20)  # 实际送入 LLM 的条目数
                lines = "\n".join(f"- {c[:200]}" for c in contents[:memory_count])
                formatted_text = await _llm.chat_completion([{
                    "role": "user",
                    "content": f"将以下记忆碎片总结为一段通顺的摘要，注入AI对话上下文。保留关键信息，去除冗余：\n{lines}"
                }], max_tokens=body.max_tokens or 500)
            except Exception:
                pass

        # 设置 context_snapshot 供日志中间件合并到 ApiLog
        # 仅 formatted_text 非空时才写入，避免空快照污染 latest_context
        if formatted_text:
            generated_at = datetime.now(timezone.utc)
            trace_id = getattr(request.state, "trace_id", None)
            request.state.context_snapshot = {
                "version": 1,
                "query": body.query,
                "formatted_text": formatted_text,
                "memory_count": memory_count,
                "memory_ids": [],  # TODO: 从聚合来源记录原始 memory_id，当前仅追踪数量
                "return_mode": "aggregation",
                "scope_type": scope_type,
                "user_id": body.user_id,
                "agent_id": agent_id,
                "scene_id": body.scene_id,
                "session_id": body.session_id,
                "task_id": body.task_id,
                "generated_at": generated_at.isoformat(),
                "trace_id": trace_id,
            }

        return ok({
            "aggregation": aggregation,
            "formatted_text": formatted_text,
            "estimated_tokens": len(formatted_text) // 2 if formatted_text else 0,
        })
    except Exception as e:
        logger.error(f"Context generation failed: {e}")
        return error(
            message="上下文生成失败",
            code=-2,
            data={
                "aggregation": {},
                "formatted_text": "",
                "estimated_tokens": 0,
            },
            error_code="CONTEXT_FAILED",
        )


# ============================================================
# 更新 — 对齐前端对接文档 二.2 节
# ============================================================

@router.put("/update", summary="更新记忆")
async def memory_update(
    body: MemoryUpdateRequest,
    db: AsyncSession = Depends(get_db),
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

@router.post("/list", summary="列出全部记忆")
async def memory_list(
    user_id: str = Query(...),
    scene_id: str | None = Query(None),
    task_id: str | None = Query(None),
    session_id: str | None = Query(None),
    memory_scope: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    分页列出用户全部记忆。

    优先使用 MemoryStore 直查 PostgreSQL；
    MemoryStore 查询为空时降级到 MCP 路径。
    """
    try:
        result = await memory_store.list_memories(
            user_id=user_id,
            db=db,
            scene_id=scene_id,
            task_id=task_id,
            session_id=session_id,
            memory_scope=memory_scope,
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
