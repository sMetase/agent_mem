# -*- coding: utf-8 -*-
"""全局默认 LLM 配置 API。"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.crypto import encrypt_secret
from app.core.logger import get_logger
from app.models.base import LlmConfig
from app.schemas.common import ok

logger = get_logger("config_api")
router = APIRouter()


class LlmConfigRequest(BaseModel):
    llm_model: Optional[str] = Field(None, max_length=128, description="全局默认 LLM 模型")
    llm_api_key: Optional[str] = Field(None, max_length=256, description="全局默认 LLM API Key")


@router.get("/llm", summary="读取全局默认 LLM 配置")
async def get_llm_config(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LlmConfig).order_by(LlmConfig.id).limit(1))
    cfg = result.scalar_one_or_none()
    return ok({
        "llm_model": cfg.llm_model if cfg else None,
        "has_api_key": bool(cfg.llm_api_key) if cfg else False,
    })


@router.put("/llm", summary="更新全局默认 LLM 配置")
async def put_llm_config(body: LlmConfigRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LlmConfig).order_by(LlmConfig.id).limit(1))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = LlmConfig(llm_model=body.llm_model, llm_api_key=encrypt_secret(body.llm_api_key))
        db.add(cfg)
    else:
        if body.llm_model is not None:
            cfg.llm_model = body.llm_model
        if body.llm_api_key is not None:
            cfg.llm_api_key = encrypt_secret(body.llm_api_key)
    await db.commit()
    return ok({"updated": True}, "全局默认 LLM 配置已更新")
