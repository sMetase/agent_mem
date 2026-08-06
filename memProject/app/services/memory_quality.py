# -*- coding: utf-8 -*-
"""
Memory Quality Service — 记忆质量校验与价值判断。

在流水线中提供三个关键校验点：
  1. 抽取后价值判断：对抽取结果进行重要性/时效性/可复用性预评分
  2. 生成后准确性校验：检查结构化记忆是否忠实反映原始内容
  3. 生成后可用性校验：判断记忆是否具有后续检索/调用价值

低置信度/低质量记忆自动标记为 pending 状态。
"""

from dataclasses import dataclass, field
from typing import Optional

from app.core.logger import get_logger
from app.services.llm_client import LLMClient
from app.services.memory_generator import MemoryCandidate
from app.services.memory_extractor import ExtractionResult

logger = get_logger("memory_quality")

# ============================================================
# 质量判定结果
# ============================================================


@dataclass
class QualityReport:
    """单条记忆的质量校验报告"""
    candidate: MemoryCandidate
    is_accurate: bool = True           # 是否忠实反映原始内容
    accuracy_note: str = ""            # 准确性备注
    is_usable: bool = True             # 是否具有后续使用价值
    usability_note: str = ""           # 可用性备注
    suggested_status: str = "active"   # 建议状态: active / pending / archived
    quality_score: float = 0.5         # 综合质量分 0.0-1.0
    issues: list[str] = field(default_factory=list)


@dataclass
class ValueJudgment:
    """抽取后的价值判断"""
    importance_score: float = 0.5      # 重要性 0.0-1.0
    timeliness_score: float = 0.5      # 时效性 0.0-1.0 (越高越持久)
    reusability_score: float = 0.5     # 可复用性 0.0-1.0
    overall_value: float = 0.5         # 综合价值分
    should_keep: bool = True           # 是否值得保留
    reason: str = ""


# ============================================================
# 抽取价值判断（基于规则的预评分）
# ============================================================

EXTRACTION_TYPE_WEIGHTS = {
    # (importance, timeliness, reusability)
    "key_fact": (0.7, 0.9, 0.7),       # 事实高时效、高可复用
    "task_state": (0.8, 0.4, 0.4),     # 任务状态高重要但时效性低
    "decision": (0.8, 0.7, 0.6),       # 决策高重要、较高可复用
    "preference": (0.6, 0.8, 0.8),     # 偏好中等重要但高度可复用
    "process": (0.4, 0.5, 0.7),        # 过程中等，高可复用（经验教训）
    "feedback": (0.7, 0.6, 0.5),       # 反馈修正高重要
}


def judge_extraction_value(extraction_result: ExtractionResult) -> ValueJudgment:
    """
    对抽取结果进行基于规则的价值判断。

    综合考虑：抽取到的信息量和类型、各类型的预设权重。

    Returns:
        ValueJudgment 包含各项评分和是否保留的建议
    """
    if extraction_result.is_empty():
        return ValueJudgment(
            importance_score=0.0,
            timeliness_score=0.0,
            reusability_score=0.0,
            overall_value=0.0,
            should_keep=False,
            reason="抽取结果为空，无保留价值",
        )

    # 统计有内容的类型
    active_types = []
    if extraction_result.key_facts and not extraction_result.key_facts.is_empty():
        active_types.append("key_fact")
    if extraction_result.task_state and not extraction_result.task_state.is_empty():
        active_types.append("task_state")
    if extraction_result.preferences and not extraction_result.preferences.is_empty():
        active_types.append("preference")
    if extraction_result.process and not extraction_result.process.is_empty():
        active_types.append("process")
    if extraction_result.feedback and not extraction_result.feedback.is_empty():
        active_types.append("feedback")

    if not active_types:
        return ValueJudgment(
            overall_value=0.0,
            should_keep=False,
            reason="所有抽取类型均为空",
        )

    # 加权平均
    total_importance = 0.0
    total_timeliness = 0.0
    total_reusability = 0.0

    for t in active_types:
        w = EXTRACTION_TYPE_WEIGHTS.get(t, (0.5, 0.5, 0.5))
        total_importance += w[0]
        total_timeliness += w[1]
        total_reusability += w[2]

    n = len(active_types)
    importance = total_importance / n
    timeliness = total_timeliness / n
    reusability = total_reusability / n
    overall = 0.4 * importance + 0.3 * timeliness + 0.3 * reusability

    should_keep = overall >= 0.25

    return ValueJudgment(
        importance_score=round(importance, 2),
        timeliness_score=round(timeliness, 2),
        reusability_score=round(reusability, 2),
        overall_value=round(overall, 2),
        should_keep=should_keep,
        reason=f"活跃类型: {active_types}, 综合价值={overall:.2f}",
    )


