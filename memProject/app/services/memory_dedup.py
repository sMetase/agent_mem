# -*- coding: utf-8 -*-
"""
Memory Dedup Service — 单层记忆去重与融合引擎（v3）。

去重算法流程：
  1. 为每个候选并行搜相似记忆（Qdrant，扩大候选范围）
  2. LLM 批量判断动作 + 输出「局部整合」后的内容
  3. 应用决策（含审计 + 动态权重调整）

动作语义：
  - keep_new:        全新信息，新建记忆
  - discard:         与已有记忆高度重复，不写入
  - merge:           补充信息 → 局部合并（保留旧内容，自然融入新信息）
  - update_existing: 纠正/矛盾取值 → 局部纠错（最新为准，只改矛盾取值，旧值入历史）

注意：本模块已合并原 preference/fact 的类型专属去重。偏好「同主题替换」、
事实「矛盾取值纠正」等类型规则已揉进 LLM 批量判断的 prompt 中。
"""

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.core.qdrant_client import QdrantClientSingleton
from app.models.base import Memory, DedupAudit
from app.services.embedding_client import EmbeddingClient
from app.services.llm_config import resolve_llm_config
from app.services.memory_generator import MemoryCandidate

logger = get_logger("memory_dedup")

_audit_id_prefix = "audit"

# 去重候选搜索范围（合并两套去重后扩大，覆盖原 preference/fact 的穷举搜索）
_SIMILAR_TOP_K = 50
_SIMILAR_SCORE_THRESHOLD = 0.5
# 给 LLM 看的相似记忆条数（截断）
_LLM_TOP_MATCHES = 5
# 旧内容给 LLM 时的截断长度（局部整合需完整旧内容，仅防超长）
_LLM_CONTENT_MAX = 2000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_audit_id() -> str:
    return f"{_audit_id_prefix}_{uuid.uuid4().hex[:16]}"


class DedupAction(str, Enum):
    KEEP_NEW = "keep_new"
    MERGE = "merge"
    DISCARD = "discard"
    UPDATE_EXISTING = "update_existing"


@dataclass
class DedupResult:
    """去重决策结果"""
    action: DedupAction
    memory_id: Optional[str] = None       # 目标 memory_id（merge/update/discard 时指向已有记忆）
    content: str = ""                     # 最终内容（整合后）
    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    memory_type: str = "fact"
    tags: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    importance: float = 0.5
    confidence: float = 0.5
    merged_from: list[str] = field(default_factory=list)  # 合并来源 memory_ids
    message: str = ""
    audit: Optional[dict] = None          # 审计记录数据


