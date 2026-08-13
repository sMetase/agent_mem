# -*- coding: utf-8 -*-
"""
会话管理 API — 5 个接口，全部实现真实 DB 操作。

对齐前端对接文档 三 节：
- POST /session — 创建会话
- GET /session/{id} — 查询
- GET /session — 列表
- PUT /session/{id} — 更新
- POST /session/{id}/close — 关闭会话（含碎片压缩+摘要升级）
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_agent, get_current_user_id
from app.core.database import get_db
from app.core.logger import get_logger
from app.core.security import generate_session_id
from app.models.base import Session, Memory, MemoryVector
from app.schemas.common import ok
from app.schemas.session import SessionCreateRequest, SessionUpdateRequest

logger = get_logger("session_api")
router = APIRouter()



@router.post("", summary="创建会话", status_code=201)
async def session_create(
    body: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
):
    """创建新会话，状态 active"""
    session_id = generate_session_id()

    session = Session(
        session_id=session_id,
        user_id=body.user_id.strip().lower(),
        agent_id=body.agent_id or agent_id,
        scene_id=body.scene_id,
        task_id=body.task_id,
        status="active",
        started_at=datetime.now(timezone.utc),
        message_count=0,
        extra_meta=body.extra_meta or {},
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(f"会话创建: session_id={session_id}, user_id={body.user_id}")

    return ok({
        "session_id": session_id,
        "user_id": session.user_id,
        "agent_id": session.agent_id,
        "scene_id": session.scene_id,
        "task_id": session.task_id,
        "status": "active",
        "started_at": session.started_at.isoformat() if session.started_at else None,
    }, "创建成功")


@router.get("/{session_id}", summary="查询会话")
async def session_get(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """查询单个会话"""
    result = await db.execute(
        select(Session).where(Session.session_id == session_id.strip().lower())
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError(f"会话不存在: {session_id}")

    return ok({
        "session_id": session.session_id,
        "user_id": session.user_id,
        "agent_id": session.agent_id,
        "scene_id": session.scene_id,
        "task_id": session.task_id,
        "status": session.status,
        "message_count": session.message_count,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
    })


@router.get("", summary="会话列表")
async def session_list(
    user_id: str | None = Query(None),
    agent_id: str | None = Query(None),
    status: str | None = Query(None),
    scene_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """分页查询会话列表"""
    query = select(Session)

    if user_id:
        query = query.where(Session.user_id == user_id.strip().lower())
    if agent_id:
        query = query.where(Session.agent_id == agent_id.strip().lower())
    if status:
        query = query.where(Session.status == status)
    if scene_id:
        query = query.where(Session.scene_id == scene_id.strip().lower())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(Session.started_at.desc()).offset(offset).limit(page_size)
    sessions = (await db.execute(query)).scalars().all()

    items = []
    for s in sessions:
        items.append({
            "session_id": s.session_id,
            "user_id": s.user_id,
            "agent_id": s.agent_id,
            "scene_id": s.scene_id,
            "task_id": s.task_id,
            "status": s.status,
            "message_count": s.message_count,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        })

    return ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.put("/{session_id}", summary="更新会话")
async def session_update(
    session_id: str,
    body: SessionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """更新会话状态/关联任务"""
    result = await db.execute(
        select(Session).where(Session.session_id == session_id.strip().lower())
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError(f"会话不存在: {session_id}")

    if body.status is not None:
        session.status = body.status
    if body.task_id is not None:
        session.task_id = body.task_id.strip().lower()
    if body.extra_meta is not None:
        session.extra_meta = body.extra_meta

    await db.commit()
    logger.info(f"会话更新: session_id={session_id}")

    return ok({"session_id": session_id, "updated": True}, "更新成功")


@router.post("/{session_id}/close", summary="关闭会话（含碎片压缩+摘要升级）")
async def session_close(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """
    关闭会话 + 记忆压缩。

    流程:
      1. 会话标记 closed + ended_at
      2. 查该会话所有 active 记忆，按类型分流:
         - preference / fact  → 升级为长期记忆 (session_id=NULL)
         - 其他类型           → 压缩池
      3. 压缩池非空 → LLM 生成摘要 → INSERT 新记忆
      4. 压缩池记忆 → status='expired' + 删除 T_MEMORY_VECTOR + Qdrant
      5. 新摘要 → 向量化 + T_MEMORY_VECTOR + Qdrant
    """
    sid = session_id.strip().lower()

    # ── Step 1: 会话标记关闭 ──
    result = await db.execute(select(Session).where(Session.session_id == sid))
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError(f"会话不存在: {session_id}")

    session.status = "closed"
    session.ended_at = datetime.now(timezone.utc)

    # ── Step 2: 查该会话所有 active 记忆 ──
    mem_result = await db.execute(
        select(Memory).where(
            Memory.session_id == sid,
            Memory.status == "active",
        )
    )
    memories = list(mem_result.scalars().all())

    total_count = len(memories)
    compress_types = {"task_state", "process", "correction"}
    compress_pool = [m for m in memories if m.memory_type in compress_types]
    keep_count = total_count - len(compress_pool)  # pref/fact 原样保留
    compressed_count = len(compress_pool)

    # ── Step 3: 压缩路径（pref/fact 不动，保持原样）──
    summary_text = ""
    if compress_pool:
        # 拼接为 LLM 输入
        contents = [m.content for m in compress_pool]
        lines = "\n".join(f"- {c[:200]}" for c in contents[:30])
        try:
            from app.services.llm_client import llm_client as _llm
            summary_text = await _llm.chat_completion([{
                "role": "user",
                "content": (
                    f"将以下会话记忆碎片总结为一段通顺的摘要（中文），"
                    f"保留关键信息，去除流程性冗余：\n{lines}"
                ),
            }], max_tokens=500)
        except Exception as e:
            logger.warning(f"LLM 压缩总结失败: {e}")
            summary_text = "；".join(contents[:5])

        # 旧碎片标记 expired
        compress_ids = [m.memory_id for m in compress_pool]
        await db.execute(
            sql_update(Memory)
            .where(Memory.memory_id.in_(compress_ids))
            .values(status="expired")
        )

        # 删除 T_MEMORY_VECTOR + Qdrant 向量
        try:
            from app.models.base import MemoryVector as _MV
            mv_result = await db.execute(
                select(_MV).where(_MV.memory_id.in_(compress_ids))
            )
            expired_mvs = list(mv_result.scalars().all())
            if expired_mvs:
                qdrant_ids = [mv.vector_store_id for mv in expired_mvs]
                for mv in expired_mvs:
                    await db.delete(mv)
                try:
                    from app.core.qdrant_client import qdrant_client as _qd
                    _qd.delete_vectors(qdrant_ids)
                except Exception as e:
                    logger.warning(f"Qdrant 删除过期向量失败: {e}")
        except Exception as e:
            logger.warning(f"T_MEMORY_VECTOR 清理失败: {e}")

    # ── Step 5: 新摘要入库 ──
    if summary_text:
        import uuid as _uuid
        new_memory_id = f"mem_{_uuid.uuid4().hex[:16]}"
        new_memory = Memory(
            memory_id=new_memory_id,
            user_id=session.user_id,
            agent_id=session.agent_id,
            scene_id=session.scene_id,
            session_id=sid,
            task_id=session.task_id,
            content=summary_text,
            summary=summary_text[:200],
            key_points=[],
            memory_type="process",
            tags=["session_summary"],
            entities=[],
            status="active",
            version=1,
            importance=0.7,
            confidence=0.8,
            source_type="compressed",
            source_record_ids=[],
            memory_scope="session",
        )
        db.add(new_memory)
        await db.flush()

        # 向量化 + Qdrant + T_MEMORY_VECTOR
        try:
            from app.core.qdrant_client import qdrant_client as _qd, _str_to_uuid
            from app.services.embedding_client import embedding_client as _emb
            vector = await _emb.embed_single(summary_text)
            point_id = f"pt_{_uuid.uuid4().hex[:16]}"
            qdrant_id = _str_to_uuid(point_id)
            _qd.upsert_single(
                point_id=point_id,
                vector=vector,
                payload={
                    "user_id": session.user_id,
                    "scene_id": session.scene_id or "",
                    "task_id": session.task_id or "",
                    "session_id": sid,
                },
            )
            mv = MemoryVector(
                memory_id=new_memory_id,
                vector_store_id=qdrant_id,
                dimension=1024,
            )
            db.add(mv)
        except Exception as e:
            logger.warning(f"新摘要向量化写入失败: {e}")

    await db.commit()

    logger.info(
        f"会话关闭完成: session_id={sid}, total={total_count}, "
        f"kept={keep_count}, compressed={compressed_count}"
    )

    return ok({
        "session_id": session_id,
        "status": "closed",
        "total_memory_count": total_count,
        "kept_count": keep_count,
        "compressed_count": compressed_count,
        "summary_text": summary_text,
        "ended_at": session.ended_at.isoformat(),
    }, "关闭成功")
