# -*- coding: utf-8 -*-
"""验证 /memory/delete 是否 500（前后端问题 #4）。"""
import httpx

BASE = "http://127.0.0.1:8000"
c = httpx.Client(base_url=BASE, timeout=30)

# 1. 创建 scene
r = c.post("/api/v1/scene", json={"scene_name": "delete测试场景", "description": "test"})
print(f"[1] 创建 scene: {r.status_code} {r.json()}")
scene_id = r.json()["data"]["scene_id"]

# 2. 注册 agent
r = c.post("/api/v1/agent/register", json={
    "agent_name": "delete测试agent", "scene_id": scene_id, "permissions": ["read", "write"],
})
print(f"[2] 注册 agent: {r.status_code}")
data = r.json()["data"]
agent_id, api_key = data["agent_id"], data["api_key"]
headers = {"X-API-Key": api_key, "X-User-Id": "user_delete_test", "X-Agent-Id": agent_id}

# 3. 同步生成一条记忆（拿 memory_id）
r = c.post("/api/v1/memory/generate", json={
    "text": "用户偏好使用 Python 开发", "user_id": "user_delete_test", "scene_id": scene_id,
}, headers=headers)
print(f"[3] generate: {r.status_code}")
gen_data = r.json().get("data", {})
memory_ids = gen_data.get("memory_ids", [])
if not memory_ids:
    # generate 可能无记忆，降级：直接用 list 找一条已有记忆
    r2 = c.post("/api/v1/memory/list", params={"user_id": "user_delete_test"}, headers=headers)
    items = r2.json().get("data", {}).get("items", [])
    if items:
        memory_ids = [items[0]["memory_id"]]
print(f"    memory_id 候选: {memory_ids}")

if not memory_ids:
    print("!! 无 memory_id 可删，跳过 delete 测试")
    raise SystemExit(0)

memory_id = memory_ids[0]

# 4. delete 测试（核心）
r = c.delete("/api/v1/memory/delete", json={"memory_id": memory_id}, headers=headers)
print(f"[4] DELETE /memory/delete: {r.status_code}")
print(f"    响应: {r.text[:300]}")

if r.status_code >= 500:
    print(">>> 结论：/memory/delete 确实返回 500，需修复")
else:
    print(f">>> 结论：/memory/delete 正常（{r.status_code}），前端 workaround 可删")
