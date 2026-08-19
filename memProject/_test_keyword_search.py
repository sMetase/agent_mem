# -*- coding: utf-8 -*-
"""关键词检索端到端验证：insert(带 content 生成 sparse) → search_keyword 命中。"""
import asyncio

from app.services.vector_store import vector_store
from app.services.embedding_client import embedding_client


async def main():
    memory_id = "mem_keyword_test"
    user_id = "user_keyword_test"
    content = "用户订单DH001需要退货退款，退款将在3个工作日内到账"

    # 1. insert（带 content 生成 sparse）
    vector = await embedding_client.embed_single(content)
    await vector_store.insert(
        memory_id=memory_id,
        vector=vector,
        metadata={"user_id": user_id, "scene_id": "", "task_id": "", "session_id": ""},
        content=content,
    )
    print(f"[1] insert 完成: {memory_id}")

    # 2. 关键词检索（query 含关键词「DH001」，语义可能不相似，但字面匹配应命中）
    hits = await vector_store.search_keyword(
        query_text="DH001",
        user_id=user_id,
        top_k=5,
    )
    print(f"[2] keyword search 返回 {len(hits)} 条: {[(h['memory_id'], round(h['score'], 3)) for h in hits]}")

    # 3. 确认命中（关键词「DH001」字面匹配）
    found = [h for h in hits if h["memory_id"] == memory_id]
    assert found, "关键词检索未命中 —— sparse 检索失败"
    print(f"[3] 验证通过：关键词检索命中 {memory_id}，score={round(found[0]['score'], 3)}")

    # 4. 清理
    await vector_store.delete(memory_id)
    print("[4] 清理完成")


if __name__ == "__main__":
    asyncio.run(main())
