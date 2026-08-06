# -*- coding: utf-8 -*-
"""
Memory Dedup Service — 多阶段记忆去重与融合引擎。

去重算法流程：
  1. 向量相似度检索（Qdrant 语义搜索）
  2. 数据库加载完整候选记忆
  3. 关键词重合计算（Jaccard 系数）
  4. 标识一致性判断（task_id + session_id + entities 重叠）
  5. 冲突检测（偏好变化 / 任务约束调整 / 事实更新）
  6. 综合评分决策（DISCARD / MERGE / UPDATE_EXISTING / CONFLICT / KEEP_NEW）
  7. 融合执行（合并内容、要点、实体，建立版本关系）
  8. 审计记录（写入 DedupAudit 表）

新增功能（v2）：
  - CONFLICT 决策动作：无法自动判断时保留双方，标记冲突
  - 会话级标识校验（session_id）
  - 冲突检测：偏好变化、任务约束调整、事实更新
  - 融合审计追踪（DedupAudit 表）
  - 版本管理与替代关系（replaced_by + MemoryRelation）
  - 动态权重调整（高频确认提升权重，过期降权）
"""

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.core.qdrant_client import QdrantClientSingleton
from app.models.base import Memory, MemoryRelation, DedupAudit
from app.services.embedding_client import EmbeddingClient
from app.services.memory_generator import MemoryCandidate

logger = get_logger("memory_dedup")

_audit_id_prefix = "audit"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_audit_id() -> str:
    return f"{_audit_id_prefix}_{uuid.uuid4().hex[:16]}"


class DedupAction(str, Enum):
    KEEP_NEW = "keep_new"
    MERGE = "merge"
    DISCARD = "discard"
    UPDATE_EXISTING = "update_existing"
    CONFLICT = "conflict"  # 新增：无法自动判断，保留双方并标记冲突


@dataclass
class SimilarMemory:
    """与候选记忆相似的已有记忆"""
    memory_id: str
    content: str
    vector_score: float           # 余弦相似度 (0-1)
    keyword_overlap: float        # Jaccard 系数 (0-1)
    identity_match: bool          # 是否同一实体/任务/会话


@dataclass
class DedupResult:
    """去重决策结果"""
    action: DedupAction
    memory_id: Optional[str] = None       # 分配或已有的 memory_id
    content: str = ""                     # 最终内容（合并后）
    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    memory_type: str = "fact"
    tags: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    importance: float = 0.5
    confidence: float = 0.5
    merged_from: list[str] = field(default_factory=list)  # 合并来源的 memory_ids
    replaced_by: Optional[str] = None     # 替代关系（旧记忆 → 新记忆）
    conflict_with: list[str] = field(default_factory=list)  # 冲突记忆 IDs
    message: str = ""
    # 审计信息
    audit: Optional[dict] = None          # 审计记录数据


