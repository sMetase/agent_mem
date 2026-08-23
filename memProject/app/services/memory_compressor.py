# -*- coding: utf-8 -*-
"""
Memory Compressor — 长对话语义压缩与上下文恢复。

实现设计文档 Section 5.4:
  5.4.1: 长对话语义压缩 → 紧凑结构化表示
  5.4.2: 压缩后关键记忆保持验证
  5.4.3: 基于相关记忆召回的历史上下文补全
"""

import json
from dataclasses import dataclass, field
from typing import Optional

from app.core.logger import get_logger
from app.services.llm_client import LLMClient
from app.prompts.compression import (
    COMPRESSION_SYSTEM_PROMPT,
    COMPRESSION_USER_TEMPLATE,
    COMPRESSION_OUTPUT_SCHEMA,
    PRESERVATION_CHECK_SYSTEM_PROMPT,
    PRESERVATION_CHECK_USER_TEMPLATE,
    PRESERVATION_CHECK_OUTPUT_SCHEMA,
    CONTEXT_COMPLETION_SYSTEM_PROMPT,
    CONTEXT_COMPLETION_USER_TEMPLATE,
    CONTEXT_COMPLETION_OUTPUT_SCHEMA,
)

logger = get_logger("memory_compressor")


@dataclass
class CompressedMemory:
    """压缩后的记忆表示"""
    conversation_overview: str = ""
    key_facts: list[dict] = field(default_factory=list)
    user_preferences: list[dict] = field(default_factory=list)
    task_state: dict = field(default_factory=dict)
    key_decisions: list[dict] = field(default_factory=list)
    corrections_and_feedback: list[dict] = field(default_factory=list)
    important_context: list[str] = field(default_factory=list)
    trivial_summary: str = ""
    # 元数据
    original_length: int = 0
    compressed_length: int = 0
    compression_ratio: float = 0.0
    preservation_score: float = 1.0
    lost_items: list[dict] = field(default_factory=list)

    def to_compact_text(self) -> str:
        """将压缩记忆转为可注入上下文的紧凑文本。"""
        parts = []

        if self.conversation_overview:
            parts.append(f"[概览] {self.conversation_overview}")

        if self.key_facts:
            facts_text = "; ".join(
                f["fact"] for f in self.key_facts
            )
            parts.append(f"[关键事实] {facts_text}")

        if self.user_preferences:
            prefs_text = "; ".join(
                f["preference"] for f in self.user_preferences
            )
            parts.append(f"[用户偏好] {prefs_text}")

        if self.task_state:
            ts = self.task_state
            if ts.get("overall_progress"):
                parts.append(f"[任务进展] {ts['overall_progress']}")
            if ts.get("pending_items"):
                parts.append(f"[待处理] {'; '.join(ts['pending_items'])}")
            if ts.get("active_constraints"):
                parts.append(f"[约束] {'; '.join(ts['active_constraints'])}")

        if self.key_decisions:
            dec_text = "; ".join(d["decision"] for d in self.key_decisions)
            parts.append(f"[关键决策] {dec_text}")

        if self.corrections_and_feedback:
            corr_text = "; ".join(
                f"{c['corrected_from']} -> {c['corrected_to']}"
                for c in self.corrections_and_feedback
            )
            parts.append(f"[修正记录] {corr_text}")

        if self.important_context:
            parts.append(f"[重要上下文] {'; '.join(self.important_context)}")

        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "conversation_overview": self.conversation_overview,
            "key_facts": self.key_facts,
            "user_preferences": self.user_preferences,
            "task_state": self.task_state,
            "key_decisions": self.key_decisions,
            "corrections_and_feedback": self.corrections_and_feedback,
            "important_context": self.important_context,
            "trivial_summary": self.trivial_summary,
            "original_length": self.original_length,
            "compressed_length": self.compressed_length,
            "compression_ratio": self.compression_ratio,
            "preservation_score": self.preservation_score,
        }


