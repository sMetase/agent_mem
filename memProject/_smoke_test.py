# -*- coding: utf-8 -*-
"""冒烟测试 — 按 冒烟测试方案.md 逐组执行，输出 PASS/FAIL 汇总。

运行前提：服务已启动（uvicorn app.main:app --port 8000），L1/L2/L3 worker 运行。
"""
import asyncio
import sys
import time

import httpx
from sqlalchemy import select, func

BASE = "http://127.0.0.1:8000"
TS = str(int(time.time()))[-6:]
PREFIX = f"smoke{TS}"

results = []  # (group, name, passed, detail)


def check(group, name, passed, detail=""):
    results.append((group, name, passed, detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {group} | {name}" + (f" — {detail}" if detail else ""))


async def main():
    user_id = f"{PREFIX}_user"
    async with httpx.AsyncClient(base_url=BASE, timeout=60.0) as c:
        # ============ Group 1: 健康与监控 ============
        g = "1.健康监控"
        r = await c.get("/health")
        check(g, "GET /health", r.status_code == 200 and r.json().get("status") == "ok", f"status={r.status_code}")

        r = await c.get("/api/v1/health")
        check(g, "GET /api/v1/health", r.status_code == 200 and r.json().get("database") is True, f"status={r.status_code}")

        r = await c.get("/api/v1/monitor/stats")
        j = r.json() if r.status_code == 200 else {}
        layers = (j.get("data") or {}).get("layers", {})
        ok_mon = r.status_code == 200 and all(k in layers for k in ("l1", "l2", "l3"))
        check(g, "GET /monitor/stats", ok_mon, f"status={r.status_code}, layers={list(layers.keys())}")

        # P7 回归：async_write 已废除
        r = await c.post("/api/v1/memory/async_write", json={})
        check(g, "P7 回归 async_write=404", r.status_code == 404, f"status={r.status_code}")

        # ============ Group 2: 实体管理 ============
        g = "2.实体管理"
        # 场景（去鉴权，方案A）
        r = await c.post("/api/v1/scene", json={"scene_name": f"{PREFIX}_scene"})
        scene_id = (r.json().get("data") or {}).get("scene_id")
        check(g, "2.1 POST /scene 无key", r.status_code in (200, 201) and bool(scene_id), f"status={r.status_code}, scene={scene_id}")

        # 智能体注册（拿 api_key）
        r = await c.post("/api/v1/agent/register", json={"agent_name": f"{PREFIX}_agent", "scene_id": scene_id, "permissions": []})
        reg = r.json().get("data") or {}
        api_key = reg.get("api_key")
        agent_id = reg.get("agent_id")
        check(g, "2.6 POST /agent/register", r.status_code == 201 and bool(api_key), f"agent={agent_id}, key={'有' if api_key else '无'}")

        r = await c.post("/api/v1/agent/register", json={"agent_name": "x", "scene_id": "scene_not_exist", "permissions": []})
        check(g, "2.7 register 不存在scene", r.status_code == 404, f"status={r.status_code}")

        hdr = {"X-API-Key": api_key, "X-User-Id": user_id}
        # 会话
        r = await c.post("/api/v1/session", json={"user_id": user_id, "scene_id": scene_id}, headers=hdr)
        session_id = (r.json().get("data") or {}).get("session_id")
        check(g, "2.10 POST /session", r.status_code == 201 and bool(session_id), f"session={session_id}")

        # 任务
        r = await c.post("/api/v1/task", json={"user_id": user_id, "scene_id": scene_id, "title": f"{PREFIX} 任务"}, headers=hdr)
        task_id = (r.json().get("data") or {}).get("task_id")
        check(g, "2.14 POST /task", r.status_code == 201 and bool(task_id), f"task={task_id}")

        # 非法状态转换：先 completed（pending->completed 合法），再 completed->pending 非法
        await c.put(f"/api/v1/task/{task_id}", json={"status": "completed"}, headers=hdr)
        r = await c.put(f"/api/v1/task/{task_id}", json={"status": "pending"}, headers=hdr)
        check(g, "2.16 非法状态转换", r.status_code == 409, f"status={r.status_code}")

        # ============ Group 3: 记忆写入 ============
        g = "3.记忆写入"
        r = await c.post("/api/v1/memory/write", json={
            "user_id": user_id, "scene_id": scene_id, "session_id": session_id,
            "interaction_type": "dialogue",
            "messages": [{"role": "user", "content": "我喜欢用 Python 开发"}, {"role": "assistant", "content": "好的"}],
        }, headers=hdr)
        wj = r.json().get("data") or {}
        check(g, "3.1 dialogue 写2条", r.status_code == 200 and wj.get("l0_count") == 2, f"l0_count={wj.get('l0_count')}")

        r = await c.post("/api/v1/memory/write", json={
            "user_id": user_id, "scene_id": scene_id, "session_id": session_id,
            "interaction_type": "dialogue", "messages": [],
        }, headers=hdr)
        check(g, "3.4 dialogue空messages", r.status_code == 422, f"status={r.status_code}")

        r = await c.post("/api/v1/memory/write", json={
            "user_id": user_id, "scene_id": scene_id, "session_id": session_id,
            "interaction_type": "dialogue",
            "messages": [{"role": "foo", "content": "x"}],
        }, headers=hdr)
        check(g, "3.5 非法role", r.status_code == 422, f"status={r.status_code}")

        r = await c.post("/api/v1/memory/write", json={
            "user_id": user_id, "scene_id": scene_id, "session_id": session_id,
            "interaction_type": "bad_type",
            "messages": [{"role": "user", "content": "x"}],
        }, headers=hdr)
        check(g, "3.6 非法interaction_type", r.status_code == 422, f"status={r.status_code}")

        r = await c.post("/api/v1/memory/write", json={
            "user_id": user_id, "scene_id": scene_id, "interaction_type": "dialogue",
            "messages": [{"role": "user", "content": "x"}],
        }, headers=hdr)
        check(g, "3.7 缺session_id", r.status_code == 422, f"status={r.status_code}")

        # 3.8 无key写 -> 401
        r = await c.post("/api/v1/memory/write", json={"user_id": user_id, "session_id": session_id, "interaction_type": "dialogue", "messages": [{"role": "user", "content": "x"}]})
        check(g, "3.8 无key写=401", r.status_code == 401, f"status={r.status_code}")

        # ============ Group 8: 治理层（鉴权+隔离） ============
        g = "8.治理层"
        # 8.1 无 key 调 write/search/profile -> 401
        r = await c.post("/api/v1/memory/search", json={"query": "test", "user_id": user_id})
        check(g, "8.1 search无key=401", r.status_code == 401, f"status={r.status_code}")
        r = await c.post("/api/v1/memory/profile", json={"user_id": user_id})
        check(g, "8.1 profile无key=401", r.status_code == 401, f"status={r.status_code}")

        # P2 回归：无 key 调 list/update/delete/delete-all -> 401
        r = await c.post("/api/v1/memory/list", params={"user_id": user_id})
        check(g, "P2回归 list无key=401", r.status_code == 401, f"status={r.status_code}")
        r = await c.put("/api/v1/memory/update", json={"memory_id": "mem_x"})
        check(g, "P2回归 update无key=401", r.status_code == 401, f"status={r.status_code}")
        r = await c.request("DELETE", "/api/v1/memory/delete", json={"memory_id": "mem_x"})
        check(g, "P2回归 delete无key=401", r.status_code == 401, f"status={r.status_code}")
        r = await c.post("/api/v1/memory/delete-all", params={"user_id": user_id})
        check(g, "P2回归 delete-all无key=401", r.status_code == 401, f"status={r.status_code}")

        # P3 回归：无 key 调 generate/compress -> 401
        r = await c.post("/api/v1/memory/generate", json={"text": "x", "user_id": user_id})
        check(g, "P3回归 generate无key=401", r.status_code == 401, f"status={r.status_code}")
        r = await c.post("/api/v1/memory/compress", json={"text": "x"})
        check(g, "P3回归 compress无key=401", r.status_code == 401, f"status={r.status_code}")

        # P4 回归：非 admin agent 调 admin -> 403
        r = await c.get("/api/v1/admin/memories", headers=hdr)
        check(g, "P4回归 admin非admin=403", r.status_code == 403, f"status={r.status_code}")

        # ============ Group 4: 异步蒸馏链路（写更多对话，等待 L1->L2->L3） ============
        g = "4.蒸馏链路"
        # 写 3 轮同主题对话（攒够 L1）
        for i, msg in enumerate(["我计划去日本旅行，预算2万", "想去东京和大阪", "偏好自由行"]):
            r = await c.post("/api/v1/memory/write", json={
                "user_id": user_id, "scene_id": scene_id, "session_id": session_id,
                "interaction_type": "dialogue",
                "messages": [{"role": "user", "content": msg}],
            }, headers=hdr)
        check(g, "4.1 write3轮同主题", r.status_code == 200, "写3轮对话")

        print("    … 等待 worker 蒸馏 (35s) …")
        await asyncio.sleep(35)

        # L1: /memory/list 有记忆
        r = await c.post("/api/v1/memory/list", params={"user_id": user_id}, headers=hdr)
        lj = r.json().get("data") or {}
        l1_total = lj.get("total", 0)
        check(g, "4.1 L1抽出记忆", r.status_code == 200 and l1_total > 0, f"L1 total={l1_total}")

        # L3: /profile 返回 persona
        r = await c.post("/api/v1/memory/profile", json={"user_id": user_id}, headers=hdr)
        pj = r.json().get("data") or {}
        persona = pj.get("persona", "")
        check(g, "4.3 L3画像", r.status_code == 200 and bool(persona), f"persona_len={len(persona)}")

        # ============ Group 5: 检索与上下文 ============
        g = "5.检索上下文"
        r = await c.post("/api/v1/memory/search", json={"query": "日本旅行", "user_id": user_id}, headers=hdr)
        sj = r.json().get("data") or {}
        results5 = sj.get("results", [])
        check(g, "5.1 search命中", r.status_code == 200 and len(results5) > 0, f"results={len(results5)}")

        r = await c.post("/api/v1/memory/search", json={"query": "完全不相关的量子引力理论", "user_id": user_id}, headers=hdr)
        sj = r.json().get("data") or {}
        check(g, "5.2 search无匹配", r.status_code == 200, f"results={len(sj.get('results', []))}")

        r = await c.post("/api/v1/memory/context", json={"query": "日本旅行", "user_id": user_id}, headers=hdr)
        cj = r.json().get("data") or {}
        check(g, "5.5 context装配", r.status_code == 200, f"memory_count={cj.get('memory_count')}, tokens={cj.get('estimated_tokens')}")

        # ============ Group 6: 记忆管理 ============
        g = "6.记忆管理"
        # P1 回归：/stats 返回单一稳定结构
        r = await c.get("/api/v1/memory/stats", params={"user_id": user_id}, headers=hdr)
        stj = r.json().get("data") or {}
        has_dist = "level_distribution" in stj and "total" in stj
        check(g, "P1回归 /stats结构", r.status_code == 200 and has_dist, f"total={stj.get('total')}, dist={'有' if has_dist else '无'}")

        # 6.2 update：改一条记忆
        if results5:
            mid = results5[0].get("memory_id")
            r = await c.put("/api/v1/memory/update", json={"memory_id": mid, "importance": 0.9}, headers=hdr)
            check(g, "6.2 update记忆", r.status_code == 200, f"status={r.status_code}")

            # 6.3 delete 软删
            r = await c.request("DELETE", "/api/v1/memory/delete", json={"memory_id": mid}, headers=hdr)
            check(g, "6.3 delete软删", r.status_code == 200, f"status={r.status_code}")
        else:
            check(g, "6.2/6.3 update/delete", False, "无记忆可操作")

        # ============ Group 9: 生成/压缩 ============
        g = "9.生成压缩"
        r = await c.post("/api/v1/memory/generate", json={
            "text": "用户说他喜欢用 Python 开发，项目 deadline 是下周五", "user_id": user_id, "scene_id": scene_id,
        }, headers=hdr)
        gj = r.json().get("data") or {}
        check(g, "9.1 generate", r.status_code == 200 and "new_count" in gj, f"new={gj.get('new_count')}, merged={gj.get('merged_count')}")

        r = await c.post("/api/v1/memory/generate/batch", json={"texts": ["t"*60] * 51, "user_id": user_id}, headers=hdr)
        check(g, "9.3 batch>50", r.status_code == 422, f"status={r.status_code}")

        r = await c.post("/api/v1/memory/compress", json={"text": "这是一个很长的对话内容" * 20}, headers=hdr)
        check(g, "9.5 compress", r.status_code == 200, f"status={r.status_code}")

        # ============ Group 7: 透明代理 ============
        g = "7.透明代理"
        r = await c.post("/proxy/space_001/v1/chat/completions", json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "你好"}],
        }, headers={"x-conversation-id": f"{PREFIX}_conv"})
        pj = r.json() if r.status_code == 200 else {}
        ok_proxy = r.status_code == 200 and "choices" in pj
        check(g, "7.1 proxy首轮", ok_proxy, f"status={r.status_code}, choices={'有' if 'choices' in pj else '无'}")

        r = await c.post("/proxy/space_not_exist/v1/chat/completions", json={"model": "x", "messages": [{"role": "user", "content": "hi"}]})
        check(g, "7.4 proxy未知space", r.status_code == 404, f"status={r.status_code}")

        # ============ Group 10: 管理后台（非 admin 已 403，这里只验证 dashboard 参数校验） ============
        g = "10.管理后台"
        # 注册 admin 权限 agent 测 dashboard 参数校验（dashboard 用 require_admin）
        r = await c.post("/api/v1/agent/register", json={"agent_name": f"{PREFIX}_admin", "scene_id": scene_id, "permissions": ["admin"]})
        admin_key = (r.json().get("data") or {}).get("api_key")
        admin_hdr = {"X-API-Key": admin_key, "X-User-Id": user_id}
        r = await c.get("/api/v1/admin/dashboard", params={"hours": 999}, headers=admin_hdr)
        check(g, "10.4 dashboard非法参数", r.status_code == 400, f"status={r.status_code}")

    # ============ 汇总 ============
    total = len(results)
    passed = sum(1 for _, _, p, _ in results if p)
    failed = [r for r in results if not r[2]]
    print("\n" + "=" * 60)
    print(f"汇总: {passed}/{total} PASS")
    if failed:
        print("失败用例:")
        for grp, name, _, detail in failed:
            print(f"  - [{grp}] {name} {detail}")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
