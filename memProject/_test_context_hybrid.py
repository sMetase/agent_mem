# -*- coding: utf-8 -*-
"""context 接口 hybrid 端到端验证：字面召回「DH001」+ formatted_text 结构不变。"""
import asyncio
import uuid

from sqlalchemy import delete as _delete

from app.core.database import async_session_factory
from app.models.base import Memory
from app.services.vector_store import vector_store
from app.services.embedding_client import embedding_client
from app.services.memory_service import create_memory


async def main():
    user_id = "user_ctx_hybrid"
    memory_id = f"mem_ctx_dh001_{uuid.uuid4().hex[:8]}"

    # 1. 写 T_MEMORY 记忆（content 含「订单DH001」）
    async with async_session_factory() as db:
        await create_memory(db, {
            "memory_id": memory_id,
            "user_id": user_id,
            "scene_id": "scene_ctx",
            "session_id": "sess_ctx",
            "content": "订单DH001需要退货退款，退款3个工作日到账",
            "memory_type": "fact",
            "status": "active",
            "importance": 0.8,
            "confidence": 0.9,
        })
        await db.commit()

    # 2. 写向量（dense + sparse）
    content = "订单DH001需要退货退款，退款3个工作日到账"
    vector = await embedding_client.embed_single(content)
    await vector_store.insert(
        memory_id=memory_id, vector=vector,
        metadata={"user_id": user_id, "scene_id": "scene_ctx", "task_id": "", "session_id": "sess_ctx"},
        content=content,
    )

    # 3. 调 memory_context 端点逻辑（字面查询「DH001」）
    from app.api.v1.memory import memory_context
    from app.schemas.memory import ContextRequest

    async with async_session_factory() as db:
        body = ContextRequest(query="DH001", user_id=user_id, scene_id="scene_ctx")
        class _Req:
            class _State:
                pass
            def __init__(self):
                self.state = self._State()
        request = _Req()
        result = await memory_context(body=body, request=request, db=db, agent_id="agent_ctx")

    data = result["data"] if isinstance(result, dict) else result
    formatted = data.get("formatted_text", "")
    print(f"[1] formatted_text 非空: {bool(formatted)}")
    print(f"[2] formatted_text 内容: {formatted[:100]}")
    print(f"[3] memory_count: {data.get('memory_count')}")
    assert formatted and "DH001" in formatted, "context 未字面召回「DH001」"
    print("[4] 验证通过：context hybrid 字面召回 DH001，formatted_text 结构正常")

    # 4. 清理（T_MEMORY + 向量）
    async with async_session_factory() as db:
        await db.execute(_delete(Memory).where(Memory.memory_id == memory_id))
        await db.commit()
    await vector_store.delete(memory_id)
    print("[5] 清理完成")


if __name__ == "__main__":
    asyncio.run(main())
