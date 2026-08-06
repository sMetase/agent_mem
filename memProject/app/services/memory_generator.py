# -*- coding: utf-8 -*-
"""
Memory Generator — 结构化记忆生成服务。

将 ExtractionResult 中的抽取数据通过 LLM 转化为标准化的 MemoryCandidate 对象，
包含记忆文本、摘要、要点、类型标签、重要性/置信度评分。
"""

import json
from dataclasses import dataclass, field
from typing import Optional

from app.core.exceptions import MemoryGenerationError
from app.core.logger import get_logger
from app.prompts.memory_generation import (
    MEMORY_GENERATION_SYSTEM_PROMPT,
    MEMORY_GENERATION_USER_TEMPLATE,
    MEMORY_GENERATION_OUTPUT_SCHEMA,
)
from app.services.llm_client import LLMClient
from app.services.memory_extractor import ExtractionResult

logger = get_logger("memory_generator")

VALID_MEMORY_TYPES = {
    "fact", "preference", "task_state", "process", "correction",
}


@dataclass
class MemoryCandidate:
    """一条待存储的标准化记忆。"""
    content: str
    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    memory_type: str = "fact"
    tags: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    importance: float = 0.5
    confidence: float = 0.5
    source_type: str = "extracted"

    def validate(self) -> None:
        """验证必填字段和值域。"""
        if not self.content.strip():
            raise ValueError("content 不能为空")
        if not self.summary.strip():
            self.summary = self.content[:200]
        if self.memory_type not in VALID_MEMORY_TYPES:
            logger.warning(f"Invalid memory_type '{self.memory_type}', defaulting to 'fact'")
            self.memory_type = "fact"
        self.importance = max(0.0, min(1.0, self.importance))
        self.confidence = max(0.0, min(1.0, self.confidence))


class MemoryGenerator:
    """
    结构化记忆生成器。

    使用 LLM 将抽取结果转化为标准化的 MemoryCandidate 对象列表。
    LLM 负责判断如何将相关事实分组、评估重要性/置信度。
    """

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def generate(self, extraction_result: ExtractionResult) -> list[MemoryCandidate]:
        """
        从抽取结果生成结构化记忆。

        Args:
            extraction_result: MemoryExtractor 的输出

        Returns:
            MemoryCandidate 列表

        Raises:
            MemoryGenerationError: LLM 生成失败
        """
        if extraction_result.is_empty():
            logger.info("Extraction result is empty, no memories to generate")
            return []

        data = extraction_result.to_dict()

        try:
            user_content = MEMORY_GENERATION_USER_TEMPLATE.format(
                business_objects=json.dumps(data.get("business_objects", []), ensure_ascii=False),
                constraints=json.dumps(data.get("constraints", []), ensure_ascii=False),
                confirmations=json.dumps(data.get("confirmations", []), ensure_ascii=False),
                current_progress=data.get("current_progress", ""),
                completed_items=json.dumps(data.get("completed_items", []), ensure_ascii=False),
                pending_items=json.dumps(data.get("pending_items", []), ensure_ascii=False),
                style_preferences=json.dumps(data.get("style_preferences", []), ensure_ascii=False),
                habitual_preferences=json.dumps(data.get("habitual_preferences", []), ensure_ascii=False),
                decision_tendencies=json.dumps(data.get("decision_tendencies", []), ensure_ascii=False),
                execution_actions=json.dumps(data.get("execution_actions", []), ensure_ascii=False),
                intermediate_conclusions=json.dumps(data.get("intermediate_conclusions", []), ensure_ascii=False),
                failure_records=json.dumps(data.get("failure_records", []), ensure_ascii=False),
                decisions=json.dumps(data.get("decisions", []), ensure_ascii=False),
                corrections=json.dumps(data.get("corrections", []), ensure_ascii=False),
                confirmation_statuses=json.dumps(data.get("confirmation_statuses", []), ensure_ascii=False),
                replacement_relationships=json.dumps(data.get("replacement_relationships", []), ensure_ascii=False),
            )

            llm_result = await self._llm.extract_structured(
                system_prompt=MEMORY_GENERATION_SYSTEM_PROMPT,
                user_content=user_content,
                output_schema=MEMORY_GENERATION_OUTPUT_SCHEMA,
                max_tokens=4000,  # 记忆生成可能返回多条，需要更大输出空间
            )

            raw_memories = llm_result.get("memories", [])
            if not isinstance(raw_memories, list):
                logger.warning(f"LLM returned non-list memories: {type(raw_memories)}")
                return []

            candidates = []
            for item in raw_memories:
                try:
                    candidate = MemoryCandidate(
                        content=item.get("content", "").strip(),
                        summary=item.get("summary", "").strip(),
                        key_points=item.get("key_points", []),
                        memory_type=item.get("memory_type", "fact"),
                        tags=item.get("tags", []),
                        entities=item.get("entities", []),
                        importance=float(item.get("importance", 0.5)),
                        confidence=float(item.get("confidence", 0.5)),
                    )
                    candidate.validate()
                    candidates.append(candidate)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Skipping invalid memory candidate: {e}")
                    continue

            logger.info(f"Generated {len(candidates)} memory candidates from extraction result")
            return candidates

        except Exception as e:
            raise MemoryGenerationError(f"记忆生成失败: {str(e)}")

    async def generate_single(self, extraction_result: ExtractionResult) -> Optional[MemoryCandidate]:
        """
        生成单条综合记忆（用于简单场景）。

        Args:
            extraction_result: MemoryExtractor 的输出

        Returns:
            单条 MemoryCandidate 或 None（如果无法生成）
        """
        candidates = await self.generate(extraction_result)
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        # 多条时合并为一条综合记忆
        merged = MemoryCandidate(
            content="; ".join(c.content for c in candidates),
            summary=extraction_result.source_text[:200],
            key_points=[kp for c in candidates for kp in c.key_points],
            memory_type=candidates[0].memory_type,
            tags=list(set(t for c in candidates for t in c.tags)),
            entities=list(set(e for c in candidates for e in c.entities)),
            importance=max(c.importance for c in candidates),
            confidence=sum(c.confidence for c in candidates) / len(candidates),
        )
        return merged