# ============================================================
# 生成后质量校验
# ============================================================

def verify_candidate_quality(
    candidate: MemoryCandidate,
    source_text: str = "",
) -> QualityReport:
    """
    对单条 MemoryCandidate 进行质量校验。

    检查项：
    1. 准确性：内容是否完整有意义（非截断、非幻觉特征检测）
    2. 可用性：是否具有后续检索价值
    3. 置信度：低置信度 → pending

    Args:
        candidate: 待校验的记忆候选
        source_text: 原始文本（用于准确性校验参考）

    Returns:
        QualityReport 包含校验结果和建议状态
    """
    issues = []
    is_accurate = True
    is_usable = True
    accuracy_notes = []
    usability_notes = []

    # ---- 准确性检查 ----

    # 1.1 内容不能为空
    if not candidate.content.strip():
        is_accurate = False
        accuracy_notes.append("content 为空")
        issues.append("empty_content")

    # 1.2 内容不能过短（至少 10 个字符）
    if len(candidate.content.strip()) < 10:
        is_accurate = False
        accuracy_notes.append("content 过短 (< 10 chars)")
        issues.append("content_too_short")

    # 1.3 检测幻觉特征：内容中出现明显的占位符或不确定表达
    hallucination_patterns = [
        "无法确定", "不确定", "可能", "也许",
        "[TODO]", "[FIXME]", "[PLACEHOLDER]",
        "N/A", "TBD", "unknown",
    ]
    hallucination_count = sum(
        1 for p in hallucination_patterns if p.lower() in candidate.content.lower()
    )
    if hallucination_count >= 3:
        is_accurate = False
        accuracy_notes.append(f"内容包含 {hallucination_count} 个不确定标记")
        issues.append("too_many_uncertain_markers")

    # 1.4 与 source_text 的基本一致性（如果提供）
    if source_text and len(candidate.content) > 200:
        # 粗略检查：过长内容可能包含编造
        content_ratio = len(candidate.content) / max(len(source_text), 1)
        if content_ratio > 0.8:
            accuracy_notes.append("生成内容占比过高，可能包含冗余或编造")
            issues.append("content_too_long_vs_source")

    # ---- 可用性检查 ----

    # 2.1 summary 不能为空
    if not candidate.summary.strip():
        is_usable = False
        usability_notes.append("summary 为空")
        issues.append("empty_summary")

    # 2.2 key_points 至少 1 条
    if not candidate.key_points:
        is_usable = False
        usability_notes.append("key_points 为空")
        issues.append("empty_key_points")

    # 2.3 tags 至少 1 个
    if not candidate.tags:
        is_usable = False
        usability_notes.append("tags 为空")
        issues.append("empty_tags")

    # 2.4 置信度过低
    if candidate.confidence < 0.3:
        usability_notes.append(f"置信度过低 ({candidate.confidence:.2f})")
        issues.append("very_low_confidence")

    # ---- 状态判定 ----
    if not is_accurate or not is_usable:
        suggested_status = "pending"
    elif candidate.confidence < 0.5:
        suggested_status = "pending"
    else:
        suggested_status = "active"

    # 综合质量分
    accuracy_score = 1.0 if is_accurate else 0.3
    usability_score = 1.0 if is_usable else 0.3
    confidence_factor = candidate.confidence
    quality_score = round(
        0.4 * accuracy_score + 0.3 * usability_score + 0.3 * confidence_factor, 2
    )

    report = QualityReport(
        candidate=candidate,
        is_accurate=is_accurate,
        accuracy_note="; ".join(accuracy_notes) if accuracy_notes else "准确性检查通过",
        is_usable=is_usable,
        usability_note="; ".join(usability_notes) if usability_notes else "可用性检查通过",
        suggested_status=suggested_status,
        quality_score=quality_score,
        issues=issues,
    )

    if issues:
        logger.info(
            f"Quality check for [{candidate.memory_type}] "
            f"score={quality_score:.2f} status={suggested_status} issues={issues}"
        )

    return report


