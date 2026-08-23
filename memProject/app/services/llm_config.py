# -*- coding: utf-8 -*-
"""LLM 配置解析：agent 级 > 全局默认(t_llm_config) > .env（LLMClient 兜底）。"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret
from app.core.logger import get_logger

logger = get_logger("llm_config")


async def resolve_llm_config(
    db: AsyncSession,
    agent_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """返回 (llm_model, llm_api_key)，两者都可能为 None（表示回退 .env 默认）。

    agent_id 提供时优先取 agent 级配置；agent 未配置或未提供 agent_id 时回退全局默认 t_llm_config。
    """
    from sqlalchemy import select

    from app.models.base import Agent, LlmConfig

    model: Optional[str] = None
    api_key: Optional[str] = None

    try:
        if agent_id:
            agent_result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
            agent = agent_result.scalar_one_or_none()
            if agent:
                model = agent.llm_model
                api_key = decrypt_secret(agent.llm_api_key)

        if not model or not api_key:
            cfg_result = await db.execute(select(LlmConfig).order_by(LlmConfig.id).limit(1))
            cfg = cfg_result.scalar_one_or_none()
            if cfg:
                model = model or cfg.llm_model
                api_key = api_key or decrypt_secret(cfg.llm_api_key)
    except Exception as e:
        logger.warning(f"查 LLM 配置失败，回退 .env 默认: {e}")

    return model, api_key
