# -*- coding: utf-8 -*-
"""hybrid 检索（RRF 融合）端到端验证：dense + sparse 融合命中。"""
import asyncio

from app.services.vector_store import vector_store
from app.services.embedding_client import embedding_client


async def main():
    user_id = "user_hybrid_test"
    mems = [
        ("mem_hybrid_dh", "订单DH001需要退货退款，退款3个工作日到账"),
        ("mem_hybrid_py", "用户偏好使用Python开发，追求代码简洁"),
    ]

    # 1. insert 两条记忆
    for mid, content in mems:
        vector = await embedding_client.embed_single(content)
        await vector_store.insert(
            memory_id=mid, vector=vector,
            metadata={"user_id": user_id, "scene_id": "", "task_id": "", "session_id": ""},
            content=content,
        )
    print("[1] insert 2 条完成")

    # 2. hybrid 检索（关键词「DH001」，sparse 应命中 mem_hybrid_dh）
    qv1 = await embedding_client.embed_single("DH001")
    hits1 = await vector_store.hybrid_search(
        query_vector=qv1, query_text="DH001", user_id=user_id, top_k=5,
    )
    print(f"[2] hybrid('DH001') 返回: {[(h['memory_id'], h['score']) for h in hits1]}")
    assert hits1 and hits1[0]["memory_id"] == "mem_hybrid_dh", "关键词 DH001 应命中 mem_hybrid_dh"

    # 3. hybrid 检索（语义「用户喜欢什么语言」，dense 应命中 mem_hybrid_py）
    qv2 = await embedding_client.embed_single("用户喜欢什么编程语言")
    hits2 = await vector_store.hybrid_search(
        query_vector=qv2, query_text="用户喜欢什么编程语言", user_id=user_id, top_k=5,
    )
    print(f"[3] hybrid('用户喜欢什么编程语言') 返回: {[(h['memory_id'], h['score']) for h in hits2]}")
    assert hits2 and hits2[0]["memory_id"] == "mem_hybrid_py", "语义应命中 mem_hybrid_py"

    # 4. 清理
    for mid, _ in mems:
        await vector_store.delete(mid)
    print("[4] 验证通过 + 清理完成")


if __name__ == "__main__":
    asyncio.run(main())
