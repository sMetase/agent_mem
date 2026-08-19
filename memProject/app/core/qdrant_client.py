# -*- coding: utf-8 -*-
"""
Qdrant Client 单例 — 复用 gRPC 连接模式进行向量存储与检索。

与 mem0_client.py 中的 QdrantClient 模式一致：gRPC 端口 6334。
"""
import uuid
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    Modifier,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.core.exceptions import VectorStoreError
from app.core.logger import get_logger

logger = get_logger("qdrant_client")


def _str_to_uuid(s: str) -> str:
    """将字符串 ID 转换为合法的 UUID 格式（基于 uuid5）。"""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, s))

QDRANT_HOST = "localhost"
QDRANT_GRPC_PORT = 6333
COLLECTION_NAME = "agent_mem_generation"  # 独立 collection，不影响 mem0 的 openmemory
VECTOR_DIM = 1024  # bge-m3 维度
DEFAULT_SCORE_THRESHOLD = 0.5


class QdrantClientSingleton:
    """Qdrant gRPC 客户端单例，用于记忆去重的向量检索。"""

    def __init__(self) -> None:
        self._client: Optional[QdrantClient] = None
        self._collection_name: str = COLLECTION_NAME

    def initialize(self) -> bool:
        """初始化 Qdrant gRPC 连接并确保 collection 存在。"""
        try:
            self._client = QdrantClient(host=QDRANT_HOST, port=QDRANT_GRPC_PORT, prefer_grpc=False, timeout=10)

            # 确保 collection 存在
            collections = self._client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self._collection_name not in collection_names:
                self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
                    sparse_vectors_config={"keyword": SparseVectorParams(modifier=Modifier.IDF)},
                )
                logger.info(f"Qdrant collection '{self._collection_name}' created (dim={VECTOR_DIM}, sparse=keyword/IDF)")
            else:
                # 验证维度
                info = self._client.get_collection(self._collection_name)
                actual_dim = info.config.params.vectors.size
                if actual_dim != VECTOR_DIM:
                    logger.warning(
                        f"Qdrant collection '{self._collection_name}' dim mismatch: "
                        f"expected {VECTOR_DIM}, got {actual_dim}. Recreating."
                    )
                    self._client.delete_collection(self._collection_name)
                    self._client.create_collection(
                        collection_name=self._collection_name,
                        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
                        sparse_vectors_config={"keyword": SparseVectorParams(modifier=Modifier.IDF)},
                    )

            logger.info(f"Qdrant client initialized: {QDRANT_HOST}:{QDRANT_GRPC_PORT}, collection='{self._collection_name}'")
            return True
        except Exception as e:
            logger.error(f"Qdrant initialization failed: {e}")
            return False

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            if not self.initialize():
                raise VectorStoreError("Qdrant 客户端初始化失败")
        return self._client

    @property
    def is_available(self) -> bool:
        if self._client is not None:
            # 校验 collection 仍存在（防止外部清库后 client 静默失效）
            try:
                names = [c.name for c in self._client.get_collections().collections]
                if self._collection_name in names:
                    return True
                logger.warning(f"Qdrant collection '{self._collection_name}' 不存在，重新初始化")
                self._client = None
            except Exception:
                logger.warning("Qdrant collection 校验失败，重置客户端")
                self._client = None
        # 惰性初始化
        return self.initialize()

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def search_similar(
        self,
        query_vector: list[float],
        user_id: str,
        top_k: int = 5,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        payload_filters: dict | None = None,
    ) -> list[dict]:
        """
        按语义相似度检索最相近的记忆向量。

        Args:
            query_vector: 查询向量 (1024 维)
            user_id: 限定用户范围
            top_k: 返回 Top-K 条
            score_threshold: 最低相似度阈值
            payload_filters: 额外的 payload 过滤条件 {scene_id, task_id, session_id}

        Returns:
            [{"id": str, "score": float, "payload": dict}, ...]
        """
        try:
            must_conditions = [
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id),
                )
            ]
            if payload_filters:
                for key, value in payload_filters.items():
                    if value:
                        must_conditions.append(
                            FieldCondition(
                                key=key,
                                match=MatchValue(value=value),
                            )
                        )

            hits = self.client.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                query_filter=Filter(must=must_conditions),
                limit=top_k,
                score_threshold=score_threshold,
            )

            results = [
                {
                    "id": str(hit.id),
                    "score": float(hit.score) if hit.score is not None else 0.0,
                    "payload": hit.payload or {},
                }
                for hit in hits.points
            ]
            logger.info(
                f"Qdrant search: user={user_id}, top_k={top_k}, found={len(results)}"
            )
            return results
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            raise VectorStoreError(f"Qdrant 检索失败: {str(e)}")

    def search_keyword(
        self,
        query_text: str,
        user_id: str,
        top_k: int = 5,
        payload_filters: dict | None = None,
    ) -> list[dict]:
        """
        关键词检索（sparse vector，jieba 分词 + 词频，Qdrant IDF modifier 自动加权）。

        Returns:
            [{"id": str, "score": float, "payload": dict}, ...]
        """
        from app.services.sparse_encoder import text_to_sparse

        sparse = text_to_sparse(query_text)
        if not sparse:
            return []

        sparse_vector = SparseVector(indices=list(sparse.keys()), values=list(sparse.values()))

        try:
            must_conditions = [
                FieldCondition(key="user_id", match=MatchValue(value=user_id))
            ]
            if payload_filters:
                for key, value in payload_filters.items():
                    if value:
                        must_conditions.append(
                            FieldCondition(key=key, match=MatchValue(value=value))
                        )

            hits = self.client.query_points(
                collection_name=self._collection_name,
                query=sparse_vector,
                using="keyword",
                query_filter=Filter(must=must_conditions),
                limit=top_k,
            )

            results = [
                {
                    "id": str(hit.id),
                    "score": float(hit.score) if hit.score is not None else 0.0,
                    "payload": hit.payload or {},
                }
                for hit in hits.points
            ]
            logger.info(f"Qdrant keyword search: user={user_id}, top_k={top_k}, found={len(results)}")
            return results
        except Exception as e:
            logger.error(f"Qdrant keyword search failed: {e}")
            raise VectorStoreError(f"Qdrant 关键词检索失败: {str(e)}")

    def upsert_vectors(
        self,
        vectors: list[list[float]],
        payloads: list[dict],
        ids: list[str],
        sparse_vectors: list[dict] | None = None,
    ) -> None:
        """
        批量写入/更新向量（dense + 可选 sparse）。

        Args:
            vectors: 向量列表（dense）
            payloads: 每个向量的 payload（含 user_id, memory_id 等）
            ids: 每个向量的唯一标识（使用 memory_id）
            sparse_vectors: 可选稀疏向量列表（{词ID: 词频}，用于关键词检索）
        """
        if len(vectors) != len(payloads) or len(vectors) != len(ids):
            raise ValueError("vectors, payloads, ids 长度必须一致")

        try:
            points = []
            for i in range(len(ids)):
                named = {"": vectors[i]}
                if sparse_vectors and i < len(sparse_vectors) and sparse_vectors[i]:
                    sv = sparse_vectors[i]
                    named["keyword"] = SparseVector(
                        indices=list(sv.keys()),
                        values=list(sv.values()),
                    )
                points.append(PointStruct(id=_str_to_uuid(ids[i]), vector=named, payload=payloads[i]))
            self.client.upsert(
                collection_name=self._collection_name,
                points=points,
            )
            logger.info(f"Qdrant upsert: {len(points)} vectors")
        except Exception as e:
            logger.error(f"Qdrant upsert failed: {e}")
            raise VectorStoreError(f"Qdrant 写入失败: {str(e)}")

    def upsert_single(
        self,
        point_id: str,
        vector: list[float],
        payload: dict,
    ) -> None:
        """写入/更新单条向量。"""
        self.upsert_vectors([vector], [payload], [point_id])

    def update_payload(self, point_id: str, payload: dict) -> None:
        """更新单条向量的 payload（不更新向量本身）。"""
        try:
            self.client.set_payload(
                collection_name=self._collection_name,
                payload=payload,
                points=[_str_to_uuid(point_id)],
            )
        except Exception as e:
            logger.error(f"Qdrant update_payload failed: {e}")

    def delete_vectors(self, ids: list[str]) -> None:
        """删除指定 ID 的向量。"""
        try:
            self.client.delete(
                collection_name=self._collection_name,
                points_selector=[_str_to_uuid(id_) for id_ in ids],
            )
            logger.info(f"Qdrant delete: {len(ids)} vectors")
        except Exception as e:
            logger.error(f"Qdrant delete failed: {e}")
            # 删除失败不抛异常（非致命）


# 模块级单例
qdrant_client = QdrantClientSingleton()
