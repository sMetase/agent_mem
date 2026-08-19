# -*- coding: utf-8 -*-
"""
向量存储抽象层。

业务层只依赖 VectorStore 接口，未来可切换 Qdrant / Oracle 23ai 等实现。
- 语义检索：dense 向量相似度
- 关键词检索：sparse 向量（jieba + 词频，Qdrant IDF modifier 加权）
- 实体检索：实体表 boost（暂不做）

设计（对应《前后端联动开发问题》检索三路 + 存储抽象决策）：
- point id = 确定性映射(memory_id)，payload 存 memory_id → **无桥接表**
- 未来 Oracle 23ai（向量+关系同表）也无需桥接表，接口一致
"""

import asyncio
from abc import ABC, abstractmethod

from app.core.qdrant_client import qdrant_client as _qdrant
from app.services.sparse_encoder import text_to_sparse

RRF_K = 60


def _rrf_fusion(dense_hits: list[dict], sparse_hits: list[dict], k: int = RRF_K) -> list[dict]:
    """RRF（Reciprocal Rank Fusion）融合 dense + sparse 结果，返回归一化到 [0,1] 的排序列表。"""
    scores: dict[str, float] = {}
    for rank, h in enumerate(dense_hits):
        scores[h["memory_id"]] = scores.get(h["memory_id"], 0) + 1.0 / (k + rank + 1)
    for rank, h in enumerate(sparse_hits):
        scores[h["memory_id"]] = scores.get(h["memory_id"], 0) + 1.0 / (k + rank + 1)

    max_rrf = 2.0 / (k + 1)  # dense + sparse 都排名第 1 的最大 RRF
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {"memory_id": mid, "score": round(min(1.0, score / max_rrf), 4)}
        for mid, score in ranked
    ]


class VectorStore(ABC):
    """向量存储抽象接口。"""

    @abstractmethod
    async def insert(
        self,
        memory_id: str,
        vector: list[float],
        metadata: dict,
        content: str = "",
    ) -> None:
        """写入记忆向量（point id 由 memory_id 确定性推导，payload 含 memory_id；content 用于生成 sparse）。"""

    @abstractmethod
    async def search(
        self,
        query_vector: list[float],
        user_id: str,
        top_k: int = 5,
        filters: dict | None = None,
        score_threshold: float = 0.5,
    ) -> list[dict]:
        """语义检索，返回 [{memory_id, score}, ...]。"""

    @abstractmethod
    async def search_keyword(
        self,
        query_text: str,
        user_id: str,
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[dict]:
        """关键词检索，返回 [{memory_id, score}, ...]。"""

    @abstractmethod
    async def hybrid_search(
        self,
        query_vector: list[float],
        query_text: str,
        user_id: str,
        top_k: int = 5,
        filters: dict | None = None,
        score_threshold: float = 0.5,
    ) -> list[dict]:
        """语义 + 关键词 hybrid 检索（RRF 融合），返回 [{memory_id, score}], score 归一化到 [0,1]。"""

    @abstractmethod
    async def delete(self, memory_id: str) -> None:
        """删除记忆向量。"""


class QdrantVectorStore(VectorStore):
    """Qdrant 实现（dense + sparse，point id = UUID5(memory_id)，payload 含 memory_id，无桥接表）。"""

    def __init__(self, client) -> None:
        self._client = client

    async def insert(
        self,
        memory_id: str,
        vector: list[float],
        metadata: dict,
        content: str = "",
    ) -> None:
        sparse = text_to_sparse(content) if content else None
        await asyncio.to_thread(
            self._client.upsert_vectors,
            vectors=[vector],
            payloads=[{**metadata, "memory_id": memory_id}],
            ids=[memory_id],
            sparse_vectors=[sparse] if sparse else None,
        )

    async def search(
        self,
        query_vector: list[float],
        user_id: str,
        top_k: int = 5,
        filters: dict | None = None,
        score_threshold: float = 0.5,
    ) -> list[dict]:
        hits = await asyncio.to_thread(
            self._client.search_similar,
            query_vector=query_vector,
            user_id=user_id,
            top_k=top_k,
            score_threshold=score_threshold,
            payload_filters=filters,
        )
        return [
            {"memory_id": h["payload"].get("memory_id"), "score": h["score"]}
            for h in hits
            if h.get("payload", {}).get("memory_id")
        ]

    async def search_keyword(
        self,
        query_text: str,
        user_id: str,
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[dict]:
        hits = await asyncio.to_thread(
            self._client.search_keyword,
            query_text,
            user_id,
            top_k,
            filters,
        )
        return [
            {"memory_id": h["payload"].get("memory_id"), "score": h["score"]}
            for h in hits
            if h.get("payload", {}).get("memory_id")
        ]

    async def hybrid_search(
        self,
        query_vector: list[float],
        query_text: str,
        user_id: str,
        top_k: int = 5,
        filters: dict | None = None,
        score_threshold: float = 0.5,
    ) -> list[dict]:
        dense_hits = await self.search(query_vector, user_id, top_k, filters, score_threshold)
        sparse_hits = await self.search_keyword(query_text, user_id, top_k, filters)
        return _rrf_fusion(dense_hits, sparse_hits)[:top_k]

    async def delete(self, memory_id: str) -> None:
        await asyncio.to_thread(self._client.delete_vectors, [memory_id])


# 模块级单例
vector_store = QdrantVectorStore(_qdrant)
