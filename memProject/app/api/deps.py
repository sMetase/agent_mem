# -*- coding: utf-8 -*-
"""
API 依赖注入 — 鉴权、租户隔离、上下文注入。

对齐前端对接文档与核心改动文档：
1. 开发阶段 AUTH_ENABLED=False 时跳过鉴权，使用默认测试 Agent
2. 生产阶段 AUTH_ENABLED=True 时强制校验 X-API-Key
3. 多租户数据隔离（强制注入 agent_id + scene_id）
"""

from typing import Optional

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.logger import get_logger
from app.core.security import decode_access_token, hash_api_key
from app.models.base import Agent, Scene

logger = get_logger("deps")
settings = get_settings()

# 开发阶段默认测试 Agent ID
DEFAULT_DEV_AGENT_ID = "agent_dev_default"
DEFAULT_DEV_SCENE_ID = "scene_dev_default"


async def get_current_agent(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    验证调用方身份，返回 agent_id。

    开发阶段 (AUTH_ENABLED=False)：
      - 跳过鉴权，使用 X-Agent-Id Header 或默认测试 Agent
      - 不查数据库，直接注入到 request.state

    生产阶段 (AUTH_ENABLED=True)：
      - API Key → SHA256 哈希 → 查 T_AGENT 表
      - 验证 is_active 状态
      - JWT 作为备选方案
    """
    # ================================================================
    # 开发阶段：跳过鉴权（对齐核心改动文档 四.2 节）
    # ================================================================
    if not settings.auth.enabled:
        # 尝试从 Header 获取 X-Agent-Id，没有则使用默认测试 Agent
        # 注意：不能用 X-API-Key 兜底——它是 api_key 值，不是 agent_id
        dev_agent = (
            request.headers.get("X-Agent-Id")
            or DEFAULT_DEV_AGENT_ID
        )
        dev_scene = request.headers.get("X-Scene-Id") or None  # 无Header时让Body生效

        request.state.agent_id = dev_agent
        request.state.scene_id = dev_scene
        request.state.auth_bypassed = True

        logger.debug(f"[DEV模式] Agent 鉴权跳过: agent_id={dev_agent}")
        return dev_agent

    # ================================================================
    # 生产阶段：强制鉴权
    # ================================================================
    if x_api_key:
        key_hash = hash_api_key(x_api_key)
        # 先查是否存在（不论激活状态）
        result = await db.execute(
            select(Agent).where(Agent.api_key_hash == key_hash)
        )
        agent = result.scalar_one_or_none()

        if not agent:
            logger.warning(f"无效的 API Key 尝试: prefix={x_api_key[:8]}...")
            raise AuthenticationError("无效的 API Key")

        if not agent.is_active:
            logger.warning(f"已停用 Agent 尝试访问: agent_id={agent.agent_id}")
            raise AuthenticationError("该智能体已被停用，请联系管理员")

        request.state.agent_id = agent.agent_id
        request.state.scene_id = agent.scene_id
        request.state.auth_bypassed = False

        logger.debug(f"Agent 鉴权通过 (API Key): agent_id={agent.agent_id}")
        return agent.agent_id

    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        agent_id = decode_access_token(token)
        if not agent_id:
            logger.warning("无效的 JWT Token")
            raise AuthenticationError("无效的 Token")

        result = await db.execute(
            select(Agent).where(
                Agent.agent_id == agent_id,
                Agent.is_active == True,
            )
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise AuthenticationError("Token 对应的智能体已停用或不存在")

        request.state.agent_id = agent_id
        request.state.scene_id = agent.scene_id  # FIX: JWT路径也注入scene_id
        request.state.auth_bypassed = False
        logger.debug(f"Agent 鉴权通过 (JWT): agent_id={agent_id}")
        return agent_id

    logger.warning("请求缺少认证凭证")
    raise AuthenticationError("缺少认证凭证 — 请提供 X-API-Key 或 Authorization: Bearer <token>")


async def get_current_user_id(request: Request) -> str:
    """
    从 Header 获取当前用户 ID。

    优先级：X-User-Id Header > 请求体中的 user_id（开发期兼容）
    """
    user_id = request.headers.get("X-User-Id")
    if user_id:
        user_id = user_id.strip().lower()
        if len(user_id) > 128:
            raise AuthenticationError("X-User-Id 长度超过限制 (128)")
        return user_id

    # 开发期兼容：如果没有 Header，返回 None，由路由层从 body 中获取
    if not settings.auth.enabled:
        logger.debug("[DEV模式] X-User-Id 未在 Header 中提供，将从请求体获取")
        return ""  # 空字符串表示"待从 body 获取"

    raise AuthenticationError("缺少 X-User-Id 请求头 — 请提供用户唯一标识")


async def get_current_scene_id(request: Request) -> Optional[str]:
    """从 Header 获取场景 ID"""
    scene_id = request.headers.get("X-Scene-Id")
    if scene_id:
        return scene_id.strip()
    return getattr(request.state, "scene_id", None)


async def get_current_session_id(request: Request) -> Optional[str]:
    """从 Header 获取会话 ID"""
    session_id = request.headers.get("X-Session-Id")
    if session_id:
        return session_id.strip().lower()
    return None


async def get_current_task_id(request: Request) -> Optional[str]:
    """从 Header 获取任务 ID"""
    task_id = request.headers.get("X-Task-Id")
    if task_id:
        return task_id.strip().lower()
    return None


async def verify_scene_access(
    scene_id: Optional[str],
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> Optional[str]:
    """验证 Agent 对 Scene 的访问权限（生产阶段有效）"""
    if not settings.auth.enabled:
        return scene_id

    if not scene_id:
        return None

    result = await db.execute(
        select(Agent).where(Agent.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise AuthenticationError("智能体不存在")

    if agent.scene_id and agent.scene_id != scene_id:
        raise AuthorizationError(
            f"智能体 {agent_id} 无权访问场景 {scene_id}，"
            f"仅限访问场景 {agent.scene_id}"
        )

    return scene_id


async def verify_data_isolation(
    request_user_id: str,
    agent_id: str,
) -> None:
    """验证数据隔离"""
    if not request_user_id or not request_user_id.strip():
        raise AuthenticationError("user_id 不能为空")


async def require_admin(
    request: Request,
    agent_id: str = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> str:
    """管理员鉴权依赖 — 仅允许管理员访问。"""
    if not settings.auth.enabled:
        return agent_id
    result = await db.execute(
        select(Agent).where(Agent.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise AuthenticationError("智能体不存在")
    permissions = agent.permissions or []
    if "admin" not in permissions:
        raise AuthorizationError("管理员权限不足")
    return agent_id


async def authorize_user_access(
    requested_user_id: str,
    agent_id: str,
    request: Request,
) -> str:
    """
    验证调用方 agent 有权访问目标 user_id 的数据。

    授权信任链：
      1. agent 已通过 X-API-Key / JWT 在 get_current_agent 中完成身份认证
      2. 生产阶段 agent 绑定 scene_id，数据隔离由 scene 维度保障
      3. 开发阶段 (AUTH_ENABLED=False)：信任 query param（与 /memory/list 一致）

    注意：本函数不依赖 X-User-Id Header（客户端可伪造）。
    完整的 agent→user 细粒度权限映射需要引入独立的授权关系表。
    """
    if not settings.auth.enabled:
        return requested_user_id

    # 生产阶段：agent 已在 get_current_agent 中完成身份认证
    # scene 级别的数据隔离由 get_current_agent 注入的 scene_id 保证
    # 此处确保 user_id 非空（空 user_id 在 query 层已被 min_length=1 拦截）
    if not requested_user_id or not requested_user_id.strip():
        raise AuthorizationError("user_id 不能为空")

    return requested_user_id