class MemoryCompressor:
    """
    长对话记忆压缩器。

    用法:
        compressor = MemoryCompressor(llm_client)
        compressed = await compressor.compress(long_conversation_text)
        # 验证保留程度
        check = await compressor.check_preservation(original_text, compressed)
        # 上下文补全
        context = await compressor.complete_context(query, [compressed1, compressed2])
    """

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    # ---- 5.4.1: 语义压缩 ----

    async def compress(
        self,
        conversation_text: str,
        max_input_chars: int = 8000,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> CompressedMemory:
        """
        将长对话历史压缩为结构化紧凑表示。

        Args:
            conversation_text: 原始对话文本
            max_input_chars: 最大输入长度（超长截断）

        Returns:
            CompressedMemory 结构化压缩结果
        """
        original_len = len(conversation_text)
        if original_len > max_input_chars:
            conversation_text = conversation_text[:max_input_chars] + "\n...[截断]"
            logger.info(f"Conversation truncated: {original_len} -> {max_input_chars}")

        try:
            user_content = COMPRESSION_USER_TEMPLATE.format(
                conversation_text=conversation_text
            )
            data = await self._llm.extract_structured(
                system_prompt=COMPRESSION_SYSTEM_PROMPT,
                user_content=user_content,
                output_schema=COMPRESSION_OUTPUT_SCHEMA,
                max_tokens=4000,
                model=model,
                api_key=api_key,
            )

            compressed = CompressedMemory(
                conversation_overview=data.get("conversation_overview", ""),
                key_facts=data.get("key_facts", []),
                user_preferences=data.get("user_preferences", []),
                task_state=data.get("task_state", {}),
                key_decisions=data.get("key_decisions", []),
                corrections_and_feedback=data.get("corrections_and_feedback", []),
                important_context=data.get("important_context", []),
                trivial_summary=data.get("trivial_summary", ""),
                original_length=original_len,
            )

            # 计算压缩统计
            compact_text = compressed.to_compact_text()
            compressed.compressed_length = len(compact_text)
            compressed.compression_ratio = (
                1.0 - compressed.compressed_length / max(original_len, 1)
            )

            logger.info(
                f"Compression: {original_len} -> {compressed.compressed_length} chars "
                f"({compressed.compression_ratio:.1%} reduction), "
                f"{len(compressed.key_facts)} facts, "
                f"{len(compressed.user_preferences)} preferences"
            )
            return compressed

        except Exception as e:
            logger.error(f"Compression failed: {e}")
            # 降级：返回原始文本作为概览
            return CompressedMemory(
                conversation_overview=conversation_text[:500],
                original_length=original_len,
                compressed_length=min(500, original_len),
                compression_ratio=1.0 - min(500, original_len) / max(original_len, 1),
            )

    # ---- 5.4.2: 关键记忆保持验证 ----

    async def check_preservation(
        self,
        original_text: str,
        compressed: CompressedMemory,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> tuple[float, list[dict]]:
        """
        验证压缩后关键信息是否保留完整。

        Returns:
            (preservation_score, lost_items)
        """
        try:
            user_content = PRESERVATION_CHECK_USER_TEMPLATE.format(
                original_text=original_text[:3000],
                compressed_json=json.dumps(compressed.to_dict(), ensure_ascii=False),
            )
            data = await self._llm.extract_structured(
                system_prompt=PRESERVATION_CHECK_SYSTEM_PROMPT,
                user_content=user_content,
                output_schema=PRESERVATION_CHECK_OUTPUT_SCHEMA,
                max_tokens=2000,
                model=model,
                api_key=api_key,
            )

            score = data.get("preservation_score", 0.8)
            lost = data.get("lost_items", [])

            compressed.preservation_score = score
            compressed.lost_items = lost

            critical_lost = [li for li in lost if li.get("severity") == "critical"]
            if critical_lost:
                logger.warning(
                    f"Preservation check: score={score:.2f}, "
                    f"{len(lost)} lost ({len(critical_lost)} critical)"
                )
            else:
                logger.info(f"Preservation check: score={score:.2f}, {len(lost)} minor losses")

            return score, lost

        except Exception as e:
            logger.warning(f"Preservation check failed: {e}")
            return 0.8, []

    # ---- 5.4.3: 历史上下文补全 ----

    async def complete_context(
        self,
        query: str,
        compressed_memories: list[CompressedMemory],
        max_context_tokens: int = 3000,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> dict:
        """
        基于当前查询和历史压缩记忆，构建完整上下文。

        Args:
            query: 当前用户查询
            compressed_memories: 相关的历史压缩记忆列表
            max_context_tokens: 最大上下文 token 数

        Returns:
            {"context_text": str, "sections_used": list[str], "estimated_relevance": float}
        """
        if not compressed_memories:
            return {
                "context_text": "",
                "sections_used": [],
                "estimated_relevance": 0.0,
            }

        # 将所有压缩记忆拼接
        memories_parts = []
        for i, cm in enumerate(compressed_memories):
            memories_parts.append(f"--- Memory {i + 1} ---\n{cm.to_compact_text()}")

        memories_text = "\n\n".join(memories_parts)

        try:
            user_content = CONTEXT_COMPLETION_USER_TEMPLATE.format(
                query=query, memories_text=memories_text,
            )
            data = await self._llm.extract_structured(
                system_prompt=CONTEXT_COMPLETION_SYSTEM_PROMPT,
                user_content=user_content,
                output_schema=CONTEXT_COMPLETION_OUTPUT_SCHEMA,
                max_tokens=3000,
                model=model,
                api_key=api_key,
            )

            context_text = data.get("context_text", "")

            # Token 截断（粗略按 1.5 chars/token）
            if len(context_text) > max_context_tokens * 1.5:
                context_text = context_text[:int(max_context_tokens * 1.5)] + "\n...[截断]"
                logger.info(f"Context truncated to ~{max_context_tokens} tokens")

            return {
                "context_text": context_text,
                "sections_used": data.get("sections_used", []),
                "estimated_relevance": data.get("estimated_relevance", 0.5),
            }

        except Exception as e:
            logger.warning(f"Context completion failed: {e}")
            # 降级：直接拼接压缩记忆
            fallback = "\n".join(cm.to_compact_text() for cm in compressed_memories)
            return {
                "context_text": fallback[:int(max_context_tokens * 1.5)],
                "sections_used": ["fallback"],
                "estimated_relevance": 0.3,
            }

    # ---- 便捷方法：全流程 ----

    async def compress_and_validate(
        self,
        conversation_text: str,
        validate_preservation: bool = True,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> CompressedMemory:
        """
        压缩 + 可选的质量验证。
        """
        compressed = await self.compress(conversation_text, model=model, api_key=api_key)

        if validate_preservation:
            score, lost = await self.check_preservation(
                conversation_text, compressed, model=model, api_key=api_key,
            )
            compressed.preservation_score = score
            compressed.lost_items = lost

        return compressed


# 模块级单例（惰性初始化）
_memory_compressor: Optional[MemoryCompressor] = None


def get_compressor(llm: Optional[LLMClient] = None) -> MemoryCompressor:
    """获取压缩器单例。"""
    global _memory_compressor
    if _memory_compressor is None:
        if llm is None:
            from app.services.llm_client import llm_client as _llm
            llm = _llm
        _memory_compressor = MemoryCompressor(llm)
    return _memory_compressor
