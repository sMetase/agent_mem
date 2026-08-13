# -*- coding: utf-8 -*-
"""
智能体管理 API — 6 个接口，全部实现真实 DB 操作。

负责：
- 注册智能体（生成 API Key，只返回一次明文）
- 查询/列表/更新/停用智能体
- API Key 轮换（旧 Key 立即失效）
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_agent
from app.core.database import get_db
from app.core.exceptions import NotFoundError, ConflictError, AuthenticationError
from app.core.logger import get_logger
from app.core.security import generate_agent_id, generate_api_key, hash_api_key
from app.models.base import Agent
from app.schemas.agent import (
    AgentRegisterRequest,
    AgentRegisterResponse,
    AgentUpdateRequest,
    AgentInfo,
    ApiKeyRotateResponse,
)
from app.schemas.common import ok, paginated

logger = get_logger("agent_api")
router = APIRouter()


@router.post("/register", summary="注册智能体", status_code=201)
async def agent_register(body: AgentRegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    注册新智能体。

    1. 生成 agent_id 和 api_key
    2. 数据库中只存储 api_key_hash (SHA256)
    3. 返回一次性的 api_key 明文（仅此一次，请妥善保存）
    """
    agent_id = generate_agent_id()
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)

    # 校验 scene_id 是否存在
    from app.models.base import Scene
    scene_result = await db.execute(
        select(Scene).where(Scene.scene_id == body.scene_id, Scene.is_active == True)
    )
    if not scene_result.scalar_one_or_none():
        raise NotFoundError(f"场景不存在或已停用: {body.scene_id}")

    # 检查 agent_id 冲突（几乎不可能，但做防御）
    existing = await db.execute(
        select(Agent).where(Agent.agent_id == agent_id)
    )
    if existing.scalar_one_or_none():
        raise ConflictError(f"智能体 ID 冲突，请重试: {agent_id}")

    agent = Agent(
        agent_id=agent_id,
        agent_name=body.agent_name,
        scene_id=body.scene_id,
        api_key_hash=api_key_hash,
        api_key_prefix="mem_" + api_key[4:8] + "****",
        is_active=True,
        permissions=body.permissions,
    )

    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    logger.info(f"智能体注册成功: agent_id={agent_id}, agent_name={body.agent_name}")

    return ok({
        "agent_id": agent_id,
        "agent_name": body.agent_name,
        "api_key": api_key,  # ← 仅此一次返回明文
        "api_key_prefix": agent.api_key_prefix,
        "scene_id": body.scene_id,
        "is_active": True,
        "created_at": agent.created_at.isoformat(),
    }, "注册成功 — API Key 仅显示一次，请妥善保存")


@router.get("/{agent_id}", summary="查询智能体")
async def agent_get(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _current: str = Depends(get_current_agent),
):
    """查询单个智能体信息（不含 API Key）"""
    result = await db.execute(
        select(Agent).where(Agent.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise NotFoundError(f"智能体不存在: {agent_id}")

    return ok({
        "agent_id": agent.agent_id,
        "agent_name": agent.agent_name,
        "scene_id": agent.scene_id,
        "api_key_prefix": agent.api_key_prefix,
        "is_active": agent.is_active,
        "permissions": agent.permissions,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    })


@router.get("", summary="智能体列表")
async def agent_list(
    scene_id: str | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current: str = Depends(get_current_agent),
):
    """分页查询智能体列表"""
    query = select(Agent)

    if scene_id:
        query = query.where(Agent.scene_id == scene_id)
    if is_active is not None:
        query = query.where(Agent.is_active == is_active)

    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页
    offset = (page - 1) * page_size
    query = query.order_by(Agent.created_at.desc()).offset(offset).limit(page_size)
    agents = (await db.execute(query)).scalars().all()

    items = []
    for a in agents:
        items.append({
            "agent_id": a.agent_id,
            "agent_name": a.agent_name,
            "scene_id": a.scene_id,
            "api_key_prefix": a.api_key_prefix,
            "is_active": a.is_active,
            "permissions": a.permissions,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        })

    return ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.put("/{agent_id}", summary="更新智能体")
async def agent_update(
    agent_id: str,
    body: AgentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _current: str = Depends(get_current_agent),
):
    """更新智能体信息（名称、权限、启用/停用）"""
    result = await db.execute(
        select(Agent).where(Agent.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise NotFoundError(f"智能体不存在: {agent_id}")

    if body.agent_name is not None:
        agent.agent_name = body.agent_name
    if body.is_active is not None:
        agent.is_active = body.is_active
    if body.permissions is not None:
        agent.permissions = body.permissions
    if body.extra_meta is not None:
        agent.extra_meta = body.extra_meta

    await db.commit()
    logger.info(f"智能体更新成功: agent_id={agent_id}")

    return ok({"agent_id": agent_id, "updated": True}, "更新成功")


@router.delete("/{agent_id}", summary="停用智能体")
async def agent_disable(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _current: str = Depends(get_current_agent),
):
    """停用智能体（软删除，不删除记录）"""
    result = await db.execute(
        select(Agent).where(Agent.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise NotFoundError(f"智能体不存在: {agent_id}")

    agent.is_active = False
    await db.commit()
    logger.info(f"智能体已停用: agent_id={agent_id}")

    return ok({"agent_id": agent_id, "is_active": False}, "已停用")


@router.post("/{agent_id}/rotate-key", summary="轮换 API Key")
async def agent_rotate_key(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _current: str = Depends(get_current_agent),
):
    """
    轮换 API Key — 旧 Key 立即失效，返回新 Key 明文。

    安全要求：
    - 旧 API Key 哈希被覆盖，即刻失效
    - 新 API Key 只在本次响应中返回明文
    """
    result = await db.execute(
        select(Agent).where(Agent.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise NotFoundError(f"智能体不存在: {agent_id}")

    new_api_key = generate_api_key()
    new_hash = hash_api_key(new_api_key)

    agent.api_key_hash = new_hash
    agent.api_key_prefix = "mem_" + new_api_key[4:8] + "****"
    await db.commit()

    logger.info(f"API Key 已轮换: agent_id={agent_id}")

    return ok({
        "agent_id": agent_id,
        "api_key": new_api_key,  # ← 仅此一次返回明文
        "api_key_prefix": agent.api_key_prefix,
    }, "轮换成功 — 新 API Key 仅显示一次，旧 Key 已失效")
