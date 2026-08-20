# -*- coding: utf-8 -*-
"""
任务管理 API — 6 个接口，全部实现真实 DB 操作。

对齐前端对接文档 四 节：
- POST /task — 创建任务
- GET /task/{id} — 查询
- GET /task — 列表
- PUT /task/{id} — 更新进展
- GET /task/{id}/progress — 进展摘要
- POST /task/{id}/complete — 完成任务
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_agent, get_current_user_id
from app.core.database import get_db
from app.core.exceptions import NotFoundError, ConflictError
from app.core.logger import get_logger
from app.core.security import generate_task_id
from app.models.base import Task, Memory
from app.schemas.common import ok
from app.schemas.task import TaskCreateRequest, TaskUpdateRequest

logger = get_logger("task_api")
router = APIRouter()

# 合法状态转换规则
VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in_progress", "completed", "cancelled"},
    "in_progress": {"completed", "cancelled", "pending"},
    "completed": {"in_progress", "cancelled"},  # 允许重新打开已完成任务
    "cancelled": {"pending"},  # 取消后可重新激活
}


def _validate_status_transition(current: str, new: str) -> None:
    """校验状态转换合法性"""
    if current == new:
        return
    allowed = VALID_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise ConflictError(
            f"任务状态不能从 '{current}' 直接转为 '{new}'，"
            f"允许的转换: {', '.join(sorted(allowed))}"
        )


@router.post("", summary="创建任务", status_code=201)
async def task_create(
    body: TaskCreateRequest,
    db: AsyncSession = Depends(get_db),
    agent_id: str = Depends(get_current_agent),
):
    """创建新任务，状态 pending"""
    task_id = generate_task_id()

    task = Task(
        task_id=task_id,
        user_id=body.user_id.strip().lower(),
        agent_id=body.agent_id or agent_id,
        scene_id=body.scene_id,
        session_id=body.session_id,
        title=body.title,
        goal=body.goal,
        status="pending",
        started_at=datetime.now(timezone.utc),
        completed_items=[],
        pending_items=[],
        extra_meta=body.extra_meta or {},
    )

    db.add(task)
    await db.commit()
    await db.refresh(task)

    logger.info(f"任务创建: task_id={task_id}, title={body.title}")

    return ok({
        "task_id": task_id,
        "user_id": task.user_id,
        "title": task.title,
        "goal": task.goal,
        "status": "pending",
        "started_at": task.started_at.isoformat() if task.started_at else None,
    }, "创建成功")


@router.get("/{task_id}", summary="查询任务")
async def task_get(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """查询单个任务"""
    result = await db.execute(
        select(Task).where(Task.task_id == task_id.strip().lower())
    )
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError(f"任务不存在: {task_id}")

    return ok({
        "task_id": task.task_id,
        "user_id": task.user_id,
        "agent_id": task.agent_id,
        "scene_id": task.scene_id,
        "session_id": task.session_id,
        "title": task.title,
        "goal": task.goal,
        "status": task.status,
        "progress": task.progress,
        "completed_items": task.completed_items or [],
        "pending_items": task.pending_items or [],
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "ended_at": task.ended_at.isoformat() if task.ended_at else None,
    })


@router.get("", summary="任务列表")
async def task_list(
    status: str | None = Query(None),
    session_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
    user_id: str = Depends(get_current_user_id),
):
    """分页查询任务列表（user 从 X-User-Id header 派生，不客户端传参）"""
    query = select(Task)

    if user_id:
        query = query.where(Task.user_id == user_id)
    if status:
        query = query.where(Task.status == status)
    if session_id:
        query = query.where(Task.session_id == session_id.strip().lower())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(Task.started_at.desc()).offset(offset).limit(page_size)
    tasks = (await db.execute(query)).scalars().all()

    items = []
    for t in tasks:
        items.append({
            "task_id": t.task_id,
            "user_id": t.user_id,
            "title": t.title,
            "goal": t.goal,
            "status": t.status,
            "progress": t.progress,
            "completed_items": t.completed_items or [],
            "pending_items": t.pending_items or [],
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "ended_at": t.ended_at.isoformat() if t.ended_at else None,
        })

    return ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.put("/{task_id}", summary="更新任务进展")
async def task_update(
    task_id: str,
    body: TaskUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """
    更新任务进展。

    前端每轮对话后可调用此接口更新：
    - status: pending → in_progress → completed
    - progress: 当前进展描述文本
    - completed_items / pending_items: 完成/待办清单
    """
    result = await db.execute(
        select(Task).where(Task.task_id == task_id.strip().lower())
    )
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError(f"任务不存在: {task_id}")

    if body.title is not None:
        task.title = body.title
    if body.goal is not None:
        task.goal = body.goal
    if body.status is not None:
        _validate_status_transition(task.status, body.status)
        task.status = body.status
        if body.status == "completed":
            task.ended_at = datetime.now(timezone.utc)
    if body.progress is not None:
        task.progress = body.progress
    if body.completed_items is not None:
        task.completed_items = body.completed_items
    if body.pending_items is not None:
        task.pending_items = body.pending_items
    if body.extra_meta is not None:
        task.extra_meta = body.extra_meta

    await db.commit()
    logger.info(f"任务更新: task_id={task_id}, status={task.status}")

    return ok({"task_id": task_id, "updated": True, "status": task.status}, "更新成功")


@router.get("/{task_id}/progress", summary="任务进展摘要")
async def task_progress(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """
    查询任务进展摘要。

    返回：completed_count, pending_count, related_memory_count
    — 前端用此展示"该任务已积累多少记忆"
    """
    result = await db.execute(
        select(Task).where(Task.task_id == task_id.strip().lower())
    )
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError(f"任务不存在: {task_id}")

    # 统计关联记忆数
    mem_count_result = await db.execute(
        select(func.count()).where(
            Memory.task_id == task_id.strip().lower(),
            Memory.status == "active",
        )
    )
    related_memory_count = mem_count_result.scalar() or 0

    return ok({
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.progress,
        "completed_count": len(task.completed_items or []),
        "pending_count": len(task.pending_items or []),
        "related_memory_count": related_memory_count,
        "last_activity": task.ended_at.isoformat() if task.ended_at else (
            task.started_at.isoformat() if task.started_at else None
        ),
    })


@router.post("/{task_id}/complete", summary="完成任务")
async def task_complete(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """标记任务为已完成"""
    result = await db.execute(
        select(Task).where(Task.task_id == task_id.strip().lower())
    )
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError(f"任务不存在: {task_id}")

    task.status = "completed"
    task.ended_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(f"任务完成: task_id={task_id}")

    return ok({
        "task_id": task_id,
        "status": "completed",
        "ended_at": task.ended_at.isoformat(),
    }, "任务已完成")
