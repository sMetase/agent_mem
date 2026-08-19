# -*- coding: utf-8 -*-
# 业务逻辑层（你的 — 类型感知写入 + 多层聚合）
from app.services.memory_service import (
    create_memory,
    get_memory_by_id,
    update_memory_fields,
    soft_delete_memory,
    save_interaction_records,
    search_local,
    list_memories_filtered,
    build_context_query,
    log_retrieval_request,
    log_retrieval_results,
    get_stats,
    get_memory_relations,
    gen_memory_id,
    gen_record_id,
    gen_request_id,
)

# 存储读写层（master — memory_store）
from app.services.memory_store import MemoryStore, memory_store

# 记忆生成管线（Zhangchi）
from app.services.memory_pipeline import memory_pipeline, MemoryPipeline

# Mock 提取器（songlu66，联调期）
from app.services.mock_extractor import mock_extract_results

# MQ 异步（master — 函数式，无单例类）
from app.services.mq_producer import MQProducer, mq_producer

# mem0 客户端
from app.services.mem0_client import mem0_client, Mem0Client

__all__ = [
    # 你的 — 类型感知写入 + 多层聚合
    "create_memory",
    "get_memory_by_id",
    "update_memory_fields",
    "soft_delete_memory",
    "save_interaction_records",
    "search_local",
    "list_memories_filtered",
    "build_context_query",
    "log_retrieval_request",
    "log_retrieval_results",
    "get_stats",
    "get_memory_relations",
    "gen_memory_id",
    "gen_record_id",
    "gen_request_id",
    # master — 存储 + 管线 + MQ
    "MemoryStore",
    "memory_store",
    "memory_pipeline",
    "MemoryPipeline",
    "mock_extract_results",
    "MQProducer",
    "mq_producer",
    # mem0
    "mem0_client",
    "Mem0Client",
]
