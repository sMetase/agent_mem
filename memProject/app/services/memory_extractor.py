# -*- coding: utf-8 -*-
"""
Memory Extractor — 统一记忆抽取服务。

单次 LLM 调用同时抽取五类结构化信息，每条碎片独立评分。
value < 0.3 的碎片自动过滤，不进入后续流程。
"""

from dataclasses import dataclass, field
from typing import Optional

from app.core.exceptions import MemoryGenerationError
from app.core.logger import get_logger
from app.prompts.extraction import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_TEMPLATE,
    EXTRACTION_OUTPUT_SCHEMA,
)
from app.services.llm_client import LLMClient

logger = get_logger("memory_extractor")

VALUE_THRESHOLD = 0.3


def _filter_value(items: list[dict]) -> list[dict]:
    """过滤 value < 阈值的条目，并移除 value 字段。"""
    return [{k: v for k, v in item.items() if k != "value"}
            for item in items
            if item.get("value", 0.0) >= VALUE_THRESHOLD]


# ============================================================
# 抽取结果数据类 — 保持与 Generator 兼容
# ============================================================

@dataclass
class KeyFactsResult:
    business_objects: list[dict] = field(default_factory=list)
    constraints: list[dict] = field(default_factory=list)
    confirmations: list[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.business_objects or self.constraints or self.confirmations)


@dataclass
class TaskStateResult:
    current_progress: str = ""
    completed_items: list[dict] = field(default_factory=list)
    pending_items: list[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.current_progress or self.completed_items or self.pending_items)


@dataclass
class PreferenceResult:
    style_preferences: list[dict] = field(default_factory=list)
    habitual_preferences: list[dict] = field(default_factory=list)
    decision_tendencies: list[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.style_preferences or self.habitual_preferences or self.decision_tendencies)


@dataclass
class ProcessResult:
    execution_actions: list[dict] = field(default_factory=list)
    intermediate_conclusions: list[dict] = field(default_factory=list)
    failure_records: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.execution_actions or self.intermediate_conclusions
                    or self.failure_records or self.decisions)


@dataclass
class FeedbackResult:
    corrections: list[dict] = field(default_factory=list)
    confirmation_statuses: list[dict] = field(default_factory=list)
    replacement_relationships: list[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.corrections or self.confirmation_statuses
                    or self.replacement_relationships)


@dataclass
class ExtractionResult:
    key_facts: Optional[KeyFactsResult] = None
    task_state: Optional[TaskStateResult] = None
    preferences: Optional[PreferenceResult] = None
    process: Optional[ProcessResult] = None
    feedback: Optional[FeedbackResult] = None
    source_text: str = ""

    def is_empty(self) -> bool:
        has_facts = self.key_facts is not None and not self.key_facts.is_empty()
        has_state = self.task_state is not None and not self.task_state.is_empty()
        has_pref = self.preferences is not None and not self.preferences.is_empty()
        has_proc = self.process is not None and not self.process.is_empty()
        has_fb = self.feedback is not None and not self.feedback.is_empty()
        return not (has_facts or has_state or has_pref or has_proc or has_fb)

    def to_dict(self) -> dict:
        result: dict = {"source_text": self.source_text}

        if self.key_facts:
            result["business_objects"] = self.key_facts.business_objects
            result["constraints"] = self.key_facts.constraints
            result["confirmations"] = self.key_facts.confirmations
        else:
            result["business_objects"] = []
            result["constraints"] = []
            result["confirmations"] = []

        if self.task_state:
            result["current_progress"] = self.task_state.current_progress
            result["completed_items"] = self.task_state.completed_items
            result["pending_items"] = self.task_state.pending_items
        else:
            result["current_progress"] = ""
            result["completed_items"] = []
            result["pending_items"] = []

        if self.preferences:
            result["style_preferences"] = self.preferences.style_preferences
            result["habitual_preferences"] = self.preferences.habitual_preferences
            result["decision_tendencies"] = self.preferences.decision_tendencies
        else:
            result["style_preferences"] = []
            result["habitual_preferences"] = []
            result["decision_tendencies"] = []

        if self.process:
            result["execution_actions"] = self.process.execution_actions
            result["intermediate_conclusions"] = self.process.intermediate_conclusions
            result["failure_records"] = self.process.failure_records
            result["decisions"] = self.process.decisions
        else:
            result["execution_actions"] = []
            result["intermediate_conclusions"] = []
            result["failure_records"] = []
            result["decisions"] = []

        if self.feedback:
            result["corrections"] = self.feedback.corrections
            result["confirmation_statuses"] = self.feedback.confirmation_statuses
            result["replacement_relationships"] = self.feedback.replacement_relationships
        else:
            result["corrections"] = []
            result["confirmation_statuses"] = []
            result["replacement_relationships"] = []

        return result


class MemoryExtractor:
    """统一记忆抽取器。单次 LLM 调用抽取五类信息，每条碎片独立 value 评分。"""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def extract(
        self,
        text: str,
        types: Optional[list[str]] = None,
        task_context: Optional[dict] = None,
    ) -> ExtractionResult:
        if not text.strip():
            return ExtractionResult(source_text=text)

        try:
            user_content = EXTRACTION_USER_TEMPLATE.format(text=text)
            data = await self._llm.extract_structured(
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_content=user_content,
                output_schema=EXTRACTION_OUTPUT_SCHEMA,
            )
        except Exception as e:
            raise MemoryGenerationError(f"记忆抽取失败: {str(e)}")

        result = ExtractionResult(source_text=text)

        kf = data.get("key_facts", {}) or {}
        result.key_facts = KeyFactsResult(
            business_objects=_filter_value(kf.get("business_objects", [])),
            constraints=_filter_value(kf.get("constraints", [])),
            confirmations=_filter_value(kf.get("confirmations", [])),
        )

        ts = data.get("task_state", {}) or {}
        result.task_state = TaskStateResult(
            current_progress=ts.get("current_progress", ""),
            completed_items=_filter_value(ts.get("completed_items", [])),
            pending_items=_filter_value(ts.get("pending_items", [])),
        )

        pref = data.get("preferences", {}) or {}
        result.preferences = PreferenceResult(
            style_preferences=_filter_value(pref.get("style_preferences", [])),
            habitual_preferences=_filter_value(pref.get("habitual_preferences", [])),
            decision_tendencies=_filter_value(pref.get("decision_tendencies", [])),
        )

        proc = data.get("process", {}) or {}
        result.process = ProcessResult(
            execution_actions=_filter_value(proc.get("execution_actions", [])),
            intermediate_conclusions=_filter_value(proc.get("intermediate_conclusions", [])),
            failure_records=_filter_value(proc.get("failure_records", [])),
            decisions=_filter_value(proc.get("decisions", [])),
        )

        fb = data.get("feedback", {}) or {}
        result.feedback = FeedbackResult(
            corrections=_filter_value(fb.get("corrections", [])),
            confirmation_statuses=_filter_value(fb.get("confirmation_statuses", [])),
            replacement_relationships=_filter_value(fb.get("replacement_relationships", [])),
        )

        extracted_types = []
        if not result.key_facts.is_empty():
            extracted_types.append("key_fact")
        if not result.task_state.is_empty():
            extracted_types.append("task_state")
        if not result.preferences.is_empty():
            extracted_types.append("preference")
        if not result.process.is_empty():
            extracted_types.append("process")
        if not result.feedback.is_empty():
            extracted_types.append("feedback")

        logger.info(f"Extraction complete: text_len={len(text)}, types={extracted_types}")
        return result