class DedupService:
    """单层记忆去重引擎（v3）。"""

    def __init__(
        self,
        embedding_client: EmbeddingClient,
        qdrant: QdrantClientSingleton,
        vector_weight: float = 0.5,
        keyword_weight: float = 0.3,
        identity_weight: float = 0.2,
    ) -> None:
        # 权重参数保留仅为向后兼容（v3 单层去重已不再使用关键词/标识权重）
        self._embedding = embedding_client
        self._qdrant = qdrant

    async def process_candidates(
        self,
        candidates: list[MemoryCandidate],
        user_id: str,
        db: AsyncSession,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        similarity_threshold: float = _SIMILAR_SCORE_THRESHOLD,
        keyword_threshold: float = 0.5,
    ) -> list[DedupResult]:
        """
        对候选记忆列表逐一执行去重决策。

        Returns:
            DedupResult 列表
        """
        if not self._qdrant.is_available:
            logger.warning("Qdrant unavailable, skipping dedup — all candidates KEEP_NEW")
            return [self._make_keep_new(c, "Qdrant 不可用，跳过去重") for c in candidates]

        results: list[DedupResult] = []

        # ── Step 1: 为所有候选并行搜相似记忆 ──
        candidate_matches: list[dict] = []
        for candidate in candidates:
            matches = await self._find_similar(
                candidate=candidate, user_id=user_id, db=db,
                task_id=task_id, session_id=session_id,
                similarity_threshold=similarity_threshold,
            )
            candidate_matches.append({"candidate": candidate, "similar": matches})

        # ── Step 2: LLM 批量判断（动作 + 局部整合后内容）──
        model, api_key = await resolve_llm_config(db, agent_id=None)
        llm_decisions = await self._llm_dedup_batch(candidate_matches, model=model, api_key=api_key)

        # ── Step 3: 应用决策 ──
        for i, cm in enumerate(candidate_matches):
            candidate = cm["candidate"]
            best_match = cm["similar"][0] if cm["similar"] else None
            best_memory = best_match.get("memory") if best_match else None

            decision = llm_decisions.get(i)
            if decision:
                action = decision.get("action", DedupAction.KEEP_NEW)
                llm_content = (decision.get("content") or "").strip()
            else:
                # LLM 未返回决策 → 机械兜底（基于向量分数）
                if best_match:
                    score = best_match.get("vector_score", 0.0)
                    if score >= 0.95:
                        action = DedupAction.DISCARD
                    elif score >= 0.7:
                        action = DedupAction.MERGE
                    else:
                        action = DedupAction.KEEP_NEW
                else:
                    action = DedupAction.KEEP_NEW
                llm_content = ""

            if action == DedupAction.KEEP_NEW:
                results.append(self._make_keep_new(
                    candidate, "LLM判定无匹配",
                    audit_data=self._build_audit(candidate, None, None),
                ))

            elif action == DedupAction.DISCARD and best_match:
                dr = DedupResult(
                    action=DedupAction.DISCARD,
                    memory_id=best_match["memory_id"],
                    content=candidate.content,
                    summary=candidate.summary,
                    key_points=candidate.key_points,
                    memory_type=candidate.memory_type,
                    tags=candidate.tags,
                    entities=candidate.entities,
                    importance=candidate.importance,
                    confidence=candidate.confidence,
                    message=f"LLM判定与 {best_match['memory_id']} 重复",
                )
                dr.audit = self._build_audit(candidate, best_match, best_memory)
                results.append(dr)

            elif action == DedupAction.MERGE and best_match and best_memory:
                # 局部合并：优先用 LLM 整合结果，失败退回机械追加
                merged = self._merge_content(candidate, best_memory)
                content = llm_content or merged["content"]
                dr = DedupResult(
                    action=DedupAction.MERGE,
                    memory_id=best_match["memory_id"],
                    content=content,
                    summary=merged["summary"],
                    key_points=merged["key_points"],
                    memory_type=candidate.memory_type,
                    tags=merged["tags"],
                    entities=merged["entities"],
                    importance=max(candidate.importance, float(best_memory.importance or 0.5)),
                    confidence=max(candidate.confidence, float(best_memory.confidence or 0.5)),
                    merged_from=[best_match["memory_id"]],
                    message=f"LLM判定与 {best_match['memory_id']} 合并",
                )
                dr.audit = self._build_audit(candidate, best_match, best_memory, after_content=content)
                results.append(dr)

            elif action == DedupAction.UPDATE_EXISTING and best_match:
                # 局部纠错：优先用 LLM 纠正结果，失败退回整条覆盖
                content = llm_content or candidate.content
                dr = DedupResult(
                    action=DedupAction.UPDATE_EXISTING,
                    memory_id=best_match["memory_id"],
                    content=content,
                    summary=candidate.summary,
                    key_points=candidate.key_points,
                    memory_type=candidate.memory_type,
                    tags=list(set(candidate.tags)),
                    entities=list(set(candidate.entities)),
                    importance=max(candidate.importance, 0.5),
                    confidence=max(candidate.confidence, 0.5),
                    message=f"LLM判定覆盖 {best_match['memory_id']}",
                )
                dr.audit = self._build_audit(candidate, best_match, best_memory, after_content=content)
                results.append(dr)

            else:
                results.append(self._make_keep_new(
                    candidate, "无匹配",
                    audit_data=self._build_audit(candidate, None, None),
                ))

        # 写入审计记录
        await self._write_audit_trail(results, user_id, task_id, session_id, db)

        # 动态调整权重
        await self._adjust_weights(results, db)

        actions = {a: sum(1 for r in results if r.action == a) for a in DedupAction}
        logger.info(f"Dedup complete: {len(candidates)} candidates → {actions}")
        return results

    # ── 为单个候选找相似记忆 ──

    async def _find_similar(
        self,
        candidate: MemoryCandidate,
        user_id: str,
        db: AsyncSession,
        task_id: Optional[str],
        session_id: Optional[str],
        similarity_threshold: float,
    ) -> list[dict]:
        """为单个候选记忆查找相似记忆，返回 [{memory_id, content, memory_type, vector_score, memory}]"""
        try:
            from app.services.vector_store import vector_store
            query_vector = await self._embedding.embed_single(candidate.content)
            hits = await vector_store.search(
                query_vector=query_vector, user_id=user_id,
                top_k=_SIMILAR_TOP_K, score_threshold=similarity_threshold,
            )
        except Exception:
            return []

        if not hits:
            return []

        # vector_store 已返回 memory_id，无需桥接表
        mid_scores = {h["memory_id"]: h["score"] for h in hits}
        mem_result = await db.execute(
            select(Memory).where(
                Memory.memory_id.in_(list(mid_scores.keys())),
                Memory.status.in_(["active", "pending"]),
            )
        )
        existing = {m.memory_id: m for m in mem_result.scalars().all()}

        matches = []
        for mid, score in mid_scores.items():
            mem = existing.get(mid)
            if mem:
                matches.append({
                    "memory_id": mid,
                    "content": mem.content or "",
                    "memory_type": mem.memory_type or "fact",
                    "vector_score": score,
                    "memory": mem,
                })
        matches.sort(key=lambda x: x["vector_score"], reverse=True)
        return matches[:10]

    # ── LLM 批量去重判断（含类型规则 + 局部整合）──

    async def _llm_dedup_batch(
        self,
        candidate_matches: list[dict],
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> dict[int, dict]:
        """
        一次 LLM 调用判断所有候选与其相似记忆的关系，并输出局部整合后的内容。
        返回 {candidate_index: {"action": DedupAction, "content": str}}
        """
        has_matches = [(i, cm) for i, cm in enumerate(candidate_matches) if cm["similar"]]

        if not has_matches:
            return {}

        lines = []
        for idx, cm in has_matches:
            c = cm["candidate"]
            lines.append(f"[候选{idx}] type={c.memory_type}, content=\"{c.content[:_LLM_CONTENT_MAX]}\"")
            for j, m in enumerate(cm["similar"][:_LLM_TOP_MATCHES]):
                lines.append(
                    f"  相似{j + 1}: [{m['memory_id']}] type={m['memory_type']}, "
                    f"score={m['vector_score']:.3f}, content=\"{m['content'][:_LLM_CONTENT_MAX]}\""
                )

        prompt = (
            "你是记忆去重系统，负责判断一条「新候选记忆」与「已有相似记忆」的关系，并决定如何处理。\n\n"
            "## 任务\n"
            "对每条候选记忆，输出一个 JSON 对象：key 为候选编号(整数)，value 为 {\"action\": 动作, \"content\": 整合后的内容}。只输出 JSON，不要额外解释。\n\n"
            "## 四种动作（请仔细区分含义）\n\n"
            "1. keep_new（新增）\n"
            "   含义：候选是全新信息，或与已有记忆属于「不同的事实/维度/新诉求」，应独立成条，不合并。\n"
            "   content：填候选的原始内容。\n"
            "   例：已有「用户喜欢咖啡」，候选「用户喜欢茶」——两者是不同偏好、都成立、不矛盾，应 keep_new（两条都保留）。\n\n"
            "2. merge（补充/合并）\n"
            "   含义：候选是对「同一事实」的补充细节或状态更新，让原记忆更完整，但**不改变原有事实的取值**。\n"
            "   content：填「局部合并」结果——保留旧内容，把新信息自然融入（不要机械追加一行，也不要加「[更新]」这类标记）。\n"
            "   例：已有「订单DH001退款3个工作日」，候选「用户已电话咨询退款流程」——同一订单的补充细节，应 merge。\n\n"
            "3. update_existing（纠正/覆盖更新）\n"
            "   含义：候选与已有记忆在「同一事实」上取值相反或矛盾（互相矛盾、不能同时成立）。处理原则：以最新的候选为准，旧值作废进入历史。\n"
            "   content：填「小范围更新」结果——只把矛盾的那个取值改成新值，其余无关信息（订单号、其他事实等）原样保留；**不要标注旧值**（不要写「而非之前说的3个工作日」这类话，直接干净地写新值）。\n"
            "   例：已有「退款3个工作日」，候选「退款实际是7个工作日」——同一事实取值矛盾，应 update_existing，新内容只写「7个工作日」。\n\n"
            "4. discard（重复/丢弃）\n"
            "   含义：候选的含义已被已有记忆完全覆盖、没有任何新信息。包括：①「同一含义、仅措辞不同」的重复；②候选是已有记忆「语义上的子集」（候选说的内容，已有记忆已全部包含）。\n"
            "   content：填空字符串。\n"
            "   例1：已有「用户喜欢喝咖啡」，候选「用户偏好咖啡」——同一含义、措辞不同，应 discard。\n"
            "   例2：已有「订单DH001已提交退货，退款7个工作日，用户电话咨询过」，候选「用户想退货订单DH001」——候选是已有记忆的子集、无新信息，应 discard。\n\n"
            "## 边界（如何归类）\n"
            "- 什么算「重复」：同一含义仅措辞不同，或候选是已有记忆语义上的子集（无新信息）→ discard。\n"
            "- 什么算「补充」：同一事实、新增了细节/状态、但不改变原有取值 → merge。\n"
            "- 什么算「矛盾/纠正」：同一事实、取值相反/矛盾 → update_existing（最新为准）。\n"
            "- 什么算「全新」：不同事实/维度/新诉求（如催办、新问题）→ keep_new。\n\n"
            "## 反向约束（一定不要）\n"
            "- 不要把「不同但都成立」的事实（如喜欢咖啡 vs 喜欢茶）判成矛盾，那是 keep_new。\n"
            "- update_existing 的 content 里不要出现旧值标注（不要「而非之前说的3个工作日」这种）。\n"
            "- 不要机械追加「[更新]」这类标记，要自然融入。\n\n"
            "## 候选与相似记忆\n"
            + "\n".join(lines)
            + "\n\n输出 JSON:"
        )

        try:
            from app.services.llm_client import llm_client
            result = await llm_client.chat_completion([{
                "role": "user",
                "content": prompt,
            }], max_tokens=3000, model=model, api_key=api_key)

            data = json.loads(result)
            action_map = {
                "keep_new": DedupAction.KEEP_NEW,
                "discard": DedupAction.DISCARD,
                "merge": DedupAction.MERGE,
                "update_existing": DedupAction.UPDATE_EXISTING,
            }
            decisions: dict[int, dict] = {}
            for key_str, val in data.items():
                try:
                    idx = int(key_str)
                except (ValueError, TypeError):
                    continue
                if isinstance(val, dict):
                    action_str = val.get("action", "keep_new")
                    content = val.get("content", "") or ""
                else:
                    action_str = str(val)
                    content = ""
                decisions[idx] = {
                    "action": action_map.get(action_str, DedupAction.KEEP_NEW),
                    "content": content,
                }
            return decisions
        except Exception as e:
            logger.warning(f"LLM dedup batch failed, all KEEP_NEW: {e}")
            return {}

    # ── 内容合并（LLM 失败时的机械兜底）──

    def _merge_content(
        self,
        candidate: MemoryCandidate,
        existing: Memory,
    ) -> dict:
        """机械合并兜底：旧内容 + 追加更新摘要（不丢失信息）。"""
        existing_kps = existing.key_points or []
        all_kps = existing_kps + [kp for kp in candidate.key_points if kp not in existing_kps]

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

        return {
            "content": merged_content.strip(),
            "summary": (existing.summary or "") + f" | 更新: {candidate.summary}",
            "key_points": all_kps,
            "tags": all_tags,
            "entities": all_entities,
            "importance": max(candidate.importance, float(existing.importance or 0.5)),
            "confidence": max(candidate.confidence, float(existing.confidence or 0.5)),
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

    def _build_audit(
        self,
        candidate: MemoryCandidate,
        best_match: Optional[dict],
        best_memory: Optional[Memory],
        after_content: Optional[str] = None,
    ) -> dict:
        """构建审计数据。"""
        return {
            "candidate_content": candidate.content[:500],
            "candidate_memory_type": candidate.memory_type,
            "matched_memory_id": best_match["memory_id"] if best_match else None,
            "matched_content": (best_match["content"][:500] if best_match else None),
            "vector_score": best_match["vector_score"] if best_match else None,
            "keyword_overlap": None,
            "identity_match": False,
            "composite_score": None,
            "before_content": (best_memory.content[:500] if best_memory else None),
            "after_content": (after_content[:500] if after_content else None),
            "old_version": best_memory.version if best_memory else None,
            "new_version": (best_memory.version + 1) if best_memory else None,
        }

    # ── 审计追踪 ──

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
                new_status="active",
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

    # ── 动态权重调整 ──

    async def _adjust_weights(
        self,
        results: list[DedupResult],
        db: AsyncSession,
    ) -> None:
        """根据去重结果动态调整已有记忆的权重。"""
        for dr in results:
            if dr.action in (DedupAction.MERGE, DedupAction.UPDATE_EXISTING):
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
                    except Exception as e:
                        logger.warning(f"Failed to adjust weight for {memory_id}: {e}")

            elif dr.action == DedupAction.DISCARD:
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

        try:
            await db.commit()
        except Exception as e:
            logger.warning(f"Failed to commit weight adjustments: {e}")
            await db.rollback()
