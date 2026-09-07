# -*- coding: utf-8 -*-
"""全局默认 LLM 配置 API。"""
from datetime import time
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.crypto import encrypt_secret
from app.core.logger import get_logger
from app.core.config import get_settings, persist_generation_schedule
from app.api.deps import require_admin
from app.models.base import LlmConfig
from app.schemas.common import ok

logger = get_logger("config_api")
router = APIRouter()
settings = get_settings()


class LlmConfigRequest(BaseModel):
    llm_model: Optional[str] = Field(None, max_length=128, description="全局默认 LLM 模型")
    llm_api_key: Optional[str] = Field(None, max_length=256, description="全局默认 LLM API Key")


class ExtractionScheduleRequest(BaseModel):
    extraction_schedule_enabled: Optional[bool] = None
    extraction_window_start: Optional[str] = Field(None, description="开始时间，格式 HH:MM 或 HH:MM:SS")
    extraction_window_end: Optional[str] = Field(None, description="结束时间，格式 HH:MM 或 HH:MM:SS")
    extraction_timezone: Optional[str] = Field(None, min_length=1, max_length=64)

    @field_validator("extraction_window_start", "extraction_window_end")
    @classmethod
    def validate_window_time(cls, value: str | None) -> str | None:
        if value is not None:
            time.fromisoformat(value.strip())
        return value.strip() if value is not None else value

    @field_validator("extraction_timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value.strip())
            except ZoneInfoNotFoundError as exc:
                raise ValueError(f"不支持的时区: {value}") from exc
        return value.strip() if value is not None else value


def _extraction_schedule_data() -> dict:
    schedule = settings.generation
    return {
        "extraction_schedule_enabled": schedule.extraction_schedule_enabled,
        "extraction_window_start": schedule.extraction_window_start,
        "extraction_window_end": schedule.extraction_window_end,
        "extraction_timezone": schedule.extraction_timezone,
    }


@router.get("/extraction-schedule", summary="读取记忆抽取时间窗口")
async def get_extraction_schedule(_admin: str = Depends(require_admin)):
    return ok(_extraction_schedule_data())


@router.put("/extraction-schedule", summary="更新记忆抽取时间窗口")
async def put_extraction_schedule(
    body: ExtractionScheduleRequest,
    _admin: str = Depends(require_admin),
):
    schedule = settings.generation
    updates = body.model_dump(exclude_unset=True)
    persist_generation_schedule(updates)
    for field_name, value in updates.items():
        setattr(schedule, field_name, value)

    logger.info("L1 抽取时间窗口已通过 API 更新: %s", _extraction_schedule_data())
    return ok(_extraction_schedule_data(), "记忆抽取时间窗口已更新")


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
