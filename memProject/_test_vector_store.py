# -*- coding: utf-8 -*-
"""存储抽象层端到端验证：insert → search 闭环（验证去桥接表后检索链路可用）。"""
import asyncio

from app.services.vector_store import vector_store
from app.services.embedding_client import embedding_client


async def main():
    memory_id = "mem_e2e_vector_test"
    user_id = "user_vector_test"

    # 1. 写一条记忆向量（point id = UUID5(memory_id)，payload 存 memory_id）
    text = "端到端向量测试：用户偏好使用 Python 开发"
    vector = await embedding_client.embed_single(text)
    await vector_store.insert(
        memory_id=memory_id,
        vector=vector,
        metadata={"user_id": user_id, "scene_id": "", "task_id": "", "session_id": ""},
    )
    print(f"[1] insert 完成: {memory_id}")

    # 2. 语义检索（query 向量 -> search -> 从 payload 拿 memory_id）
    query_vector = await embedding_client.embed_single("用户偏好什么编程语言")
    hits = await vector_store.search(
        query_vector=query_vector,
        user_id=user_id,
        top_k=5,
    )
    print(f"[2] search 返回 {len(hits)} 条: {[(h['memory_id'], round(h['score'], 3)) for h in hits]}")

    # 3. 确认命中刚写入的记忆（memory_id 从 payload 拿正确）
    found = [h for h in hits if h["memory_id"] == memory_id]
    assert found, "检索未命中刚写入的记忆 —— 存储抽象层改造破坏了检索"
    print(f"[3] 验证通过：检索命中 {memory_id}，score={round(found[0]['score'], 3)}")

    # 4. 清理
    await vector_store.delete(memory_id)
    print("[4] 清理完成")


if __name__ == "__main__":
    asyncio.run(main())
