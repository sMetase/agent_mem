# -*- coding: utf-8 -*-
"""
场景管理 API — 5 个接口，全部实现真实 DB 操作。

场景（Scene）是租户隔离的第二维度（Agent → Scene → Data）。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_agent
from app.core.database import get_db
from app.core.exceptions import NotFoundError, ConflictError
from app.core.logger import get_logger
from app.core.security import generate_scene_id
from app.models.base import Scene
from app.schemas.common import ok
from app.schemas.scene import SceneCreateRequest, SceneUpdateRequest

logger = get_logger("scene_api")
router = APIRouter()


@router.post("", summary="创建场景", status_code=201)
async def scene_create(
    body: SceneCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """创建新场景（接入前置，无需鉴权——开启 AUTH_ENABLED 后避免 bootstrap 死锁）"""
    scene_id = generate_scene_id()

    scene = Scene(
        scene_id=scene_id,
        scene_name=body.scene_name,
        description=body.description,
        is_active=True,
        extra_meta=body.extra_meta or {},
    )

    db.add(scene)
    await db.commit()
    await db.refresh(scene)

    logger.info(f"场景创建成功: scene_id={scene_id}, scene_name={body.scene_name}")

    return ok({
        "scene_id": scene_id,
        "scene_name": body.scene_name,
        "description": body.description,
        "is_active": True,
        "created_at": scene.created_at.isoformat() if scene.created_at else None,
    }, "创建成功")


@router.get("/{scene_id}", summary="查询场景")
async def scene_get(
    scene_id: str,
    db: AsyncSession = Depends(get_db),
    _current: str = Depends(get_current_agent),
):
    """查询单个场景信息"""
    result = await db.execute(
        select(Scene).where(Scene.scene_id == scene_id)
    )
    scene = result.scalar_one_or_none()
    if not scene:
        raise NotFoundError(f"场景不存在: {scene_id}")

    return ok({
        "scene_id": scene.scene_id,
        "scene_name": scene.scene_name,
        "description": scene.description,
        "is_active": scene.is_active,
        "created_at": scene.created_at.isoformat() if scene.created_at else None,
        "updated_at": scene.updated_at.isoformat() if scene.updated_at else None,
    })


@router.get("", summary="场景列表")
async def scene_list(
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current: str = Depends(get_current_agent),
):
    """分页查询场景列表"""
    query = select(Scene)

    if is_active is not None:
        query = query.where(Scene.is_active == is_active)

    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页
    offset = (page - 1) * page_size
    query = query.order_by(Scene.created_at.desc()).offset(offset).limit(page_size)
    scenes = (await db.execute(query)).scalars().all()

    items = []
    for s in scenes:
        items.append({
            "scene_id": s.scene_id,
            "scene_name": s.scene_name,
            "description": s.description,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })

    return ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.put("/{scene_id}", summary="更新场景")
async def scene_update(
    scene_id: str,
    body: SceneUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _current: str = Depends(get_current_agent),
):
    """更新场景信息"""
    result = await db.execute(
        select(Scene).where(Scene.scene_id == scene_id)
    )
    scene = result.scalar_one_or_none()
    if not scene:
        raise NotFoundError(f"场景不存在: {scene_id}")

    if body.scene_name is not None:
        scene.scene_name = body.scene_name
    if body.description is not None:
        scene.description = body.description
    if body.is_active is not None:
        scene.is_active = body.is_active
    if body.extra_meta is not None:
        scene.extra_meta = body.extra_meta

    await db.commit()
    logger.info(f"场景更新成功: scene_id={scene_id}")

    return ok({"scene_id": scene_id, "updated": True}, "更新成功")


@router.delete("/{scene_id}", summary="停用场景")
async def scene_disable(
    scene_id: str,
    db: AsyncSession = Depends(get_db),
    _current: str = Depends(get_current_agent),
):
    """停用场景（软删除）"""
    result = await db.execute(
        select(Scene).where(Scene.scene_id == scene_id)
    )
    scene = result.scalar_one_or_none()
    if not scene:
        raise NotFoundError(f"场景不存在: {scene_id}")

    scene.is_active = False
    await db.commit()
    logger.info(f"场景已停用: scene_id={scene_id}")

    return ok({"scene_id": scene_id, "is_active": False}, "已停用")
