# -*- coding: utf-8 -*-
"""
记忆相关 Schema — 写入/检索/上下文/更新/删除。

对齐前端对接文档 API 契约：
- 写入请求：messages 数组为 Primary 格式
- 写入响应：results[{id, memory, event}]
- 统一响应：{code, message, data}
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================
# 写入
# ============================================================

class MessageItem(BaseModel):
    """单条对话消息（对齐前端文档 messages 数组元素）"""
    role: str = Field(..., description="角色: user / assistant / system")
    content: str = Field(..., min_length=1, max_length=50000, description="消息内容")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"user", "assistant", "system", "tool", "agent"}
        if v.lower() not in allowed:
            raise ValueError(f"非法 role 值: '{v}'，允许: {', '.join(sorted(allowed))}")
        return v.lower()

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str) -> str:
        return v.strip()


class MemoryWriteRequest(BaseModel):
    """
    同步写入请求 — 对齐前端对接文档 一.1 节。

    支持三种数据类型（通过 interaction_type 区分）：
    - dialogue:     当前对话记录，messages 数组为 Primary 格式
    - session:      历史会话数据，含会话时间/来源/摘要
    - task_process: 任务过程数据，含目标/进展/执行结果
    """
    user_id: str = Field(..., min_length=1, max_length=128, description="用户唯一标识")
    scene_id: Optional[str] = Field(None, max_length=128, description="场景标识")
    session_id: str = Field(..., min_length=1, max_length=128, description="会话ID")
    task_id: Optional[str] = Field(None, max_length=128, description="任务标识")
    interaction_type: str = Field(
        default="dialogue",
        description="数据类型: dialogue(对话记录) / session(历史会话) / task_process(任务过程)"
    )
    messages: list[MessageItem] = Field(
        default_factory=list, max_length=100, description="对话消息数组（dialogue/session 类型使用）"
    )
    # 历史会话专用字段
    session_time: Optional[str] = Field(None, description="历史会话发生时间 (ISO 8601)")
    session_source: Optional[str] = Field(None, max_length=256, description="历史会话来源智能体/场景")
    session_summary: Optional[str] = Field(None, max_length=10000, description="历史会话摘要/内容")
    # 任务过程专用字段
    task_goal: Optional[str] = Field(None, max_length=2000, description="任务目标")
    task_progress: Optional[str] = Field(None, max_length=5000, description="任务进展描述")
    task_result: Optional[str] = Field(None, max_length=5000, description="任务执行结果")
    metadata: Optional[dict[str, Any]] = Field(None, description="扩展元数据")

    @field_validator("interaction_type")
    @classmethod
    def validate_interaction_type(cls, v: str) -> str:
        allowed = {"dialogue", "session", "task_process"}
        v_lower = v.strip().lower()
        if v_lower not in allowed:
            raise ValueError(f"非法 interaction_type: '{v}'，允许: {', '.join(sorted(allowed))}")
        return v_lower

    @field_validator("user_id")
    @classmethod
    def normalize_user_id(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("scene_id", "session_id", "task_id")
    @classmethod
    def normalize_optional_id(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return v.strip().lower()
        return v

    @field_validator("messages")
    @classmethod
    def validate_messages_for_type(cls, v: list, info) -> list:
        """session/task_process 类型允许空 messages，dialogue 类型必须有 messages"""
        itype = info.data.get("interaction_type", "dialogue") if info.data else "dialogue"
        if itype == "dialogue" and len(v) == 0:
            raise ValueError("dialogue 类型必须提供 messages 数组")
        return v

    def get_content_text(self) -> str:
        """将数据内容拼接为单个文本（用于 mem0 LLM 抽取）"""
        parts = []
        # 对话消息
        for i, m in enumerate(self.messages):
            parts.append(f"[{m.role}](轮次{i + 1}): {m.content}")
        # 历史会话
        if self.interaction_type == "session":
            if self.session_summary:
                parts.append(f"[历史会话摘要]: {self.session_summary}")
            if self.session_source:
                parts.append(f"[会话来源]: {self.session_source}")
            if self.session_time:
                parts.append(f"[会话时间]: {self.session_time}")
        # 任务过程
        if self.interaction_type == "task_process":
            if self.task_goal:
                parts.append(f"[任务目标]: {self.task_goal}")
            if self.task_progress:
                parts.append(f"[任务进展]: {self.task_progress}")
            if self.task_result:
                parts.append(f"[执行结果]: {self.task_result}")
        return "\n".join(parts) if parts else ""

    def get_last_role(self) -> str:
        """获取最后一条消息的角色"""
        return self.messages[-1].role if self.messages else "user"

    def get_last_content(self) -> str:
        """获取最后一条消息的内容"""
        return self.messages[-1].content if self.messages else ""


# ============================================================
# 写入响应 — 对齐前端文档 results 格式
# ============================================================

class MemoryEvent(str, Enum):
    """记忆事件类型"""
    ADD = "ADD"       # 新增记忆
    UPDATE = "UPDATE" # 更新已有记忆
    SKIP = "SKIP"     # 跳过（无价值信息）
    MERGE = "MERGE"   # 合并到已有记忆


class WriteResultItem(BaseModel):
    """单条写入结果（对齐前端文档 results 数组元素）"""
    id: str = Field(..., description="记忆 ID")
    memory: str = Field(..., description="记忆内容摘要")
    event: MemoryEvent = Field(..., description="事件: ADD / UPDATE / SKIP / MERGE")


class MemoryWriteResponse(BaseModel):
    """写入响应"""
    mode: str = Field(default="legacy", description="处理路径：pipeline|mock|mq|mq_timeout|degraded")
    results: list[WriteResultItem] = Field(default_factory=list, description="每条消息的处理结果")


# ============================================================
# 检索
# ============================================================

class MemorySearchRequest(BaseModel):
    """混合检索请求"""
    query: str = Field(..., description="检索查询文本")
    user_id: str = Field(..., description="用户标识")
    scene_id: Optional[str] = Field(None)
    task_id: Optional[str] = Field(None)
    session_id: Optional[str] = Field(None)
    agent_id: Optional[str] = Field(None, description="智能体标识")
    memory_types: Optional[list[str]] = Field(None, description="筛选类型: preference/fact/task/decision/constraint")
    keyword: Optional[str] = Field(None, description="应用层关键词后过滤（mem0 BM25 融合不保证TopK全命中，传入后强制过滤）")
    top_k: int = Field(default=10, ge=1, le=50)
    time_start: Optional[datetime] = Field(None)
    time_end: Optional[datetime] = Field(None)
    include_scores: bool = Field(default=True)
    rerank: bool = Field(default=True, description="启用 Reranker 二次排序（+150-200ms，默认开启）")
    status: Optional[list[str]] = Field(None, description="筛选状态，不传默认只查 active")
    max_content_length: Optional[int] = Field(None, description="返回内容最大字符数，超出截断")


# ============================================================
# 上下文
# ============================================================

class ContextRequest(BaseModel):
    """上下文返回请求"""
    query: str = Field(..., description="当前用户问题")
    user_id: str = Field(..., description="用户标识")
    agent_id: Optional[str] = Field(None)
    scene_id: Optional[str] = Field(None)
    task_id: Optional[str] = Field(None)
    session_id: Optional[str] = Field(None)
    max_tokens: int = Field(default=3000)
    top_k: int = Field(default=10)
    max_content_length: Optional[int] = Field(None)
    group_by_type: bool = Field(default=True)
    memory_types: Optional[list[str]] = Field(None)
    status: Optional[list[str]] = Field(None)
    include_preferences: bool = Field(default=True)
    include_facts: bool = Field(default=True)
    include_task_state: bool = Field(default=True)
    rerank: bool = Field(default=False)


# ============================================================
# 更新 / 删除
# ============================================================

class MemoryUpdateRequest(BaseModel):
    """更新记忆请求"""
    memory_id: str = Field(..., description="记忆唯一标识")
    content: Optional[str] = Field(None)
    summary: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    importance: Optional[float] = Field(None, ge=0, le=1)
    confidence: Optional[float] = Field(None, ge=0, le=1)
    tags: Optional[list[str]] = Field(None)


class MemoryUpdateResponse(BaseModel):
    """更新响应"""
    memory_id: str
    updated: bool = True
    version: int = 1


class MemoryDeleteRequest(BaseModel):
    """删除记忆请求（软删除）"""
    memory_id: str = Field(..., description="记忆唯一标识")
    reason: Optional[str] = Field(None)


class MemoryDeleteResponse(BaseModel):
    """删除响应"""
    memory_id: str
    deleted: bool = True
    previous_status: str = "active"
