# -*- coding: utf-8 -*-
"""
数据库物理模型 — PostgreSQL 12 张表。
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean,
    DateTime, BigInteger, JSON, Index,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_uuid() -> str:
    return uuid.uuid4().hex


# ============================================================
# 1. T_USER
# ============================================================
class User(Base):
    __tablename__ = "t_user"

    id = Column(String(32), primary_key=True, default=_gen_uuid)
    user_id = Column(String(128), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=True)
    extra_meta = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


# ============================================================
# 2. T_AGENT
# ============================================================
class Agent(Base):
    __tablename__ = "t_agent"

    id = Column(String(32), primary_key=True, default=_gen_uuid)
    agent_id = Column(String(128), unique=True, nullable=False, index=True)
    agent_name = Column(String(256))
    scene_id = Column(String(128), nullable=True, index=True)
    api_key_hash = Column(String(256))
    api_key_prefix = Column(String(16))
    is_active = Column(Boolean, default=True)
    permissions = Column(JSON, default=list)
    extra_meta = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


# ============================================================
# 3. T_SCENE
# ============================================================
class Scene(Base):
    __tablename__ = "t_scene"

    id = Column(String(32), primary_key=True, default=_gen_uuid)
    scene_id = Column(String(128), unique=True, nullable=False, index=True)
    scene_name = Column(String(256))
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    extra_meta = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


# ============================================================
# 4. T_SESSION
# ============================================================
class Session(Base):
    __tablename__ = "t_session"

    id = Column(String(32), primary_key=True, default=_gen_uuid)
    session_id = Column(String(128), unique=True, nullable=False, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    agent_id = Column(String(128), nullable=True, index=True)
    scene_id = Column(String(128), nullable=True, index=True)
    task_id = Column(String(128), nullable=True, index=True)
    status = Column(String(32), default="active")
    started_at = Column(DateTime(timezone=True), default=_now)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    message_count = Column(Integer, default=0)
    extra_meta = Column(JSON, default=dict)


# ============================================================
# 5. T_TASK
# ============================================================
class Task(Base):
    __tablename__ = "t_task"

    id = Column(String(32), primary_key=True, default=_gen_uuid)
    task_id = Column(String(128), unique=True, nullable=False, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    agent_id = Column(String(128), nullable=True, index=True)
    scene_id = Column(String(128), nullable=True, index=True)
    session_id = Column(String(128), nullable=True, index=True)
    title = Column(String(512))
    goal = Column(Text)
    status = Column(String(32), default="pending")
    progress = Column(Text)
    completed_items = Column(JSON, default=list)
    pending_items = Column(JSON, default=list)
    started_at = Column(DateTime(timezone=True), default=_now)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)
    extra_meta = Column(JSON, default=dict)


# ============================================================
# 6. T_INTERACTION_RECORD
# ============================================================
class InteractionRecord(Base):
    __tablename__ = "t_interaction_record"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    record_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    agent_id = Column(String(128), nullable=True, index=True)
    scene_id = Column(String(128), nullable=True, index=True)
    session_id = Column(String(128), nullable=False, index=True)
    task_id = Column(String(128), nullable=True, index=True)
    interaction_type = Column(String(32), default="dialogue", index=True)
    turn_index = Column(Integer, default=0)
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    content_type = Column(String(32), default="text")
    processed = Column(Boolean, default=False)
    status = Column(String(32), default="pending_extract", index=True,
                    comment="记录状态: pending_extract / processed / failed")
    recorded_at = Column(DateTime(timezone=True), default=_now)
    extra_meta = Column(JSON, default=dict)

    __table_args__ = (
        Index("idx_interaction_session_turn", "session_id", "turn_index"),
        Index("idx_interaction_processed", "processed", "recorded_at"),
        Index("idx_interaction_user_time", "user_id", "recorded_at"),
        Index("idx_interaction_type_user", "interaction_type", "user_id"),
        Index("idx_interaction_user_session_time", "user_id", "session_id", "recorded_at"),
        Index("idx_interaction_status", "status", "recorded_at"),
    )


# ============================================================
# 7. T_MEMORY
# ============================================================
class Memory(Base):
    __tablename__ = "t_memory"

    id = Column(String(32), primary_key=True, default=_gen_uuid)
    memory_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    agent_id = Column(String(128), nullable=True, index=True)
    scene_id = Column(String(128), nullable=True, index=True)
    session_id = Column(String(128), nullable=True, index=True)
    task_id = Column(String(128), nullable=True, index=True)

    content = Column(Text, nullable=False)
    summary = Column(Text)
    key_points = Column(JSON, default=list)

    memory_type = Column(String(64), nullable=False, index=True)
    tags = Column(JSON, default=list)
    entities = Column(JSON, default=list)

    status = Column(String(32), default="active", index=True)
    version = Column(Integer, default=1)

    importance = Column(Float, default=0.5)
    confidence = Column(Float, default=0.5)
    use_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    decay_factor = Column(Float, default=1.0)

    memory_scope = Column(
        String(16), nullable=True, index=True,
        comment="记忆层级/复用边界: user / session / task / agent",
    )

    source_type = Column(String(32), default="extracted")
    source_record_ids = Column(JSON, default=list)

    vector_id = Column(String(64), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)

    __table_args__ = (
        Index("idx_memory_user_type_status", "user_id", "memory_type", "status"),
        Index("idx_memory_task", "task_id", "status"),
        Index("idx_memory_session", "session_id", "status"),
        Index("idx_memory_status_time", "status", "created_at"),
        Index("idx_memory_deleted_at", "deleted_at"),
        # 记忆层级统计索引（对齐 memory_scope_v1）
        Index("idx_memory_user_status_scope", "user_id", "status", "memory_scope"),
        Index("idx_memory_user_scene_status_scope", "user_id", "scene_id", "status", "memory_scope"),
    )


# ============================================================
# 7.1 T_MEMORY_HISTORY
# ============================================================
class MemoryHistory(Base):
    """记忆版本历史快照 — 每次 MERGE/UPDATE/替换 前保存旧版本内容。"""
    __tablename__ = "t_memory_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    memory_id = Column(String(64), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text)
    key_points = Column(JSON, default=list)
    tags = Column(JSON, default=list)
    entities = Column(JSON, default=list)
    importance = Column(Float, default=0.5)
    confidence = Column(Float, default=0.5)
    action = Column(String(32), nullable=True)  # merge / update / replace
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("idx_memory_history_memory", "memory_id", "version"),
    )


# ============================================================
# 8. T_MEMORY_VECTOR
# ============================================================
class MemoryVector(Base):
    __tablename__ = "t_memory_vector"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    memory_id = Column(String(64), nullable=False, index=True)
    vector_store_id = Column(String(128), unique=True, nullable=False)
    dimension = Column(Integer, default=1024)
    model_name = Column(String(128))
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("idx_memory_vector_memory", "memory_id"),
    )


# ============================================================
# 9. T_MEMORY_RELATION
# ============================================================
class MemoryRelation(Base):
    __tablename__ = "t_memory_relation"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_memory_id = Column(String(64), nullable=False, index=True)
    target_memory_id = Column(String(64), nullable=False, index=True)
    relation_type = Column(String(32), nullable=False)
    description = Column(Text)
    confidence = Column(Float, default=0.5)
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("idx_mem_rel_source", "source_memory_id", "relation_type"),
        Index("idx_mem_rel_target", "target_memory_id", "relation_type"),
    )


# ============================================================
# 10. T_RETRIEVAL_REQUEST
# ============================================================
class RetrievalRequest(Base):
    __tablename__ = "t_retrieval_request"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    request_id = Column(String(64), unique=True, nullable=False, index=True)
    agent_id = Column(String(128), nullable=True, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    scene_id = Column(String(128), nullable=True, index=True)
    session_id = Column(String(128), nullable=True, index=True)
    task_id = Column(String(128), nullable=True, index=True)
    query_text = Column(Text)
    filter_conditions = Column(JSON)
    top_k = Column(Integer, default=10)
    is_triggered = Column(Boolean, default=False)
    retrieval_mode = Column(String(32), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_now)


# ============================================================
# 11. T_RETRIEVAL_RESULT
# ============================================================
class RetrievalResult(Base):
    __tablename__ = "t_retrieval_result"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=False, index=True)
    memory_id = Column(String(64), nullable=False, index=True)
    rank = Column(Integer)
    relevance_score = Column(Float)
    semantic_score = Column(Float, nullable=True)
    keyword_score = Column(Float, nullable=True)
    recency_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("idx_result_request", "request_id", "rank"),
    )


# ============================================================
# 12. T_API_LOG
# ============================================================
class ApiLog(Base):
    __tablename__ = "t_api_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    log_id = Column(String(64), unique=True, nullable=False, index=True)
    trace_id = Column(String(64), index=True)
    agent_id = Column(String(128), nullable=True, index=True)
    api_path = Column(String(256))
    method = Column(String(16))
    request_params = Column(JSON)
    response_code = Column(Integer)
    error_code = Column(String(64), nullable=True)
    elapsed_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=_now, index=True)

    __table_args__ = (
        Index("idx_api_log_time", "created_at"),
        Index("idx_api_log_agent_path", "agent_id", "api_path"),
    )


# ============================================================
# 13. T_DEDUP_AUDIT
# ============================================================
class DedupAudit(Base):
    """去重融合操作审计记录"""
    __tablename__ = "t_dedup_audit"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    audit_id = Column(String(64), unique=True, nullable=False, index=True)
    # 新记忆信息
    candidate_content = Column(Text)
    candidate_memory_type = Column(String(64))
    # 匹配到的历史记忆
    matched_memory_id = Column(String(64), nullable=True, index=True)
    matched_content = Column(Text, nullable=True)
    # 匹配分数
    vector_score = Column(Float, nullable=True)
    keyword_overlap = Column(Float, nullable=True)
    identity_match = Column(Boolean, default=False)
    composite_score = Column(Float, nullable=True)
    # 决策结果
    action = Column(String(32), nullable=False)  # keep_new / merge / discard / update_existing / conflict
    # 融合前后内容
    before_content = Column(Text, nullable=True)   # 旧记忆内容
    after_content = Column(Text, nullable=True)    # 融合后内容
    # 状态变化
    old_status = Column(String(32), nullable=True)
    new_status = Column(String(32), nullable=True)
    old_version = Column(Integer, nullable=True)
    new_version = Column(Integer, nullable=True)
    # 上下文
    user_id = Column(String(128), nullable=True)
    task_id = Column(String(128), nullable=True)
    session_id = Column(String(128), nullable=True)
    message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_now, index=True)

    __table_args__ = (
        Index("idx_dedup_audit_matched", "matched_memory_id", "created_at"),
        Index("idx_dedup_audit_action", "action", "created_at"),
        Index("idx_dedup_audit_user", "user_id", "created_at"),
    )
