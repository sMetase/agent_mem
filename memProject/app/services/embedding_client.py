# -*- coding: utf-8 -*-
"""
Embedding Client — 直接调用 SiliconFlow OpenAI 兼容 Embedding API。

使用 BAAI/bge-m3 模型生成 1024 维向量，用于语义相似度计算和去重检测。
内置速率限制处理和批量拆分。
"""

import asyncio
import asyncio
import json
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

from app.core.exceptions import LLMServiceError
from app.core.logger import get_logger

logger = get_logger("embedding_client")

# SiliconFlow 配置（优先从环境变量读取）
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDER_MODEL", "BAAI/bge-m3")
EMBEDDING_DIMENSION = 1024
MAX_BATCH_SIZE = 32  # SiliconFlow 单次 API 调用最大文本数
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0


class EmbeddingClient:
    """SiliconFlow Embedding 客户端（OpenAI 兼容协议）。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or SILICONFLOW_API_KEY
        self._base_url = (base_url or SILICONFLOW_BASE_URL).rstrip("/")
        self._model = model or EMBEDDING_MODEL
        self._http: Optional[httpx.AsyncClient] = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _call_api(self, texts: list[str]) -> list[list[float]]:
        """单次 API 调用，返回嵌入向量列表。"""
        payload = {
            "model": self._model,
            "input": texts,
            "encoding_format": "float",
        }
        url = f"{self._base_url}/embeddings"

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await self.http.post(url, json=payload)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "5"))
                    logger.warning(
                        f"Embedding rate limited (429), waiting {retry_after}s (attempt {attempt}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                data = response.json()
                embeddings = [
                    item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])
                ]
                logger.info(
                    f"Embedding: {len(texts)} texts → {len(embeddings)} vectors, dim={len(embeddings[0]) if embeddings else '?'}"
                )
                return embeddings

            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"Embedding HTTP error (attempt {attempt}/{MAX_RETRIES}): {e.response.status_code}"
                )
                if attempt == MAX_RETRIES:
                    raise LLMServiceError(
                        f"SiliconFlow Embedding API 错误 (status={e.response.status_code}): {e.response.text[:500]}"
                    )
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            except (httpx.RequestError, json.JSONDecodeError, KeyError, IndexError) as e:
                logger.warning(f"Embedding request error (attempt {attempt}/{MAX_RETRIES}): {e}")
                if attempt == MAX_RETRIES:
                    raise LLMServiceError(f"SiliconFlow Embedding API 请求失败: {str(e)}")
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))

        raise LLMServiceError("SiliconFlow Embedding API 不可达，已达最大重试次数")

    async def embed_single(self, text: str) -> list[float]:
        """生成单个文本的嵌入向量（1024 维）。"""
        results = await self._call_api([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        批量生成嵌入向量。自动拆分超过 MAX_BATCH_SIZE 的批次。

        Args:
            texts: 文本列表

        Returns:
            与 texts 顺序对应的嵌入向量列表
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), MAX_BATCH_SIZE):
            batch = texts[i : i + MAX_BATCH_SIZE]
            embeddings = await self._call_api(batch)
            all_embeddings.extend(embeddings)

            if i + MAX_BATCH_SIZE < len(texts):
                # 批次间隔少量延迟，避免触发速率限制
                await asyncio.sleep(0.2)

        return all_embeddings


# 模块级单例
embedding_client = EmbeddingClient()