def verify_candidates_batch(
    candidates: list[MemoryCandidate],
    source_text: str = "",
) -> list[QualityReport]:
    """
    对多条 candidates 执行批量质量校验。

    Returns:
        QualityReport 列表，顺序与 candidates 一致
    """
    return [verify_candidate_quality(c, source_text) for c in candidates]


# ============================================================
# LLM 辅助质量校验（用于高价值场景）
# ============================================================

QUALITY_CHECK_SYSTEM_PROMPT = """You are a memory quality auditor. For each memory entry, evaluate:
1. Accuracy: Does this memory faithfully reflect what was actually discussed, without hallucination?
2. Usability: Would this memory be useful for future retrieval in a conversation context?
3. Completeness: Are all required fields filled meaningfully?

For each memory, return:
- memory_index: the index in the original list
- is_accurate: true/false
- accuracy_issue: describe any accuracy problems (or empty string)
- is_usable: true/false
- usability_issue: describe any usability problems (or empty string)
- suggested_status: "active" or "pending"
- quality_score: 0.0-1.0

Output ONLY valid JSON: {"evaluations": [...]}"""

QUALITY_CHECK_USER_TEMPLATE = """Evaluate the quality of these generated memories:

Source Text: {source_text}

Memories:
{memories_json}

Return your evaluation."""

QUALITY_CHECK_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "evaluations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "memory_index": {"type": "integer"},
                    "is_accurate": {"type": "boolean"},
                    "accuracy_issue": {"type": "string"},
                    "is_usable": {"type": "boolean"},
                    "usability_issue": {"type": "string"},
                    "suggested_status": {"type": "string", "enum": ["active", "pending"]},
                    "quality_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["memory_index", "is_accurate", "is_usable", "suggested_status", "quality_score"],
            },
        }
    },
    "required": ["evaluations"],
}


class QualityAuditor:
    """
    使用 LLM 进行深度质量审计（可选，用于高价值场景）。
    """

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def audit(
        self,
        candidates: list[MemoryCandidate],
        source_text: str,
    ) -> list[QualityReport]:
        """
        使用 LLM 对记忆候选进行深度质量审计。

        Args:
            candidates: 待审计的记忆候选列表
            source_text: 原始文本

        Returns:
            QualityReport 列表
        """
        if not candidates:
            return []

        import json

        # 构建简化版的 memories JSON
        memories_for_audit = []
        for i, c in enumerate(candidates):
            memories_for_audit.append({
                "index": i,
                "content": c.content[:300],
                "summary": c.summary[:150],
                "memory_type": c.memory_type,
                "importance": c.importance,
                "confidence": c.confidence,
            })

        try:
            user_content = QUALITY_CHECK_USER_TEMPLATE.format(
                source_text=source_text[:2000],
                memories_json=json.dumps(memories_for_audit, ensure_ascii=False),
            )

            data = await self._llm.extract_structured(
                system_prompt=QUALITY_CHECK_SYSTEM_PROMPT,
                user_content=user_content,
                output_schema=QUALITY_CHECK_OUTPUT_SCHEMA,
            )

            evaluations = data.get("evaluations", [])
            eval_map = {e.get("memory_index", -1): e for e in evaluations}

            reports = []
            for i, c in enumerate(candidates):
                if i in eval_map:
                    e = eval_map[i]
                    report = QualityReport(
                        candidate=c,
                        is_accurate=e.get("is_accurate", True),
                        accuracy_note=e.get("accuracy_issue", ""),
                        is_usable=e.get("is_usable", True),
                        usability_note=e.get("usability_issue", ""),
                        suggested_status=e.get("suggested_status", "active"),
                        quality_score=e.get("quality_score", 0.5),
                        issues=(
                            [e["accuracy_issue"]] if e.get("accuracy_issue") else []
                        ) + (
                            [e["usability_issue"]] if e.get("usability_issue") else []
                        ),
                    )
                else:
                    report = verify_candidate_quality(c, source_text)
                reports.append(report)

            return reports

        except Exception as e:
            logger.warning(f"LLM quality audit failed, falling back to rule-based: {e}")
            return verify_candidates_batch(candidates, source_text)
