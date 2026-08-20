# -*- coding: utf-8 -*-
"""
Memory Store Service — 记忆持久层的统一读写服务。

提供:
  - search: 语义搜索 (Qdrant) + 元数据过滤 (PostgreSQL)
  - list: 分页列出记忆
  - delete_all: 清理用户全部记忆 (PostgreSQL + Qdrant)
  - get_context: 检索并格式化为 Prompt 上下文片段
  - update_memory: 更新单条记忆
  - soft_delete: 软删除单条记忆

这是前端 /api/v1/memory/* 系列端点背后的核心存储层，
替换原来通过 MCP Server 中转的 mem0 路径。
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, delete, func, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.core.qdrant_client import QdrantClientSingleton, qdrant_client as _qdrant_singleton
from app.models.base import Memory
from app.services.embedding_client import EmbeddingClient, embedding_client as _emb_singleton
from app.services.memory_service import snapshot_memory_history

logger = get_logger("memory_store")


async def _log_retrieval(
    request_id: str,
    agent_id: Optional[str],
    user_id: str,
    query: str,
    filter_conditions: dict,
    top_k: int,
    results: list[dict],
    retrieval_mode: str = "hybrid",
) -> None:
    """fire-and-forget 写入检索请求和结果到 T_RETRIEVAL_REQUEST / T_RETRIEVAL_RESULT。"""
    try:
        from app.core.database import async_session_factory
        from app.models.base import RetrievalRequest, RetrievalResult

        async with async_session_factory() as session:
            req = RetrievalRequest(
                request_id=request_id,
                agent_id=agent_id,
                user_id=user_id,
                query_text=query,
                filter_conditions=filter_conditions,
                top_k=top_k,
                retrieval_mode=retrieval_mode,
            )
            session.add(req)

            for rank, item in enumerate(results, 1):
                session.add(RetrievalResult(
                    request_id=request_id,
                    memory_id=item.get("memory_id", ""),
                    rank=rank,
                    relevance_score=item.get("relevance_score"),
                ))

            await session.commit()
    except Exception as e:
        logger.warning(f"检索日志写入失败 (非致命): {e}")


class MemoryStore:
    """记忆存储服务 — 统一封装 PostgreSQL + Qdrant 读写。"""

    def __init__(
        self,
        embedding: Optional[EmbeddingClient] = None,
        qdrant: Optional[QdrantClientSingleton] = None,
    ) -> None:
        self._embedding = embedding
        self._qdrant = qdrant

    @property
    def embedding(self) -> EmbeddingClient:
        if self._embedding is None:
            self._embedding = _emb_singleton
        return self._embedding

    @property
    def qdrant(self) -> QdrantClientSingleton:
        if self._qdrant is None:
            self._qdrant = _qdrant_singleton
        return self._qdrant

    # ================================================================
    # Search
    # ================================================================

    @staticmethod
    def _truncate_text(text: str, max_length: Optional[int]) -> str:
        """截断文本到指定长度，超出时追加省略号。"""
        if not max_length or max_length <= 0:
            return text
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."

    @staticmethod
    def _apply_status_filter(stmt, status: Optional[list[str]]):
        """对查询应用状态筛选。不传或空列表时默认只查 active。"""
        if status:
            return stmt.where(Memory.status.in_(status))
        return stmt.where(Memory.status == "active")

    async def search(
        self,
        query: str,
        user_id: str,
        db: AsyncSession,
        agent_id: Optional[str] = None,
        scene_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        memory_types: Optional[list[str]] = None,
        status: Optional[list[str]] = None,
        max_content_length: Optional[int] = None,
        time_start: Optional[datetime] = None,
        time_end: Optional[datetime] = None,
        top_k: int = 10,
        rerank: bool = False,
    ) -> dict:
        """
        语义搜索记忆 — Qdrant 向量检索 + PostgreSQL 元数据过滤。

        流程:
        1. 将 query 转为 embedding
        2. 在 Qdrant 中搜索 Top-K*3 条候选
        3. 回 PostgreSQL 加载完整 Memory 对象
        4. 按元数据条件过滤
        5. 返回 Top-K 条

        status: 不传或传空列表时默认只查 active；传具体值时按传入列表过滤。
        max_content_length: 传入时截断 content 字段，不传则返回完整内容。
        """
        import time as time_module
        start = time_module.perf_counter()

        # Step 1: Embed query
        try:
            query_vec = await self.embedding.embed_single(query)
        except Exception as e:
            logger.warning(f"Embedding failed for search, falling back to DB-only: {e}")
            return await self._db_only_search(
                query=query, user_id=user_id, db=db,
                agent_id=agent_id,
                scene_id=scene_id, task_id=task_id, session_id=session_id,
                memory_types=memory_types, status=status,
                max_content_length=max_content_length,
                time_start=time_start, time_end=time_end,
                top_k=top_k,
            )

        # Step 2: Qdrant search
        candidate_ids = set()
        qdrant_scores: dict[str, float] = {}
        if self.qdrant.is_available:
            try:
                from app.services.vector_store import vector_store
                hits = await vector_store.search(
                    query_vector=query_vec,
                    user_id=user_id,
                    top_k=top_k * 3,
                    score_threshold=0.50,
                )
                for h in hits:
                    candidate_ids.add(h["memory_id"])
                    qdrant_scores[h["memory_id"]] = h["score"]
            except Exception as e:
                logger.warning(f"vector search failed: {e}")

        # Step 3: PostgreSQL query with metadata filters
        stmt = select(Memory).where(Memory.user_id == user_id)
        stmt = self._apply_status_filter(stmt, status)

        if scene_id:
            stmt = stmt.where(Memory.scene_id == scene_id)
        if task_id:
            stmt = stmt.where(Memory.task_id == task_id)
        if session_id:
            stmt = stmt.where(Memory.session_id == session_id)
        if memory_types:
            stmt = stmt.where(Memory.memory_type.in_(memory_types))
        if time_start:
            stmt = stmt.where(Memory.created_at >= time_start)
        if time_end:
            stmt = stmt.where(Memory.created_at <= time_end)

        # If we have Qdrant candidates, filter by those IDs
        if candidate_ids:
            stmt = stmt.where(Memory.memory_id.in_(candidate_ids))

        stmt = stmt.order_by(Memory.created_at.desc()).limit(top_k * 3)

        result = await db.execute(stmt)
        memories = list(result.scalars().all())

        # Step 4: Build results with scores
        results = []
        for mem in memories:
            score = qdrant_scores.get(mem.memory_id, 0.0)
            raw_content = mem.content or ""
            results.append({
                "memory_id": mem.memory_id,
                "content": self._truncate_text(raw_content, max_content_length),
                "summary": mem.summary or "",
                "key_points": mem.key_points or [],
                "relevance_score": round(score, 4) if score > 0 else None,
                "memory_type": mem.memory_type or "unknown",
                "tags": mem.tags or [],
                "entities": mem.entities or [],
                "importance": float(mem.importance or 0.5),
                "confidence": float(mem.confidence or 0.5),
                "agent_id": mem.agent_id,
                "source_type": mem.source_type or "extracted",
                "scene_id": mem.scene_id,
                "task_id": mem.task_id,
                "session_id": mem.session_id,
                "status": mem.status,
                "version": mem.version,
                "created_at": mem.created_at.isoformat() if mem.created_at else None,
                "updated_at": mem.updated_at.isoformat() if mem.updated_at else None,
            })

        # Sort: Qdrant scores first (descending), then by created_at
        results.sort(
            key=lambda r: (
                -(r["relevance_score"] or 0),
                r.get("created_at") or "",
            )
        )

        total = len(results)
        results = results[:top_k]

        elapsed = int((time_module.perf_counter() - start) * 1000)

        # fire-and-forget 写入检索日志
        filter_conditions = {
            "scene_id": scene_id,
            "task_id": task_id,
            "session_id": session_id,
            "memory_types": memory_types,
            "status": status,
            "time_start": time_start.isoformat() if time_start else None,
            "time_end": time_end.isoformat() if time_end else None,
            "top_k": top_k,
        }
        request_id = f"retr_{uuid4().hex[:24]}"
        asyncio.create_task(
            _log_retrieval(
                request_id=request_id,
                agent_id=agent_id,
                user_id=user_id,
                query=query,
                filter_conditions=filter_conditions,
                top_k=top_k,
                results=results,
                retrieval_mode="hybrid",
            )
        )

        return {
            "query": query,
            "results": results,
            "total_candidates": total,
            "elapsed_ms": elapsed,
        }

    async def _db_only_search(
        self,
        query: str,
        user_id: str,
        db: AsyncSession,
        agent_id: Optional[str] = None,
        scene_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        memory_types: Optional[list[str]] = None,
        status: Optional[list[str]] = None,
        max_content_length: Optional[int] = None,
        time_start: Optional[datetime] = None,
        time_end: Optional[datetime] = None,
        top_k: int = 10,
    ) -> dict:
        """纯 DB 检索（Qdrant 不可用时的降级方案）— 基于关键词 LIKE 匹配。"""
        import time as time_module
        start = time_module.perf_counter()

        stmt = select(Memory).where(Memory.user_id == user_id)
        stmt = self._apply_status_filter(stmt, status)

        if scene_id:
            stmt = stmt.where(Memory.scene_id == scene_id)
        if task_id:
            stmt = stmt.where(Memory.task_id == task_id)
        if session_id:
            stmt = stmt.where(Memory.session_id == session_id)
        if memory_types:
            stmt = stmt.where(Memory.memory_type.in_(memory_types))
        if time_start:
            stmt = stmt.where(Memory.created_at >= time_start)
        if time_end:
            stmt = stmt.where(Memory.created_at <= time_end)

        stmt = stmt.order_by(Memory.created_at.desc()).limit(top_k * 2)

        result = await db.execute(stmt)
        memories = list(result.scalars().all())

        # 简单关键词匹配排序
        keywords = set(query.lower().split())
        results = []
        for mem in memories:
            content_lower = (mem.content or "").lower()
            hits = sum(1 for kw in keywords if kw in content_lower)
            results.append({
                "memory_id": mem.memory_id,
                "content": self._truncate_text(mem.content or "", max_content_length),
                "summary": mem.summary or "",
                "key_points": mem.key_points or [],
                "relevance_score": round(hits / max(len(keywords), 1), 4),
                "memory_type": mem.memory_type or "unknown",
                "tags": mem.tags or [],
                "entities": mem.entities or [],
                "importance": float(mem.importance or 0.5),
                "confidence": float(mem.confidence or 0.5),
                "agent_id": mem.agent_id,
                "source_type": mem.source_type or "extracted",
                "scene_id": mem.scene_id,
                "task_id": mem.task_id,
                "session_id": mem.session_id,
                "status": mem.status,
                "version": mem.version,
                "created_at": mem.created_at.isoformat() if mem.created_at else None,
                "updated_at": mem.updated_at.isoformat() if mem.updated_at else None,
            })

        results.sort(key=lambda r: -(r["relevance_score"] or 0))
        total = len(results)
        results = results[:top_k]

        elapsed = int((time_module.perf_counter() - start) * 1000)

        # fire-and-forget 写入检索日志（降级路径）
        filter_conditions = {
            "scene_id": scene_id,
            "task_id": task_id,
            "session_id": session_id,
            "memory_types": memory_types,
            "status": status,
            "time_start": time_start.isoformat() if time_start else None,
            "time_end": time_end.isoformat() if time_end else None,
            "top_k": top_k,
        }
        request_id = f"retr_{uuid4().hex[:24]}"
        asyncio.create_task(
            _log_retrieval(
                request_id=request_id,
                agent_id=agent_id,
                user_id=user_id,
                query=query,
                filter_conditions=filter_conditions,
                top_k=top_k,
                results=results,
                retrieval_mode="keyword",
            )
        )

        return {
            "query": query,
            "results": results,
            "total_candidates": total,
            "elapsed_ms": elapsed,
            "fallback": True,
        }

    # ================================================================
    # List
    # ================================================================

    async def list_memories(
        self,
        user_id: str,
        db: AsyncSession,
        scene_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        memory_types: Optional[list[str]] = None,
        memory_scope: Optional[str] = None,
        time_start: Optional[datetime] = None,
        time_end: Optional[datetime] = None,
        status: str = "active",
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """分页列出记忆。"""
        stmt = select(Memory).where(
            Memory.user_id == user_id,
            Memory.status == status,
        )

        if scene_id:
            stmt = stmt.where(Memory.scene_id == scene_id)
        if task_id:
            stmt = stmt.where(Memory.task_id == task_id)
        if session_id:
            stmt = stmt.where(Memory.session_id == session_id)
        if agent_id:
            stmt = stmt.where(Memory.agent_id == agent_id)
        if memory_types:
            stmt = stmt.where(Memory.memory_type.in_(memory_types))
        if memory_scope:
            stmt = stmt.where(Memory.memory_scope == memory_scope)
        if time_start:
            stmt = stmt.where(Memory.created_at >= time_start)
        if time_end:
            stmt = stmt.where(Memory.created_at <= time_end)

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Page
        offset = (page - 1) * page_size
        stmt = stmt.order_by(Memory.created_at.desc()).offset(offset).limit(page_size)
        result = await db.execute(stmt)
        memories = list(result.scalars().all())

        items = []
        for mem in memories:
            items.append({
                "memory_id": mem.memory_id,
                "content": mem.content or "",
                "summary": mem.summary or "",
                "key_points": mem.key_points or [],
                "memory_type": mem.memory_type or "unknown",
                "tags": mem.tags or [],
                "entities": mem.entities or [],
                "importance": float(mem.importance or 0.5),
                "confidence": float(mem.confidence or 0.5),
                "agent_id": mem.agent_id,
                "source_type": mem.source_type or "extracted",
                "status": mem.status,
                "version": mem.version,
                "scene_id": mem.scene_id,
                "task_id": mem.task_id,
                "session_id": mem.session_id,
                "memory_scope": mem.memory_scope or "",
                "created_at": mem.created_at.isoformat() if mem.created_at else None,
                "updated_at": mem.updated_at.isoformat() if mem.updated_at else None,
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ================================================================
    # Count By Scope — 记忆层级分布统计
    # ================================================================

    async def count_by_scope(
        self,
        user_id: str,
        db: AsyncSession,
        scene_id: Optional[str] = None,
        status: str = "active",
    ) -> dict[str, int]:
        """
        按 memory_scope 分组统计用户记忆数量。

        返回 {scope: count}，未出现的 scope 不会出现在 dict 中，调用方负责补齐。
        统计条件与 list_memories 保持一致（默认仅统计 active），确保 stats.total == list.total。
        """
        # 构建过滤条件 — 与 list_memories 相同的 status 语义
        conditions = [Memory.user_id == user_id, Memory.status == status]
        if scene_id:
            conditions.append(Memory.scene_id == scene_id)

        from sqlalchemy import and_
        stmt = (
            select(Memory.memory_scope, func.count().label("count"))
            .where(and_(*conditions))
            .group_by(Memory.memory_scope)
        )

        result = await db.execute(stmt)
        counts: dict[str, int] = {}
        for row in result.fetchall():
            scope = row.memory_scope
            if scope:
                counts[scope] = row.count
        return counts

    # ================================================================
    # Delete All
    # ================================================================

    async def delete_all_memories(
        self,
        user_id: str,
        db: AsyncSession,
        scene_id: Optional[str] = None,
    ) -> dict:
        """清除用户全部记忆（PostgreSQL + Qdrant）。"""
        # 先查询要删除的 memory_ids（用于清理 Qdrant）
        stmt = select(Memory.memory_id).where(Memory.user_id == user_id)
        if scene_id:
            stmt = stmt.where(Memory.scene_id == scene_id)

        result = await db.execute(stmt)
        memory_ids = [row[0] for row in result.fetchall()]

        deleted_count = len(memory_ids)
        logger.info(f"Deleting {deleted_count} memories for user={user_id}")

        # 清理关联表（历史快照 / 关系边）
        from app.models.base import MemoryHistory, MemoryRelation
        if memory_ids:
            await db.execute(delete(MemoryHistory).where(MemoryHistory.memory_id.in_(memory_ids)))
            await db.execute(delete(MemoryRelation).where(MemoryRelation.source_memory_id.in_(memory_ids)))
            await db.execute(delete(MemoryRelation).where(MemoryRelation.target_memory_id.in_(memory_ids)))

        # 删除 PostgreSQL 记录
        delete_stmt = delete(Memory).where(Memory.user_id == user_id)
        if scene_id:
            delete_stmt = delete_stmt.where(Memory.scene_id == scene_id)

        await db.execute(delete_stmt)
        await db.commit()

        # 删除 Qdrant 向量
        if memory_ids and self.qdrant.is_available:
            try:
                self.qdrant.delete_vectors(memory_ids)
                logger.info(f"Deleted {len(memory_ids)} vectors from Qdrant")
            except Exception as e:
                logger.warning(f"Qdrant delete failed (non-fatal): {e}")

        return {
            "deleted_count": deleted_count,
            "message": f"成功删除 {deleted_count} 条记忆",
        }

    # ================================================================
    # Context
    # ================================================================

    async def get_context(
        self,
        query: str,
        user_id: str,
        db: AsyncSession,
        agent_id: Optional[str] = None,
        scene_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        max_tokens: int = 3000,
        group_by_type: bool = True,
        top_k: int = 20,
        max_content_length: Optional[int] = 200,
        memory_types: Optional[list[str]] = None,
        status: Optional[list[str]] = None,
        include_preferences: bool = True,
        include_facts: bool = True,
        include_task_state: bool = True,
    ) -> dict:
        """
        检索记忆并格式化为 Prompt 上下文。

        先搜索相关记忆，然后按类型分组拼接为自然语言文本。

        top_k: 最大返回条数，默认 20。
        max_content_length: 单条 content 截断长度，默认 200；传 None 不截断。
        memory_types: 精确指定类型时覆盖 include_* 布尔（向前兼容）。
        status: 不传时默认只查 active。
        """
        # 确定要检索的记忆类型 — memory_types 优先，兼容旧的 include_* 布尔
        if memory_types is not None:
            types = memory_types
        else:
            types = []
            if include_preferences:
                types.append("preference")
            if include_facts:
                types.extend(["fact", "constraint", "process"])
            if include_task_state:
                types.extend(["task_state", "decision"])

        # 搜索记忆（带上长度控制参数）
        search_result = await self.search(
            query=query,
            user_id=user_id,
            db=db,
            agent_id=agent_id,
            scene_id=scene_id,
            task_id=task_id,
            session_id=session_id,
            memory_types=types if types else None,
            status=status,
            max_content_length=max_content_length,
            top_k=top_k,
        )

        memories = search_result.get("results", [])

        # 生成格式化文本（传入 max_content_length 替换硬编码 200）
        if group_by_type:
            formatted = self._format_grouped(memories, max_content_length)
        else:
            formatted = self._format_flat(memories, max_content_length)

        # 粗略估算 token 数（中英文混合：约 1.5 字符/token）
        estimated_chars = len(formatted)
        estimated_tokens = max(1, int(estimated_chars / 1.5))

        # 如果超出 max_tokens，截断并重新估算
        if estimated_tokens > max_tokens:
            ratio = max_tokens / estimated_tokens
            truncate_chars = int(estimated_chars * ratio)
            formatted = formatted[:truncate_chars] + "\n...(截断)"
            estimated_tokens = max_tokens

        return {
            "formatted_text": formatted,
            "fragments": memories,
            "memory_count": len(memories),
            "estimated_tokens": estimated_tokens,
        }

    @staticmethod
    def _format_grouped(memories: list[dict], max_content_length: Optional[int] = 200) -> str:
        """按类型分组格式化记忆。"""
        type_labels = {
            "fact": "📋 关键事实",
            "preference": "⭐ 用户偏好",
            "task_state": "📊 任务状态",
            "decision": "🎯 历史决策",
            "constraint": "🔒 约束条件",
            "process": "🔄 流程方法",
        }

        grouped: dict[str, list[dict]] = {}
        for m in memories:
            mt = m.get("memory_type", "fact")
            grouped.setdefault(mt, []).append(m)

        lines = []
        for mt, items in grouped.items():
            label = type_labels.get(mt, f"📌 {mt}")
            lines.append(f"\n## {label}")
            for item in items:
                content = item.get("content", "")
                summary = item.get("summary", "")
                key_points = item.get("key_points", [])
                if summary and summary != content:
                    lines.append(f"- {summary}")
                else:
                    lines.append(f"- {MemoryStore._truncate_text(content, max_content_length)}")
                for kp in key_points[:3]:
                    lines.append(f"  - {kp}")

        return "\n".join(lines).strip()

    @staticmethod
    def _format_flat(memories: list[dict], max_content_length: Optional[int] = 200) -> str:
        """扁平化格式化记忆。"""
        lines = []
        for i, m in enumerate(memories):
            content = m.get("content", "")
            summary = m.get("summary", "")
            text = summary or MemoryStore._truncate_text(content, max_content_length)
            lines.append(f"[{i + 1}] ({m.get('memory_type', 'fact')}) {text}")
        return "\n".join(lines)

    # ================================================================
    # Update
    # ================================================================

    async def update_memory(
        self,
        memory_id: str,
        db: AsyncSession,
        content: Optional[str] = None,
        summary: Optional[str] = None,
        status: Optional[str] = None,
        importance: Optional[float] = None,
        confidence: Optional[float] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """更新单条记忆的部分字段。"""
        result = await db.execute(
            select(Memory).where(Memory.memory_id == memory_id)
        )
        memory = result.scalar_one_or_none()

        if not memory:
            return {"memory_id": memory_id, "updated": False, "reason": "记忆不存在"}

        # 快照旧版本到历史表
        snapshot_memory_history(db, memory, "update")

        if content is not None:
            memory.content = content
        if summary is not None:
            memory.summary = summary
        if status is not None:
            memory.status = status
            if status == "deleted" and memory.deleted_at is None:
                memory.deleted_at = datetime.now(timezone.utc)
            elif status == "active" and memory.deleted_at is not None:
                memory.deleted_at = None
        if importance is not None:
            memory.importance = max(0.0, min(1.0, importance))
        if confidence is not None:
            memory.confidence = max(0.0, min(1.0, confidence))
        if tags is not None:
            memory.tags = tags

        memory.version = (memory.version or 0) + 1
        memory.updated_at = datetime.now(timezone.utc)

        await db.commit()

        # 更新 Qdrant 向量（如果内容变了）
        if content is not None and self.qdrant.is_available:
            try:
                vec = await self.embedding.embed_single(content)
                self.qdrant.upsert_vectors(
                    vectors=[vec],
                    payloads=[{
                        "user_id": memory.user_id,
                        "memory_id": memory_id,
                        "memory_type": memory.memory_type,
                    }],
                    ids=[memory_id],
                )
            except Exception as e:
                logger.warning(f"Qdrant update failed (non-fatal): {e}")

        return {
            "memory_id": memory_id,
            "updated": True,
            "version": memory.version,
        }

    # ================================================================
    # Soft Delete
    # ================================================================

    async def soft_delete(
        self,
        memory_id: str,
        db: AsyncSession,
        reason: Optional[str] = None,
    ) -> dict:
        """软删除单条记忆。"""
        result = await db.execute(
            select(Memory).where(Memory.memory_id == memory_id)
        )
        memory = result.scalar_one_or_none()

        if not memory:
            return {"memory_id": memory_id, "deleted": False, "reason": "记忆不存在"}

        previous_status = memory.status
        memory.status = "deleted"
        memory.deleted_at = datetime.now(timezone.utc)
        memory.updated_at = datetime.now(timezone.utc)

        await db.commit()

        # 从 Qdrant 中删除向量
        if self.qdrant.is_available:
            try:
                self.qdrant.delete_vectors([memory_id])
            except Exception as e:
                logger.warning(f"Qdrant delete failed (non-fatal): {e}")

        # 自动清理：每次软删除后顺手清掉超过14天的已删数据
        purged = await self.purge_deleted(db, older_than_days=14, dry_run=False)

        return {
            "memory_id": memory_id,
            "deleted": True,
            "previous_status": previous_status,
            "auto_purged": purged.get("deleted", 0),
        }

    async def purge_deleted(
        self,
        db: AsyncSession,
        older_than_days: int = 30,
        dry_run: bool = False,
    ) -> dict:
        """
        物理清理软删除超过 N 天的记忆。

        dry_run=True 时只统计不删除。
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        # 统计待清理
        count_stmt = (
            select(func.count())
            .select_from(Memory)
            .where(
                Memory.status == "deleted",
                (Memory.deleted_at.isnot(None)) & (Memory.deleted_at < cutoff)
                | (Memory.deleted_at.is_(None)) & (Memory.updated_at < cutoff),
            )
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        if dry_run or total == 0:
            return {"deleted": 0, "total_candidates": total, "dry_run": dry_run}

        # 物理删除
        delete_stmt = (
            delete(Memory)
            .where(
                Memory.status == "deleted",
                Memory.updated_at < cutoff,
            )
        )
        result = await db.execute(delete_stmt)
        await db.commit()

        deleted_count = result.rowcount

        # 同步清理 Qdrant（尽力而为）
        if self.qdrant.is_available and deleted_count > 0:
            try:
                ids_stmt = (
                    select(Memory.memory_id)
                    .where(
                        Memory.status == "deleted",
                        Memory.updated_at < cutoff,
                    )
                )
                remaining = (await db.execute(ids_stmt)).scalars().all()
                if remaining:
                    self.qdrant.delete_vectors(list(remaining))
            except Exception as e:
                logger.warning(f"Qdrant purge failed (non-fatal): {e}")

        logger.info(f"Purged {deleted_count} deleted memories older than {older_than_days} days")
        return {"deleted": deleted_count, "total_candidates": total, "dry_run": False}


# 模块级单例
memory_store = MemoryStore()