class DedupService:
    """
    多阶段记忆去重引擎（v2）。

    对每个候选记忆执行：
      vector → DB load → keyword calc → identity check → conflict detection → composite decision → merge → audit
    """

    def __init__(
        self,
        embedding_client: EmbeddingClient,
        qdrant: QdrantClientSingleton,
        vector_weight: float = 0.5,
        keyword_weight: float = 0.3,
        identity_weight: float = 0.2,
    ) -> None:
        self._embedding = embedding_client
        self._qdrant = qdrant
        self._vec_w = vector_weight
        self._kw_w = keyword_weight
        self._id_w = identity_weight

    async def process_candidates(
        self,
        candidates: list[MemoryCandidate],
        user_id: str,
        db: AsyncSession,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        similarity_threshold: float = 0.85,
        keyword_threshold: float = 0.5,
    ) -> list[DedupResult]:
        """
        对候选记忆列表逐一执行去重决策。

        Args:
            candidates: 待处理的记忆候选
            user_id: 用户标识
            db: 数据库会话
            task_id: 当前任务 ID
            session_id: 当前会话 ID（v2 新增）
            similarity_threshold: 向量相似度阈值
            keyword_threshold: 关键词重合阈值

        Returns:
            DedupResult 列表
        """
        if not self._qdrant.is_available:
            logger.warning("Qdrant unavailable, skipping dedup — all candidates KEEP_NEW")
            return [
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
                    message="Qdrant 不可用，跳过去重",
                )
                for c in candidates
            ]

        results: list[DedupResult] = []

        for candidate in candidates:
            result = await self._process_single(
                candidate=candidate,
                user_id=user_id,
                db=db,
                task_id=task_id,
                session_id=session_id,
                similarity_threshold=similarity_threshold,
                keyword_threshold=keyword_threshold,
            )
            results.append(result)

        # 写入审计记录
        await self._write_audit_trail(results, user_id, task_id, session_id, db)

        # 动态调整权重
        await self._adjust_weights(results, db)

        actions = {
            a: sum(1 for r in results if r.action == a)
            for a in DedupAction
        }
        logger.info(f"Dedup complete: {len(candidates)} candidates → {actions}")
        return results

    async def _process_single(
        self,
        candidate: MemoryCandidate,
        user_id: str,
        db: AsyncSession,
        task_id: Optional[str],
        session_id: Optional[str],
        similarity_threshold: float,
        keyword_threshold: float,
    ) -> DedupResult:
        """对单个候选记忆执行完整去重流程。"""

        # Stage 1: 向量相似度检索
        try:
            query_vector = await self._embedding.embed_single(candidate.content)
            hits = self._qdrant.search_similar(
                query_vector=query_vector,
                user_id=user_id,
                top_k=8,
                score_threshold=0.65,
            )
        except Exception as e:
            logger.warning(f"Vector search failed for dedup: {e}")
            return self._make_keep_new(candidate, "向量检索失败，默认保留")

        if not hits:
            # 无重复：正常完成去重且确认无相似记忆 → 记录审计作为一次 completed keep_new
            return self._make_keep_new(candidate, "无相似向量匹配", audit_data={
                "candidate_content": candidate.content[:500],
                "candidate_memory_type": candidate.memory_type,
                "matched_memory_id": None,
                "matched_content": None,
                "vector_score": None,
                "keyword_overlap": None,
                "identity_match": False,
                "composite_score": None,
            })

        # Stage 2: 从 PostgreSQL 加载完整记忆
        # 注意：Qdrant point id 是 _str_to_uuid(memory_id) 转换后的 UUID，
        # 与 DB 的 memory_id（mem_xxx）不同，必须用 payload.memory_id 关联
        hit_id_map = {}  # memory_id → score
        for h in hits:
            mem_id = (h.get("payload") or {}).get("memory_id") or str(h["id"])
            hit_id_map[mem_id] = h["score"]

        existing_memories: list[Memory] = []
        try:
            result = await db.execute(
                select(Memory).where(
                    Memory.memory_id.in_(list(hit_id_map.keys())),
                    Memory.status.in_(["active", "pending"]),  # 仅匹配活跃/待验证记忆
                )
            )
            existing_memories = list(result.scalars().all())
        except Exception as e:
            logger.warning(f"DB load failed for dedup: {e}")
            return self._make_keep_new(candidate, "数据库加载失败，保留新记忆")

        if not existing_memories:
            return self._make_keep_new(candidate, "无匹配数据库记录")

        # 为每个已有记忆计算相似度
        similar_memories: list[SimilarMemory] = []
        hit_score_map = hit_id_map

        for existing in existing_memories:
            vector_score = hit_score_map.get(existing.memory_id, 0.0)
            keyword_overlap = self._compute_keyword_overlap(candidate, existing)
            # 安全网：向量明确相似但分词失败 → 设置底线，不让关键词分拖垮 composite
            if vector_score > 0.85 and keyword_overlap < 0.15:
                keyword_overlap = 0.15
            identity_match = self._check_identity(
                candidate, existing, task_id, session_id
            )

            similar_memories.append(
                SimilarMemory(
                    memory_id=existing.memory_id,
                    content=existing.content or "",
                    vector_score=vector_score,
                    keyword_overlap=keyword_overlap,
                    identity_match=identity_match,
                )
            )

        # 找最佳匹配
        best = max(similar_memories, key=lambda s: s.vector_score)

        # Stage 3-4: 综合决策（含冲突检测）
        action = self._decide_action(
            vector_score=best.vector_score,
            keyword_overlap=best.keyword_overlap,
            identity_match=best.identity_match,
            similarity_threshold=similarity_threshold,
            keyword_threshold=keyword_threshold,
            candidate=candidate,
            best_match=best,
            existing_memories=existing_memories,
        )

        # 构建审计数据
        audit_data = {
            "candidate_content": candidate.content[:500],
            "candidate_memory_type": candidate.memory_type,
            "matched_memory_id": best.memory_id,
            "matched_content": best.content[:500],
            "vector_score": best.vector_score,
            "keyword_overlap": best.keyword_overlap,
            "identity_match": best.identity_match,
            "composite_score": (
                0.5 * best.vector_score + 0.3 * best.keyword_overlap
                + 0.2 * (1.0 if best.identity_match else 0.0)
            ),
        }

        # Stage 5: 执行对应的处理
        if action == DedupAction.DISCARD:
            return DedupResult(
                action=DedupAction.DISCARD,
                memory_id=best.memory_id,
                content=candidate.content,
                summary=candidate.summary,
                key_points=candidate.key_points,
                memory_type=candidate.memory_type,
                tags=candidate.tags,
                entities=candidate.entities,
                importance=candidate.importance,
                confidence=candidate.confidence,
                message=f"与现有记忆 {best.memory_id} 高度重复 (vec={best.vector_score:.3f}, kw={best.keyword_overlap:.3f})",
                audit=audit_data,
            )

        elif action == DedupAction.UPDATE_EXISTING:
            # 获取已有记忆以建立替代关系
            existing = next(
                (e for e in existing_memories if e.memory_id == best.memory_id), None
            )
            old_version = existing.version if existing else 1
            audit_data["before_content"] = existing.content[:500] if existing else ""
            audit_data["old_version"] = old_version
            audit_data["new_version"] = old_version + 1

            return DedupResult(
                action=DedupAction.UPDATE_EXISTING,
                memory_id=best.memory_id,
                content=candidate.content,
                summary=candidate.summary,
                key_points=candidate.key_points,
                memory_type=candidate.memory_type,
                tags=list(set(candidate.tags)),
                entities=list(set(candidate.entities)),
                importance=max(candidate.importance, 0.5),
                confidence=max(candidate.confidence, 0.5),
                replaced_by=candidate.content,  # 新内容
                message=f"更新现有记忆 {best.memory_id} (identity match, version {old_version}→{old_version + 1})",
                audit=audit_data,
            )

        elif action == DedupAction.MERGE:
            existing = next(
                (e for e in existing_memories if e.memory_id == best.memory_id), None
            )
            if existing:
                merged = self._merge_content(candidate, existing)
                audit_data["before_content"] = existing.content[:500] if existing else ""
                audit_data["after_content"] = merged["content"][:500]

                return DedupResult(
                    action=DedupAction.MERGE,
                    memory_id=best.memory_id,
                    content=merged["content"],
                    summary=merged["summary"],
                    key_points=merged["key_points"],
                    memory_type=candidate.memory_type,
                    tags=merged["tags"],
                    entities=merged["entities"],
                    importance=merged["importance"],
                    confidence=merged["confidence"],
                    merged_from=[best.memory_id],
                    message=f"合并到现有记忆 {best.memory_id} (vec={best.vector_score:.3f})",
                    audit=audit_data,
                )
            else:
                return self._make_keep_new(candidate, "合并目标不可用，保留新记忆")

        elif action == DedupAction.CONFLICT:
            # 新旧记忆存在冲突但无法自动判断
            existing = next(
                (e for e in existing_memories if e.memory_id == best.memory_id), None
            )
            audit_data["before_content"] = existing.content[:500] if existing else ""
            return DedupResult(
                action=DedupAction.CONFLICT,
                memory_id=None,  # 新记忆会分配新 ID
                content=candidate.content,
                summary=candidate.summary,
                key_points=candidate.key_points,
                memory_type=candidate.memory_type,
                tags=["conflict"] + candidate.tags,
                entities=candidate.entities,
                importance=candidate.importance,
                confidence=0.3,  # 冲突状态降低置信度
                conflict_with=[best.memory_id],
                message=f"与现有记忆 {best.memory_id} 存在潜在冲突，保留双方并标记 (vec={best.vector_score:.3f})",
                audit=audit_data,
            )

        else:  # KEEP_NEW
            return self._make_keep_new(
                candidate, "无匹配，保留新记忆", audit_data
            )

    # ---------- 关键词 ----------

    def _compute_keyword_overlap(
        self,
        candidate: MemoryCandidate,
        existing: Memory,
    ) -> float:
        """计算关键词 Jaccard 系数。"""
        candidate_keywords = set(
            [t.lower() for t in candidate.tags]
            + [e.lower() for e in candidate.entities]
            + self._extract_nouns(candidate.content)
        )
        existing_keywords = set(
            [t.lower() for t in (existing.tags or [])]
            + [e.lower() for e in (existing.entities or [])]
            + self._extract_nouns(existing.content or "")
        )

        if not candidate_keywords or not existing_keywords:
            return 0.0

        intersection = candidate_keywords & existing_keywords
        union = candidate_keywords | existing_keywords
        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def _extract_nouns(text: str) -> list[str]:
        """中英文关键词提取：中文 bigram/trigram + 英文技术术语。

        中文使用字符 bigram + trigram 而非滑动窗口切词，
        避免相同语义不同表述产生完全不重叠的关键词集合。
        """
        # 英文：包含连字符、数字、下划线的技术术语（如 kube-version, semver, api_v2）
        english = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{2,}", text)

        # 中文：字符 bigram + trigram（覆盖 2-3 字词，比原滑动窗口鲁棒得多）
        chinese_chars = re.findall(r"[一-鿿]", text)
        bigrams = {
            chinese_chars[i] + chinese_chars[i + 1]
            for i in range(len(chinese_chars) - 1)
        }
        trigrams = {
            chinese_chars[i] + chinese_chars[i + 1] + chinese_chars[i + 2]
            for i in range(len(chinese_chars) - 2)
        }

        keywords = english + list(bigrams | trigrams)
        seen: set[str] = set()
        unique: list[str] = []
        for kw in keywords:
            low = kw.lower()
            if low not in seen:
                seen.add(low)
                unique.append(low)
        return unique[:30]

    # ---------- 标识校验（v2 增强：含 session_id）----------

    def _check_identity(
        self,
        candidate: MemoryCandidate,
        existing: Memory,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """判断候选记忆与已有记忆是否指向同一实体/任务/会话。"""
        # 条件 1: 相同 task_id → 强匹配
        if task_id and existing.task_id == task_id:
            return True

        # 条件 2: entities 重叠 >= 2 → 强匹配（指向同一实体对象）
        candidate_entities = set(e.lower() for e in candidate.entities)
        existing_entities = set(e.lower() for e in (existing.entities or []))
        entity_overlap = candidate_entities & existing_entities
        if len(entity_overlap) >= 2:
            return True

        # 条件 3: 相同 session_id + entities 重叠 >= 1 → 弱匹配
        if session_id and existing.session_id == session_id and len(entity_overlap) >= 1:
            return True

        return False

    # ---------- 冲突检测（v2 新增）----------

    def _detect_conflict(
        self,
        candidate: MemoryCandidate,
        existing: Memory,
        best: SimilarMemory,
    ) -> tuple[bool, str]:
        """
        检测候选记忆与已有记忆之间是否存在冲突。

        检测三种冲突类型：
        1. 偏好变化：同一偏好对象，新偏好与旧偏好不一致
        2. 任务约束调整：同一任务，新约束与旧约束矛盾
        3. 事实更新：同一实体/事实，新旧描述相互矛盾

        Returns:
            (is_conflict, conflict_reason)
        """
        # 仅在高相似度但不完全相同时检测冲突
        if best.vector_score < 0.75:
            return False, ""

        # 类型一致性检查
        candidate_type = candidate.memory_type
        existing_type = existing.memory_type or "fact"

        # 同一类型的新旧记忆，内容语义高度相似但表述不同 → 可能冲突
        if candidate_type == existing_type:
            # 偏好变化检测
            if candidate_type == "preference":
                # 使用简单否定词检测
                negation_words = ["不再", "不要", "改为", "换成", "替代", "替换", "instead", "rather", "prefer not"]
                has_negation = any(w in candidate.content.lower() for w in negation_words)
                has_old_content = len(existing.content or "") > 20

                if has_negation and has_old_content and best.vector_score >= 0.75:
                    return True, "检测到偏好变化: 新表述包含否定/替代词，可能取代旧偏好"

            # 任务约束调整检测
            if candidate_type == "constraint":
                severity_words = ["必须", "严禁", "不能", "要求", "must", "required", "cannot"]
                if any(w in candidate.content.lower() for w in severity_words) and best.vector_score >= 0.80:
                    return True, "检测到任务约束调整: 新旧约束均包含强制性表述，可能存在冲突"

            # 事实更新检测（版本号/时间标记）
            if candidate_type == "fact":
                # 如果已有记忆较旧且有新信息出现
                if existing.updated_at and best.vector_score >= 0.85:
                    # 检查是否有时间更新标记
                    time_words = ["更新", "最新", "现在", "目前", "current", "latest", "updated", "now"]
                    if any(w in candidate.content.lower() for w in time_words):
                        return True, "检测到事实可能更新: 新旧表述相近但新内容包含时间更新标记"

        return False, ""

    # ---------- 综合决策（v2：含 CONFLICT）----------

    def _decide_action(
        self,
        vector_score: float,
        keyword_overlap: float,
        identity_match: bool,
        similarity_threshold: float = 0.85,
        keyword_threshold: float = 0.5,
        candidate: Optional[MemoryCandidate] = None,
        best_match: Optional[SimilarMemory] = None,
        existing_memories: Optional[list[Memory]] = None,
    ) -> DedupAction:
        """
        串行门控去重决策 — 对齐设计文档 5.2.3。

        第一步：相似度匹配（向量）
          vector_score >= 0.85 → 进入下一步；否则 KEEP_NEW

        第二步：结构化匹配（关键词 + 记忆类型）
          keyword_overlap >= 0.5 + memory_type 一致 → 进入候选集；否则 KEEP_NEW

        第三步：标识校验（user_id / session_id / task_id / entities）
          identity_match = True （同 user + (同 session 或 同 task 或 entities ≥ 2)）→ 进入融合；否则 KEEP_NEW

        第四步：融合决策
          vector >= 0.95 + keyword >= 0.70 + identity → 重复，不写入 (DISCARD)
          vector >= 0.85 + keyword >= 0.50 + identity → 补充信息 (MERGE)
          冲突检测通过 → 覆盖更新 (UPDATE_EXISTING)
          冲突无法自动判断 → 标记冲突 (CONFLICT)
        """
        # ===== 第一步：相似度匹配 =====
        if vector_score < similarity_threshold:
            return DedupAction.KEEP_NEW

        # ===== 第二步：结构化匹配（关键词 + 类型） =====
        if keyword_overlap < keyword_threshold:
            return DedupAction.KEEP_NEW

        if candidate and best_match and existing_memories:
            existing = next(
                (e for e in existing_memories if e.memory_id == best_match.memory_id),
                None,
            )
            if existing and existing.memory_type != candidate.memory_type:
                return DedupAction.KEEP_NEW

        # ===== 第三步：标识校验 =====
        if not identity_match:
            return DedupAction.KEEP_NEW

        # ===== 第四步：融合决策 =====
        # 冲突检测
        is_conflict = False
        conflict_reason = ""
        if candidate and best_match and existing_memories:
            existing = next(
                (e for e in existing_memories if e.memory_id == best_match.memory_id),
                None,
            )
            if existing:
                is_conflict, conflict_reason = self._detect_conflict(
                    candidate, existing, best_match
                )

        if is_conflict:
            logger.info(f"Conflict detected: {conflict_reason}")
            return DedupAction.CONFLICT

        if vector_score >= 0.95 and keyword_overlap >= 0.70:
            return DedupAction.DISCARD

        if vector_score >= 0.85 and keyword_overlap >= 0.50:
            return DedupAction.MERGE

        if vector_score >= 0.78:
            return DedupAction.UPDATE_EXISTING

        return DedupAction.MERGE

    # ---------- 内容合并 ----------

    def _merge_content(
        self,
        candidate: MemoryCandidate,
        existing: Memory,
    ) -> dict:
        """合并候选记忆与已有记忆。"""
        existing_kps = existing.key_points or []
        all_kps = existing_kps + [
            kp for kp in candidate.key_points if kp not in existing_kps
        ]

        existing_entities = existing.entities or []
        all_entities = list(set(
            [e.lower() for e in existing_entities]
            + [e.lower() for e in candidate.entities]
        ))

        existing_tags = existing.tags or []
        all_tags = list(set(existing_tags + candidate.tags))

        merged_content = existing.content or ""
        if candidate.content not in merged_content:
            merged_content = f"{merged_content}\n[更新: {candidate.summary}]"

        existing_importance = float(existing.importance or 0.5)
        existing_confidence = float(existing.confidence or 0.5)

        return {
            "content": merged_content.strip(),
            "summary": (existing.summary or "") + f" | 更新: {candidate.summary}",
            "key_points": all_kps,
            "tags": all_tags,
            "entities": all_entities,
            "importance": max(candidate.importance, existing_importance),
            "confidence": max(candidate.confidence, existing_confidence),
        }

    def _make_keep_new(
        self,
        candidate: MemoryCandidate,
        message: str,
        audit_data: Optional[dict] = None,
    ) -> DedupResult:
        """构造 KEEP_NEW 结果。"""
        return DedupResult(
            action=DedupAction.KEEP_NEW,
            content=candidate.content,
            summary=candidate.summary,
            key_points=candidate.key_points,
            memory_type=candidate.memory_type,
            tags=candidate.tags,
            entities=candidate.entities,
            importance=candidate.importance,
            confidence=candidate.confidence,
            message=message,
            audit=audit_data,
        )

    # ---------- 审计追踪（v2 新增）----------

    async def _write_audit_trail(
        self,
        results: list[DedupResult],
        user_id: str,
        task_id: Optional[str],
        session_id: Optional[str],
        db: AsyncSession,
    ) -> None:
        """将去重决策结果写入审计表。"""
        audit_records = []

        for dr in results:
            if dr.audit is None:
                continue

            audit_record = DedupAudit(
                audit_id=_gen_audit_id(),
                candidate_content=dr.audit.get("candidate_content", "")[:500],
                candidate_memory_type=dr.audit.get("candidate_memory_type"),
                matched_memory_id=dr.audit.get("matched_memory_id"),
                matched_content=dr.audit.get("matched_content", ""),
                vector_score=dr.audit.get("vector_score"),
                keyword_overlap=dr.audit.get("keyword_overlap"),
                identity_match=dr.audit.get("identity_match", False),
                composite_score=dr.audit.get("composite_score"),
                action=dr.action.value,
                before_content=dr.audit.get("before_content"),
                after_content=dr.audit.get("after_content"),
                old_status="active",
                new_status="pending" if dr.action == DedupAction.CONFLICT else "active",
                old_version=dr.audit.get("old_version"),
                new_version=dr.audit.get("new_version"),
                user_id=user_id,
                task_id=task_id,
                session_id=session_id,
                message=dr.message[:500],
            )
            audit_records.append(audit_record)

        if audit_records:
            try:
                for record in audit_records:
                    db.add(record)
                await db.commit()
                logger.info(f"Audit trail: {len(audit_records)} records written")
            except Exception as e:
                logger.warning(f"Failed to write audit trail: {e}")
                await db.rollback()

    # ---------- 动态权重调整（v2 新增）----------

    async def _adjust_weights(
        self,
        results: list[DedupResult],
        db: AsyncSession,
    ) -> None:
        """
        根据去重结果动态调整已有记忆的权重。

        规则：
        - 被 MERGE/UPDATE 的记忆：importance += 0.05, confidence += 0.05
        - 被 DISCARD 的新记忆：已有记忆 use_count += 1, last_used_at 更新
        - 被 CONFLICT 涉及的旧记忆：confidence -= 0.1
        - 长期未使用的记忆：decay_factor *= 0.9
        """
        for dr in results:
            if dr.action in (DedupAction.MERGE, DedupAction.UPDATE_EXISTING):
                # 提升被更新记忆的权重
                memory_id = dr.memory_id or (dr.merged_from[0] if dr.merged_from else None)
                if memory_id:
                    try:
                        result = await db.execute(
                            select(Memory).where(Memory.memory_id == memory_id)
                        )
                        existing = result.scalar_one_or_none()
                        if existing:
                            existing.importance = min(1.0, float(existing.importance or 0.5) + 0.05)
                            existing.confidence = min(1.0, float(existing.confidence or 0.5) + 0.05)
                            existing.use_count = (existing.use_count or 0) + 1
                            existing.last_used_at = _now()
                            existing.decay_factor = min(1.0, float(existing.decay_factor or 1.0) + 0.02)
                            logger.debug(f"Weight boosted: {memory_id} imp={existing.importance:.2f}")
                    except Exception as e:
                        logger.warning(f"Failed to adjust weight for {memory_id}: {e}")

            elif dr.action == DedupAction.DISCARD:
                # 被判定为重复，提升已有记忆的使用计数
                memory_id = dr.memory_id
                if memory_id:
                    try:
                        result = await db.execute(
                            select(Memory).where(Memory.memory_id == memory_id)
                        )
                        existing = result.scalar_one_or_none()
                        if existing:
                            existing.use_count = (existing.use_count or 0) + 1
                            existing.last_used_at = _now()
                    except Exception as e:
                        logger.warning(f"Failed to update use_count for {memory_id}: {e}")

            elif dr.action == DedupAction.CONFLICT:
                # 冲突涉及的旧记忆降低置信度
                for conflict_id in dr.conflict_with:
                    try:
                        result = await db.execute(
                            select(Memory).where(Memory.memory_id == conflict_id)
                        )
                        existing = result.scalar_one_or_none()
                        if existing:
                            existing.confidence = max(0.1, float(existing.confidence or 0.5) - 0.1)
                            existing.decay_factor = max(0.1, float(existing.decay_factor or 1.0) - 0.05)
                            logger.debug(f"Confidence reduced for conflict: {conflict_id}")
                    except Exception as e:
                        logger.warning(f"Failed to adjust confidence for {conflict_id}: {e}")

        try:
            await db.commit()
        except Exception as e:
            logger.warning(f"Failed to commit weight adjustments: {e}")
            await db.rollback()
