# -*- coding: utf-8 -*-
"""
Memory Pipeline — 完整记忆生成流水线编排器。

协调整个流程：
  extract → generate → dedup → store

将原始对话文本转化为持久化的结构化记忆，自动处理去重与融合。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MemoryGenerationError
from app.core.logger import get_logger
from app.core.qdrant_client import QdrantClientSingleton, qdrant_client as _qdrant_singleton
from app.models.base import Memory, MemoryRelation
from app.services.embedding_client import EmbeddingClient, embedding_client as _embedding_singleton
from app.services.llm_client import LLMClient, llm_client as _llm_singleton
from app.services.memory_dedup import (
    DedupAction,
    DedupResult,
    DedupService,
)
from app.services.memory_extractor import ExtractionResult, MemoryExtractor
from app.services.memory_generator import MemoryCandidate, MemoryGenerator
from app.services.memory_quality import (
    QualityReport,
    verify_candidates_batch,
    QualityAuditor,
)

logger = get_logger("memory_pipeline")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_id(prefix: str = "mem") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


# ============================================================
# 流水线结果
# ============================================================

@dataclass
class PipelineResult:
    """单次流水线执行结果"""
    memory_ids: list[str] = field(default_factory=list)
    new_count: int = 0
    merged_count: int = 0
    discarded_count: int = 0
    updated_count: int = 0
    conflict_count: int = 0
    details: list[dict] = field(default_factory=list)


@dataclass
class GenerationDetail:
    """单条记忆生成详情"""
    action: str
    memory_id: Optional[str]
    content_preview: str
    memory_type: str
    importance: float
    confidence: float
    message: str = ""


# ============================================================
# Memory Pipeline
# ============================================================

class MemoryPipeline:
    """
    记忆生成流水线编排器。

    用法:
        pipeline = MemoryPipeline()
        result = await pipeline.run(
            text="对话内容...",
            user_id="user_123",
            agent_id="agent_001",
            db=db_session,
        )

    去重参数可配置：
        - dedup_weights: (vector_weight, keyword_weight, identity_weight)
        - dedup_thresholds: (discard, update_existing_with_identity, merge_min)
    """

    # 可配置的去重默认参数
    DEDUP_WEIGHTS = (0.5, 0.3, 0.2)       # vector, keyword, identity
    DEDUP_THRESHOLDS = (0.90, 0.80, 0.65)  # discard, update(需identity), merge
    LLM_AUDIT_ENABLED = True                # 是否启用 LLM 深度审计

    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        embedding: Optional[EmbeddingClient] = None,
        qdrant: Optional[QdrantClientSingleton] = None,
        dedup_weights: Optional[tuple[float, float, float]] = None,
        dedup_thresholds: Optional[tuple[float, float, float]] = None,
        enable_llm_audit: Optional[bool] = None,
    ) -> None:
        self._llm = llm
        self._embedding = embedding
        self._qdrant = qdrant
        self.dedup_weights = dedup_weights or self.DEDUP_WEIGHTS
        self.dedup_thresholds = dedup_thresholds or self.DEDUP_THRESHOLDS
        self.enable_llm_audit = enable_llm_audit if enable_llm_audit is not None else self.LLM_AUDIT_ENABLED

        # 惰性初始化的子服务
        self._extractor: Optional[MemoryExtractor] = None
        self._generator: Optional[MemoryGenerator] = None
        self._dedup: Optional[DedupService] = None

    # ---- 属性 ----

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = _llm_singleton
        return self._llm

    @property
    def embedding(self) -> EmbeddingClient:
        if self._embedding is None:
            self._embedding = _embedding_singleton
        return self._embedding

    @property
    def qdrant(self) -> QdrantClientSingleton:
        if self._qdrant is None:
            self._qdrant = _qdrant_singleton
        return self._qdrant

    def _ensure_initialized(self) -> None:
        """惰性初始化所有子服务。"""
        if self._extractor is None:
            self._extractor = MemoryExtractor(self.llm)
        if self._generator is None:
            self._generator = MemoryGenerator(self.llm)
        if self._dedup is None:
            vw, kw, iw = self.dedup_weights
            self._dedup = DedupService(
                self.embedding, self.qdrant,
                vector_weight=vw, keyword_weight=kw, identity_weight=iw,
            )

    # ---- 主流程 ----

    async def run(
        self,
        text: str,
        user_id: str,
        agent_id: Optional[str] = None,
        scene_id: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        source_record_ids: Optional[list[str]] = None,
        task_context: Optional[dict] = None,
        db: Optional[AsyncSession] = None,
    ) -> PipelineResult:
        """
        执行完整记忆生成流水线：extract → generate → dedup → store。

        Args:
            text: 原始对话文本
            user_id: 用户标识（必填）
            agent_id: 智能体标识
            scene_id: 场景标识
            session_id: 会话标识
            task_id: 任务标识
            source_record_ids: 来源记录 ID 列表
            task_context: 任务上下文（用于任务状态抽取）
            db: 数据库会话（如果提供则自动存储）

        Returns:
            PipelineResult

        Raises:
            MemoryGenerationError: 流水线执行失败
        """
        self._ensure_initialized()

        result = PipelineResult()

        # ========== Phase 1: Extract ==========
        logger.info(f"Pipeline Phase 1/4: Extracting from {len(text)} chars of text")
        try:
            extraction_result: ExtractionResult = await self._extractor.extract(
                text=text,
                task_context=task_context,
            )
        except Exception as e:
            raise MemoryGenerationError(f"记忆抽取阶段失败: {str(e)}")

        if extraction_result.is_empty():
            logger.info("Extraction produced no results, pipeline complete")
            return result

        # ========== Phase 2: Generate ==========
        logger.info("Pipeline Phase 2/4: Generating structured memories")
        try:
            candidates: list[MemoryCandidate] = await self._generator.generate(extraction_result)
        except Exception as e:
            raise MemoryGenerationError(f"记忆生成阶段失败: {str(e)}")

        if not candidates:
            logger.info("No memory candidates generated, pipeline complete")
            return result

        # ========== Phase 2.5: Quality Verification ==========
        logger.info(f"Pipeline Phase 2.5/4: Verifying quality of {len(candidates)} candidates")
        quality_reports: list[QualityReport] = verify_candidates_batch(
            candidates, source_text=text
        )

        # LLM 深度审计：对高重要性候选记忆启用（如果 LLM 可用）
        high_importance_candidates = [
            (i, c) for i, c in enumerate(candidates) if c.importance >= 0.7
        ]
        if high_importance_candidates and self.llm and self.enable_llm_audit:
            try:
                auditor = QualityAuditor(self.llm)
                logger.info(
                    f"LLM deep audit: {len(high_importance_candidates)}/{len(candidates)} "
                    f"high-importance candidates"
                )
                hi_candidates = [c for _, c in high_importance_candidates]
                llm_reports = await auditor.audit(hi_candidates, source_text=text)
                # 用 LLM 审计结果覆盖规则引擎结果
                for (idx, _), llm_report in zip(high_importance_candidates, llm_reports):
                    quality_reports[idx] = llm_report
            except Exception as e:
                logger.warning(f"LLM deep audit failed, keeping rule-based results: {e}")

        # 为每个 candidate 附加质量报告（用于后续存储）
        candidate_quality_map: dict[int, QualityReport] = {
            i: qr for i, qr in enumerate(quality_reports)
        }

        # 统计质量
        active_count = sum(1 for qr in quality_reports if qr.suggested_status == "active")
        pending_count = sum(1 for qr in quality_reports if qr.suggested_status == "pending")
        logger.info(
            f"Quality verification complete: "
            f"active={active_count}, pending={pending_count}, "
            f"avg_score={sum(qr.quality_score for qr in quality_reports) / max(len(quality_reports), 1):.2f}"
        )

        # ========== Phase 3: Dedup ==========
        logger.info(f"Pipeline Phase 3/4: Deduplicating {len(candidates)} candidates")
        if db is not None and self.qdrant.is_available:
            try:
                dedup_results: list[DedupResult] = await self._dedup.process_candidates(
                    candidates=candidates,
                    user_id=user_id,
                    db=db,
                    task_id=task_id,
                    session_id=session_id,
                )
            except Exception as e:
                logger.warning(f"Dedup failed, treating all as KEEP_NEW: {e}")
                dedup_results = [
                    DedupResult(
                        action=DedupAction.KEEP_NEW,
                        content=c.content,
                        summary=c.summary,
                        key_points=c.key_points,
                        memory_type=c.memory_type,
                        tags=c.tags,
                        entities=c.entities,
                        importance=c.importance,
                        confidence=c.confidence,
                        message="去重失败，保留新记忆",
                    )
                    for c in candidates
                ]
        else:
            # 无 DB 或无 Qdrant → 全部保留
            dedup_results = [
                DedupResult(
                    action=DedupAction.KEEP_NEW,
                    content=c.content,
                    summary=c.summary,
                    key_points=c.key_points,
                    memory_type=c.memory_type,
                    tags=c.tags,
                    entities=c.entities,
                    importance=c.importance,
                    confidence=c.confidence,
                    message="无 DB 连接，保留新记忆",
                )
                for c in candidates
            ]

        # ========== Phase 4: Store ==========
        logger.info("Pipeline Phase 4/4: Storing memories")
        if db is not None:
            await self._store_results(
                dedup_results=dedup_results,
                user_id=user_id,
                agent_id=agent_id,
                scene_id=scene_id,
                session_id=session_id,
                task_id=task_id,
                source_record_ids=source_record_ids,
                db=db,
                candidate_quality_map=candidate_quality_map,
            )

        # 汇总结果
        for dr in dedup_results:
            detail = {
                "action": dr.action.value,
                "memory_id": dr.memory_id,
                "content_preview": dr.content[:100],
                "memory_type": dr.memory_type,
                "importance": dr.importance,
                "confidence": dr.confidence,
                "message": dr.message,
            }
            result.details.append(detail)

            if dr.action == DedupAction.KEEP_NEW:
                result.new_count += 1
                if dr.memory_id:
                    result.memory_ids.append(dr.memory_id)
            elif dr.action == DedupAction.MERGE:
                result.merged_count += 1
                if dr.memory_id:
                    result.memory_ids.append(dr.memory_id)
            elif dr.action == DedupAction.UPDATE_EXISTING:
                result.updated_count += 1
                if dr.memory_id:
                    result.memory_ids.append(dr.memory_id)
            elif dr.action == DedupAction.DISCARD:
                result.discarded_count += 1

        logger.info(
            f"Pipeline complete: new={result.new_count}, merged={result.merged_count}, "
            f"updated={result.updated_count}, discarded={result.discarded_count}"
        )
        return result

    async def run_batch(
        self,
        texts: list[str],
        user_id: str,
        agent_id: Optional[str] = None,
        scene_id: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        source_record_ids: Optional[list[str]] = None,
        task_context: Optional[dict] = None,
        db: Optional[AsyncSession] = None,
    ) -> list[PipelineResult]:
        """
        批量执行记忆生成流水线。

        Args:
            texts: 文本列表（最多 50 条）
            其余参数同 run()

        Returns:
            PipelineResult 列表
        """
        results: list[PipelineResult] = []
        for text in texts:
            result = await self.run(
                text=text,
                user_id=user_id,
                agent_id=agent_id,
                scene_id=scene_id,
                session_id=session_id,
                task_id=task_id,
                source_record_ids=source_record_ids,
                task_context=task_context,
                db=db,
            )
            results.append(result)
        return results

    # ---- 存储逻辑 ----

    async def _store_results(
        self,
        dedup_results: list[DedupResult],
        user_id: str,
        db: AsyncSession,
        agent_id: Optional[str] = None,
        scene_id: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        source_record_ids: Optional[list[str]] = None,
        candidate_quality_map: Optional[dict[int, "QualityReport"]] = None,
    ) -> None:
        """将去重结果持久化到 PostgreSQL 和向量存储。"""
        for i, dr in enumerate(dedup_results):
            if dr.action == DedupAction.DISCARD:
                continue

            # 获取该条记忆的质量报告
            qr = (candidate_quality_map or {}).get(i)
            status = qr.suggested_status if qr else "active"
            quality_score = qr.quality_score if qr else 0.5

            if dr.action == DedupAction.KEEP_NEW:
                # 新建记忆（走 create_memory 类型感知写入）
                from app.services.memory_service import create_memory
                memory_id = dr.memory_id or _gen_id("mem")
                dr.memory_id = memory_id

                memory = await create_memory(db, {
                    "memory_id": memory_id,
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "scene_id": scene_id,
                    "session_id": session_id,
                    "task_id": task_id,
                    "content": dr.content,
                    "summary": dr.summary,
                    "key_points": dr.key_points,
                    "memory_type": dr.memory_type,
                    "tags": dr.tags,
                    "entities": dr.entities,
                    "status": status,
                    "importance": dr.importance,
                    "confidence": dr.confidence,
                    "source_type": "extracted",
                    "source_record_ids": source_record_ids or [],
                    "version": 1,
                })
                await db.flush()

                # 向量化 + 写入（vector_store 抽象，无桥接表）
                try:
                    from app.services.vector_store import vector_store
                    vector = await self.embedding.embed_single(dr.content)
                    await vector_store.insert(
                        memory_id=memory_id,
                        vector=vector,
                        metadata={
                            "user_id": user_id,
                            "scene_id": scene_id or "",
                            "task_id": task_id or "",
                            "session_id": session_id or "",
                        },
                        content=dr.content,
                    )
                except Exception as e:
                    logger.warning(f"vector write failed for {memory_id}: {e}")

            elif dr.action in (DedupAction.MERGE, DedupAction.UPDATE_EXISTING):
                # 更新已有记忆
                memory_id = dr.memory_id
                if not memory_id:
                    continue

                try:
                    from sqlalchemy import select as _select
                    result = await db.execute(
                        _select(Memory).where(Memory.memory_id == memory_id)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        old_version = existing.version or 1

                        # 快照旧版本到历史表
                        from app.services.memory_service import snapshot_memory_history
                        snapshot_memory_history(db, existing, dr.action.value)

                        existing.content = dr.content
                        existing.summary = dr.summary
                        existing.key_points = dr.key_points
                        existing.tags = dr.tags
                        existing.entities = dr.entities
                        existing.importance = dr.importance
                        existing.confidence = dr.confidence
                        existing.version = old_version + 1
                        existing.updated_at = _now()

                        # 更新向量（vector_store 抽象，无桥接表）
                        try:
                            from app.services.vector_store import vector_store
                            vector = await self.embedding.embed_single(dr.content)
                            await vector_store.insert(
                                memory_id=memory_id,
                                vector=vector,
                                metadata={
                                    "user_id": user_id,
                                    "scene_id": scene_id or "",
                                    "task_id": task_id or "",
                                    "session_id": session_id or "",
                                },
                                content=dr.content,
                            )
                        except Exception as e:
                            logger.warning(f"vector update failed for {memory_id}: {e}")
                    else:
                        logger.warning(f"Memory {memory_id} not found for MERGE/UPDATE")
                except Exception as e:
                    logger.error(f"Failed to update memory {memory_id}: {e}")

        # 提交数据库
        try:
            await db.commit()
            logger.info(f"DB committed: {len(dedup_results)} dedup results")
        except Exception as e:
            logger.error(f"DB commit failed: {e}")
            await db.rollback()
            raise MemoryGenerationError(f"记忆存储失败: {str(e)}")


# 模块级单例
memory_pipeline = MemoryPipeline()
