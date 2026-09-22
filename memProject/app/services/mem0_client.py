# -*- coding: utf-8 -*-
"""
mem0 记忆框架封装 — history_store=PG 保持（可选），vector_store=Oracle 26ai(oracledb)。
若当前装的 mem0 版本不支持 oracledb 提供者，初始化会失败并走降级（非致命）。
"""

from typing import Optional

from mem0 import Memory as Mem0Memory

from app.core.config import get_settings
from app.core.exceptions import ServiceDegradedError
from app.core.logger import get_logger

settings = get_settings()
logger = get_logger("mem0_client")


class Mem0Client:

    def __init__(self):
        self._client: Optional[Mem0Memory] = None
        self._initialized = False

    def initialize(self) -> bool:
        try:
            vector_cfg = dict(settings.mem0.vector_store.get("config", {}))
            # Oracle 26ai: provider=oracledb，注入 connection_params（若 config 未显式提供）
            if settings.mem0.vector_store.get("provider") == "oracledb":
                if not vector_cfg.get("connection_params"):
                    db = settings.database
                    service = db.service or db.database
                    vector_cfg["connection_params"] = {
                        "user": db.user,
                        "password": db.password,
                        "dsn": f"{db.host}:{db.port}/{service}",
                    }

            config = {
                "vector_store": {
                    "provider": settings.mem0.vector_store.get("provider", "oracledb"),
                    "config": vector_cfg,
                },
                "history_store": {
                    "provider": settings.mem0.history_store.get("provider", "postgresql"),
                    "config": settings.mem0.history_store.get("config", {}),
                },
                "llm": {
                    "provider": "openai",
                    "config": settings.mem0.llm.get("config", {}),
                },
                "embedder": {
                    "provider": "openai",
                    "config": settings.mem0.embedder.get("config", {}),
                },
            }
            self._client = Mem0Memory.from_config(config_dict=config)
            self._initialized = True
            logger.info("mem0 client initialized successfully")
            return True
        except Exception as e:
            self._initialized = True
            logger.warning(f"mem0 init failed (degraded): {e}")
            return False

    @property
    def client(self) -> Optional[Mem0Memory]:
        if not self._initialized:
            self.initialize()
        return self._client

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def _check(self) -> None:
        if not self.client:
            raise ServiceDegradedError("mem0 未初始化，记忆写入/检索服务降级中")

    def add(self, messages: list[dict], *, user_id: str, agent_id: Optional[str] = None,
                  session_id: Optional[str] = None, metadata: Optional[dict] = None,
                  infer: bool = False) -> list[dict]:
        self._check()
        kwargs = {"user_id": user_id, "metadata": metadata or {}, "infer": infer}
        if agent_id: kwargs["agent_id"] = agent_id
        # session_id 通过 metadata 传递，不传顶层参数（当前 mem0 版本不支持）
        try:
            result = self.client.add(messages, **kwargs)
            logger.info(f"mem0 add: user={user_id}, msgs={len(messages)}")
            return result
        except Exception as e:
            logger.error(f"mem0 add failed: {e}")
            raise ServiceDegradedError(f"mem0 写入失败: {str(e)}")

    def search(self, query: str, *, user_id: str, agent_id: Optional[str] = None,
                     session_id: Optional[str] = None, limit: int = 10,
                     filters: Optional[dict] = None, rerank: bool = False) -> dict:
        self._check()
        f = {"user_id": user_id}
        if filters: f.update(filters)
        try:
            result = self.client.search(query, filters=f, top_k=limit, rerank=rerank)
            logger.info(f"mem0 search: '{query[:50]}...' → {len(result.get('results',[]))} results")
            return result
        except Exception as e:
            logger.error(f"mem0 search failed: {e}")
            raise ServiceDegradedError(f"mem0 检索失败: {str(e)}")

    def update(self, memory_id: str, data: str) -> dict:
        self._check()
        return self.client.update(memory_id, data)

    def delete(self, memory_id: str) -> dict:
        self._check()
        return self.client.delete(memory_id)

    def get(self, memory_id: str) -> dict:
        self._check()
        return self.client.get(memory_id)

    def get_all(self, *, user_id: str, agent_id: Optional[str] = None,
                      session_id: Optional[str] = None) -> list[dict]:
        self._check()
        kwargs = {"user_id": user_id}
        if agent_id: kwargs["agent_id"] = agent_id
        if session_id: kwargs["session_id"] = session_id
        return self.client.get_all(**kwargs)


mem0_client = Mem0Client()
