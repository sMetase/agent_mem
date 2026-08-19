# -*- coding: utf-8 -*-
"""
长对话压缩 + 上下文补全 — API 端点（Section 5.4）。

注：generate 系列接口（/generate、/generate/batch、/generate/async、/generate/{id}/status）
已于 2026-08-19 废弃。记忆生成统一走 /memory/write 异步链路（L0 → L1 worker）。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel as PydanticBaseModel, Field as PydanticField
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_agent
from app.core.database import get_db
from app.core.logger import get_logger
from app.models.base import Memory
from app.schemas.common import ok

logger = get_logger("generation_api")

router = APIRouter()


# ============================================================
# POST /memory/compress — 长对话压缩 (Section 5.4.1)
# ============================================================

class CompressRequest(PydanticBaseModel):
    text: str = PydanticField(..., description="长对话文本")
    validate_preservation: bool = PydanticField(True, description="是否验证关键信息保留")


class CompressResponse(PydanticBaseModel):
    conversation_overview: str
    key_facts_count: int
    preferences_count: int
    decisions_count: int
    corrections_count: int
    original_length: int
    compressed_length: int
    compression_ratio: float
    preservation_score: float
    compact_text: str


@router.post("/compress", summary="压缩长对话为结构化记忆 (Section 5.4)")
async def memory_compress(body: CompressRequest, _agent: str = Depends(get_current_agent)):
    """压缩长对话历史，保留关键事实/偏好/任务状态/决策/修正记录。"""
    from app.services.memory_compressor import get_compressor

    compressor = get_compressor()
    compressed = await compressor.compress_and_validate(
        body.text,
        validate_preservation=body.validate_preservation,
    )

    return ok(CompressResponse(
        conversation_overview=compressed.conversation_overview,
        key_facts_count=len(compressed.key_facts),
        preferences_count=len(compressed.user_preferences),
        decisions_count=len(compressed.key_decisions),
        corrections_count=len(compressed.corrections_and_feedback),
        original_length=compressed.original_length,
        compressed_length=compressed.compressed_length,
        compression_ratio=compressed.compression_ratio,
        preservation_score=compressed.preservation_score,
        compact_text=compressed.to_compact_text(),
    ).model_dump())


# ============================================================
# POST /memory/context/complete — 历史上下文补全 (Section 5.4.3)
# ============================================================

class ContextCompleteRequest(PydanticBaseModel):
    query: str = PydanticField(..., description="当前用户查询")
    memory_ids: list[str] = PydanticField(..., description="相关历史记忆 ID 列表")
    max_context_tokens: int = PydanticField(3000, description="最大上下文 token 数")


class ContextCompleteResponse(PydanticBaseModel):
    context_text: str
    sections_used: list[str]
    estimated_relevance: float


@router.post("/context/complete", summary="基于历史压缩记忆补全上下文 (Section 5.4.3)")
async def memory_context_complete(
    body: ContextCompleteRequest,
    db: AsyncSession = Depends(get_db),
    _agent: str = Depends(get_current_agent),
):
    """从已存储的压缩记忆中检索并补全当前查询所需的历史上下文。"""
    from app.services.memory_compressor import get_compressor
    from sqlalchemy import select as _select

    # 从 DB 加载记忆
    memories_data = []
    for mid in body.memory_ids:
        result = await db.execute(_select(Memory).where(Memory.memory_id == mid))
        mem = result.scalar_one_or_none()
        if mem:
            memories_data.append({
                "id": mem.memory_id,
                "content": mem.content,
                "summary": mem.summary or "",
                "memory_type": mem.memory_type,
            })

    if not memories_data:
        return ok(ContextCompleteResponse(
            context_text="",
            sections_used=[],
            estimated_relevance=0.0,
        ).model_dump())

    # 构建压缩记忆对象
    from app.services.memory_compressor import CompressedMemory
    compressed_list = []
    for md in memories_data:
        cm = CompressedMemory(
            conversation_overview=md["summary"],
            key_facts=[{"fact": md["content"], "category": "background", "importance": 0.5}],
            important_context=[md["content"]],
        )
        compressed_list.append(cm)

    compressor = get_compressor()
    result = await compressor.complete_context(
        query=body.query,
        compressed_memories=compressed_list,
        max_context_tokens=body.max_context_tokens,
    )

    return ok(ContextCompleteResponse(
        context_text=result["context_text"],
        sections_used=result["sections_used"],
        estimated_relevance=result["estimated_relevance"],
    ).model_dump())
