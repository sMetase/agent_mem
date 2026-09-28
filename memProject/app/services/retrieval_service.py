# -*- coding: utf-8 -*-
"""
多信号融合检索服务 — mem0 语义搜索 + 应用层元数据过滤。
"""

import time
from typing import Any, Optional

from app.core.config import get_settings
from app.core.logger import get_logger
from app.services.mem0_client import mem0_client

settings = get_settings()
logger = get_logger("retrieval")


def _truncate_text(text: str, max_length: Optional[int]) -> str:
    """截断文本到指定长度，超出时追加省略号。"""
    if not max_length or max_length <= 0:
        return text
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def build_filters(
    user_id: str,
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
) -> dict:
    filters: dict[str, Any] = {"user_id": user_id}
    if agent_id:
        filters["agent_id"] = agent_id
    if session_id:
        filters["run_id"] = session_id
    if time_start or time_end:
        created_at: dict = {}
        if time_start:
            created_at["gte"] = time_start
        if time_end:
            created_at["lte"] = time_end
        filters["created_at"] = created_at
    return filters


def _post_filter(
    items: list[dict],
    scene_id: Optional[str] = None,
    task_id: Optional[str] = None,
    memory_types: Optional[list[str]] = None,
    include_inactive: bool = False,
    status: Optional[list[str]] = None,
    keyword: Optional[str] = None,
) -> list[dict]:
    """mem0 返回后，按 metadata + 关键词 筛选。

    status 优先于 include_inactive：传 status 则按列表精确匹配，
    不传则回退到 include_inactive 行为（False=只查 active）。
    """
    filtered = []
    for item in items:
        meta = item.get("metadata", {}) or {}
        if scene_id and meta.get("scene_id") != scene_id:
            continue
        if task_id and meta.get("task_id") != task_id:
            continue
        if memory_types and meta.get("memory_type") not in memory_types:
            continue
        # 状态筛选：status 优先，回退到 include_inactive
        item_status = meta.get("status", "active")
        if status is not None:
            if item_status not in status:
                continue
        elif not include_inactive and item_status == "deleted":
            continue
        if keyword:
            content = item.get("memory", "").lower()
            if keyword.lower() not in content:
                continue
        filtered.append(item)
    return filtered


def search(
    query: str,
    *,
    user_id: str,
    agent_id: Optional[str] = None,
    scene_id: Optional[str] = None,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    memory_types: Optional[list[str]] = None,
    status: Optional[list[str]] = None,
    max_content_length: Optional[int] = None,
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
    top_k: int = 10,
    include_inactive: bool = False,
    include_scores: bool = True,
    rerank: bool = True,
    keyword: Optional[str] = None,
) -> dict:
    """多信号融合检索：mem0混合搜索 + 应用层后过滤"""
    start = time.perf_counter()

    mem0_filters = build_filters(
        user_id=user_id, agent_id=agent_id, session_id=session_id,
        time_start=time_start, time_end=time_end,
    )

    logger.info(f"Search: query='{query[:50]}...', filters={mem0_filters}, top_k={top_k}")

    try:
        fetch_k = max(top_k * 3, 30)
        raw = mem0_client.search(
            query=query, user_id=user_id, limit=fetch_k,
            filters=mem0_filters, rerank=rerank,
        )
    except Exception as e:
        logger.error(f"mem0 search failed: {e}")
        raise

    all_items = raw.get("results", [])

    filtered = _post_filter(
        all_items,
        scene_id=scene_id, task_id=task_id,
        memory_types=memory_types, include_inactive=include_inactive,
        status=status, keyword=keyword,
    )
    filtered_total = len(filtered)
    filtered = filtered[:top_k]

    elapsed = int((time.perf_counter() - start) * 1000)

    results = []
    for item in filtered:
        meta = item.get("metadata", {}) or {}
        results.append({
            "memory_id": item.get("id", ""),
            "content": _truncate_text(item.get("memory", ""), max_content_length),
            "memory_type": meta.get("memory_type", "unknown"),
            "status": meta.get("status", "active"),
            "relevance_score": item.get("score") if include_scores else None,
            "importance": meta.get("importance", 0.5),
            "confidence": meta.get("confidence", 0.5),
            "source_type": meta.get("source_type", "extracted"),
            "agent_id": item.get("agent_id", ""),
            "scene_id": meta.get("scene_id", ""),
            "session_id": item.get("run_id", ""),
            "task_id": meta.get("task_id", ""),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "metadata": meta,
        })

    return {
        "query": query,
        "results": results,
        "total_candidates": len(all_items),
        "filtered_count": filtered_total,
        "elapsed_ms": elapsed,
    }
