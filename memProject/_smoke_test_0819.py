# -*- coding: utf-8 -*-
"""冒烟测试（2026-08-19 改动后）：健康/登录/实体/写入(Kafka)/检索(hybrid)/上下文/generate废弃。"""
import time
import httpx

BASE = "http://127.0.0.1:8000"
c = httpx.Client(base_url=BASE, timeout=30)
PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  [PASS] {name}")
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name} {detail}")


print("=== A. 健康检查 + 登录 ===")
r = c.get("/health")
check("A1 /health", r.status_code == 200 and r.json().get("status") == "ok", r.text[:100])
r = c.get("/api/v1/health")
check("A2 /api/v1/health 含 app/version/database", r.status_code == 200 and "app" in r.json() and "version" in r.json() and "database" in r.json(), r.text[:100])

r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
check("A3 admin 登录", r.status_code == 200 and r.json()["data"]["user_id"], r.text[:100])

r = c.post("/api/v1/auth/login", json={"username": "smoke_newuser", "password": "pass123"})
check("A4 新用户自动注册", r.status_code == 200 and r.json()["data"]["user_id"], r.text[:100])

r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
check("A5 错误密码 401", r.status_code == 401, f"status={r.status_code}")

print("\n=== B. 实体管理 ===")
r = c.post("/api/v1/scene", json={"scene_name": "smoke测试场景", "description": "test"})
scene_id = r.json()["data"]["scene_id"]
check("B1 创建场景", r.status_code == 201 and scene_id, r.text[:100])

r = c.post("/api/v1/agent/register", json={"agent_name": "smoke测试agent", "scene_id": scene_id, "permissions": ["read", "write"]})
agent_id = r.json()["data"]["agent_id"]
api_key = r.json()["data"]["api_key"]
check("B2 注册 agent 拿 key", r.status_code == 201 and api_key, r.text[:100])
hdr = {"X-API-Key": api_key, "X-User-Id": "smoke_user", "X-Agent-Id": agent_id}

print("\n=== C. 写入链路（Kafka）===")
r = c.post("/api/v1/memory/write", json={
    "user_id": "smoke_user", "scene_id": scene_id, "session_id": "smoke_sess_1",
    "interaction_type": "dialogue",
    "messages": [
        {"role": "user", "content": "订单DH001需要退货退款，退款3个工作日到账"},
        {"role": "assistant", "content": "好的，已为您提交退货申请"},
    ],
}, headers=hdr)
check("C1 write 返回 accepted", r.status_code == 200 and r.json()["data"].get("accepted"), r.text[:200])
l0_count = r.json()["data"].get("l0_count", 0)
check("C2 l0_count=2", l0_count == 2, f"l0_count={l0_count}")

print("\n=== D. 等 L1 worker 抽取（轮询+超时）===")
found = False
for _ in range(18):  # 最多 90s
    time.sleep(5)
    r = c.post("/api/v1/memory/list", params={"user_id": "smoke_user"}, headers=hdr)
    items = r.json().get("data", {}).get("items", [])
    if items:
        found = True
        break
check("D1 L1 抽取成功（list 非空）", found, f"list items={items if 'items' in locals() else 'N/A'}")

print("\n=== E. 检索（hybrid + 关键词）===")
r = c.post("/api/v1/memory/search", json={
    "query": "DH001", "user_id": "smoke_user", "scene_id": scene_id, "top_k": 5,
}, headers=hdr)
results = r.json().get("data", {}).get("results", [])
check("E1 关键词 DH001 字面命中", r.status_code == 200 and len(results) > 0 and any("DH001" in (x.get("content") or "") for x in results), f"results={len(results)}")

r = c.post("/api/v1/memory/search", json={
    "query": "用户退货", "user_id": "smoke_user", "scene_id": scene_id, "top_k": 5,
}, headers=hdr)
results2 = r.json().get("data", {}).get("results", [])
check("E2 语义检索命中", r.status_code == 200 and len(results2) > 0, f"results={len(results2)}")

print("\n=== F. 上下文（hybrid）===")
r = c.post("/api/v1/memory/context", json={
    "query": "DH001", "user_id": "smoke_user", "scene_id": scene_id,
}, headers=hdr)
data = r.json().get("data", {})
formatted = data.get("formatted_text", "")
check("F1 context 字面召回 DH001", r.status_code == 200 and "DH001" in formatted, f"formatted={formatted[:80]}")

print("\n=== G. 记忆管理 ===")
r = c.get("/api/v1/memory/stats", params={"user_id": "smoke_user"}, headers=hdr)
check("G1 stats 返回 total", r.status_code == 200 and "total" in r.json().get("data", {}), r.text[:100])

print("\n=== H. generate 废弃 ===")
r = c.post("/api/v1/memory/generate", json={"text": "测试", "user_id": "smoke_user"}, headers=hdr)
check("H1 /memory/generate 404", r.status_code == 404, f"status={r.status_code}")

print(f"\n===== 结果: PASS={len(PASS)} FAIL={len(FAIL)} =====")
if FAIL:
    print("失败项:", FAIL)
