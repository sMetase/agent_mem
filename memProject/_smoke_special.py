# -*- coding: utf-8 -*-
"""专项验证：专项 1（满批续跑 50 条）+ 专项 2（状态记忆 agent 私有 vs 偏好共享）。"""
import asyncio
import sys
import time

import httpx
from sqlalchemy import select, func

from app.core.database import async_session_factory
from app.models.base import InteractionRecord, Memory, MemoryCursor

BASE = "http://127.0.0.1:8000"
TS = str(int(time.time()))[-6:]
PREFIX = f"spec{TS}"

results = []


def check(group, name, passed, detail=""):
    results.append((group, name, passed, detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {group} | {name}" + (f" — {detail}" if detail else ""))


FACTS = [
    "我计划去日本旅行，预算2万元",
    "我想去东京和大阪",
    "我偏好自由行，不喜欢跟团",
    "我想在11月淡季出行避开人流",
    "我喜欢吃日料，特别是寿司",
    "酒店预算每晚500元左右",
    "我打算买JR Pass坐新干线",
    "我想去京都看红叶",
    "旅行时长计划7天",
    "我需要提前办日本签证",
]


async def main():
    user_id = f"{PREFIX}_user"
    async with httpx.AsyncClient(base_url=BASE, timeout=60.0) as c:
        # ============ 专项 1：满批续跑 50 条 ============
        g = "专项1.满批续跑"
        r = await c.post("/api/v1/scene", json={"scene_name": f"{PREFIX}_scene"})
        scene_id = (r.json().get("data") or {}).get("scene_id")
        r = await c.post("/api/v1/agent/register", json={"agent_name": f"{PREFIX}_agent", "scene_id": scene_id, "permissions": []})
        reg = r.json().get("data") or {}
        api_key = reg.get("api_key")
        agent_id = reg.get("agent_id")
        hdr = {"X-API-Key": api_key, "X-User-Id": user_id}
        r = await c.post("/api/v1/session", json={"user_id": user_id, "scene_id": scene_id}, headers=hdr)
        session_id = (r.json().get("data") or {}).get("session_id")

        t0 = time.time()
        for i in range(50):
            r = await c.post("/api/v1/memory/write", json={
                "user_id": user_id, "scene_id": scene_id, "session_id": session_id,
                "interaction_type": "dialogue",
                "messages": [{"role": "user", "content": FACTS[i % 10]}],
            }, headers=hdr)
        check(g, "写入50条", r.status_code == 200, f"第50条 status={r.status_code}")

        print("    … 等待 worker 满批续跑处理 (40s) …")
        await asyncio.sleep(40)
        elapsed = time.time() - t0

        async with async_session_factory() as db:
            cnt_total = (await db.execute(select(func.count()).select_from(InteractionRecord).where(
                InteractionRecord.session_id == session_id))).scalar()
            cnt_processed = (await db.execute(select(func.count()).select_from(InteractionRecord).where(
                InteractionRecord.session_id == session_id, InteractionRecord.status == "processed"))).scalar()
            check(g, "50条L0全processed", cnt_total == 50 and cnt_processed == 50, f"total={cnt_total}, processed={cnt_processed}")

            max_id = (await db.execute(select(func.max(InteractionRecord.id)).where(
                InteractionRecord.session_id == session_id))).scalar()
            cursor_key = f"{user_id}:{agent_id}:{session_id}"
            cur = (await db.execute(select(MemoryCursor).where(MemoryCursor.cursor_key == cursor_key))).scalar_one_or_none()
            last_id = cur.last_processed_id if cur else 0
            check(g, "L1游标推进到第50条", last_id == max_id, f"cursor={last_id}, max_id={max_id}")

            l1_count = (await db.execute(select(func.count()).select_from(Memory).where(
                Memory.session_id == session_id, Memory.status == "active"))).scalar()
            check(g, "L1去重生效(远小于50)", l1_count is not None and 1 <= l1_count < 50, f"L1记忆数={l1_count}")

        check(g, "总耗时<60s(满批续跑)", elapsed < 60, f"elapsed={elapsed:.1f}s")

        # ============ 专项 2：状态记忆隔离 ============
        g = "专项2.状态隔离"
        r = await c.post("/api/v1/agent/register", json={"agent_name": f"{PREFIX}_agentB", "scene_id": scene_id, "permissions": []})
        reg_b = r.json().get("data") or {}
        api_key_b = reg_b.get("api_key")
        agent_id_b = reg_b.get("agent_id")
        hdr_b = {"X-API-Key": api_key_b, "X-User-Id": user_id}
        check(g, "注册同scene agentB", bool(api_key_b) and agent_id_b != agent_id, f"B={agent_id_b}")

        # agent A 用 /generate（不带 extraction_types，可靠创建+向量化）造两条记忆
        r = await c.post("/api/v1/memory/generate", json={
            "text": "执行了数据库迁移，先备份再升级，注意回滚", "user_id": user_id, "scene_id": scene_id,
        }, headers=hdr)
        mem_ids_p = (r.json().get("data") or {}).get("memory_ids", [])
        check(g, "A造process文本记忆", r.status_code == 200 and len(mem_ids_p) >= 1, f"ids={len(mem_ids_p)}")

        r = await c.post("/api/v1/memory/generate", json={
            "text": "用户喜欢喝咖啡，偏好深色主题界面", "user_id": user_id, "scene_id": scene_id,
        }, headers=hdr)
        mem_ids_pref = (r.json().get("data") or {}).get("memory_ids", [])
        check(g, "A造preference文本记忆", r.status_code == 200 and len(mem_ids_pref) >= 1, f"ids={len(mem_ids_pref)}")

        # DB 改 type 保证确定性
        async with async_session_factory() as db:
            for mid in mem_ids_p:
                m = (await db.execute(select(Memory).where(Memory.memory_id == mid))).scalar_one_or_none()
                if m:
                    m.memory_type = "process"
            for mid in mem_ids_pref:
                m = (await db.execute(select(Memory).where(Memory.memory_id == mid))).scalar_one_or_none()
                if m:
                    m.memory_type = "preference"
            await db.commit()

        # B 检索 process → 应看不到
        r = await c.post("/api/v1/memory/search", json={"query": "数据库迁移备份回滚", "user_id": user_id}, headers=hdr_b)
        sj = r.json().get("data") or {}
        b_process = [x for x in sj.get("results", []) if x.get("memory_type") == "process"]
        check(g, "B看不到A的process", len(b_process) == 0, f"B检索到process={len(b_process)}条")

        # A 检索 process → 应能看到
        r = await c.post("/api/v1/memory/search", json={"query": "数据库迁移备份回滚", "user_id": user_id}, headers=hdr)
        sj = r.json().get("data") or {}
        a_process = [x for x in sj.get("results", []) if x.get("memory_type") == "process"]
        check(g, "A能看到自己的process", len(a_process) >= 1, f"A检索到process={len(a_process)}条")

        # B 检索 preference → 应能看到
        r = await c.post("/api/v1/memory/search", json={"query": "喝咖啡深色主题偏好", "user_id": user_id}, headers=hdr_b)
        sj = r.json().get("data") or {}
        b_pref = [x for x in sj.get("results", []) if x.get("memory_type") == "preference"]
        check(g, "B能看到preference", len(b_pref) >= 1, f"B检索到preference={len(b_pref)}条")

    total = len(results)
    passed = sum(1 for _, _, p, _ in results if p)
    print("\n" + "=" * 60)
    print(f"专项测试: {passed}/{total} PASS")
    for grp, name, p, d in results:
        if not p:
            print(f"  FAIL: [{grp}] {name} {d}")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
