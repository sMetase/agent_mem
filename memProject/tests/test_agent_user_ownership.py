# -*- coding: utf-8 -*-
"""
智能体归属隔离测试 — 覆盖部署版本用户反馈的问题修复。

背景（用户反馈）：用 API 注册智能体并写记忆后，控制台「智能体管理」页查不到该智能体。
根因：
  1. t_agent 没有 user_id 字段，智能体归属完全依赖 scene_id → t_scene.user_id 间接决定，
     注册接口也没把「注册者 user_id」落库；
  2. 开发模式（AUTH_ENABLED=False）下 X-User-Id 缺失时 get_current_user_id 返回空串，
     端点里 `if user_id and ...` 把归属校验整体跳过，智能体可被注册到任意/无主场景，
     控制台按 user_id 过滤即查不到。

修复（本测试验证）：
  - t_agent.user_id 落库注册者；控制台列表按 Agent.user_id 过滤，旧数据（user_id 为空）
    回退按场景归属 Scene.user_id 兜底
  - get_required_user_id：开发模式无 X-User-Id 时回退默认测试用户 user_dev_default，
    归属校验始终生效

依赖 Oracle 数据库（与 tests/conftest.py 一致）；使用唯一 ID 隔离数据并在测试后清理。
运行（在 memProject 目录，后端依赖已安装且能连上 Oracle）:
    python -m pytest tests/test_agent_user_ownership.py -v
"""

import time
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.v1 import agent as agent_api
from app.api.v1 import scene as scene_api
from app.api.deps import DEFAULT_DEV_USER_ID
from app.middleware.error_handler import register_exception_handlers

API_AGENT = "/api/v1/agent"
API_SCENE = "/api/v1/scene"

# 全模块共用一个事件循环：oracledb 异步连接池绑定在首个事件循环上，
# 若每个测试各自开新 loop，池内连接会报 "Future attached to a different loop"。
pytestmark = pytest.mark.asyncio(loop_scope="module")


# ============================================================
# 测试 App — 只挂 agent / scene 两个路由，避开完整 main.py 的启动副作用
# ============================================================
@pytest.fixture(scope="module")
async def client():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(scene_api.router, prefix="/api/v1/scene")
    app.include_router(agent_api.router, prefix="/api/v1/agent")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ============================================================
# 数据库辅助（同步引擎，与 conftest 一致）
# ============================================================
def _sync_engine():
    from sqlalchemy import create_engine
    from app.core.config import get_settings
    return create_engine(get_settings().database.sync_url)


def _exec_sync(sql: str, params: dict | None = None):
    eng = _sync_engine()
    try:
        with eng.connect() as conn:
            conn.execute(text(sql), params or {})
            conn.commit()
    finally:
        eng.dispose()


def _unique(tag: str) -> str:
    return f"{tag}_{int(time.time())}_{uuid4().hex[:6]}"


def _delete_by_ids(table: str, id_col: str, ids) -> None:
    if not ids:
        return
    placeholders = ", ".join(f":x{i}" for i in range(len(ids)))
    _exec_sync(f"DELETE FROM {table} WHERE {id_col} IN ({placeholders})",
               {f"x{i}": v for i, v in enumerate(ids)})


def _delete_agents(agent_ids) -> None:
    _delete_by_ids("t_agent", "agent_id", agent_ids)


def _delete_scenes(scene_ids) -> None:
    _delete_by_ids("t_scene", "scene_id", scene_ids)


def _insert_scene(scene_id: str, user_id: str | None, scene_name: str = "test场景") -> None:
    _exec_sync(
        "INSERT INTO t_scene (id, scene_id, user_id, scene_name, is_active, created_at, updated_at) "
        "VALUES (:id, :sid, :uid, :name, 1, SYSTIMESTAMP, SYSTIMESTAMP)",
        {"id": f"id_{uuid4().hex[:16]}", "sid": scene_id, "uid": user_id, "name": scene_name},
    )


def _insert_legacy_agent(agent_id: str, scene_id: str, user_id: str | None,
                         agent_name: str = "旧数据智能体") -> None:
    """插入 user_id 为空的历史智能体（迁移前数据），用于验证列表兜底逻辑。"""
    _exec_sync(
        "INSERT INTO t_agent (id, agent_id, agent_name, scene_id, user_id, api_key_hash, "
        "api_key_prefix, is_active, permissions, created_at, updated_at) "
        "VALUES (:id, :aid, :name, :sid, :uid, :hash, :prefix, 1, :perm, SYSTIMESTAMP, SYSTIMESTAMP)",
        {
            "id": f"id_{uuid4().hex[:16]}",
            "aid": agent_id,
            "name": agent_name,
            "sid": scene_id,
            "uid": user_id,
            "hash": f"hash_{uuid4().hex}",
            "prefix": "mem_****",
            "perm": '["read","write"]',
        },
    )


def _headers(user_id: str | None = None) -> dict:
    h = {"Content-Type": "application/json"}
    if user_id is not None:
        h["X-User-Id"] = user_id
    return h


async def _list_agent_ids(client, user_id: str | None = None, scene_id: str | None = None) -> list[str]:
    params = {"page_size": 100}
    if scene_id:
        params["scene_id"] = scene_id
    resp = await client.get(f"{API_AGENT}", headers=_headers(user_id), params=params)
    assert resp.status_code == 200, f"list 失败: {resp.status_code} {resp.text}"
    body = resp.json()
    assert body.get("code") == 0, f"list 返回异常: {body}"
    return [it["agent_id"] for it in body["data"]["items"]]


# ============================================================
# 1. 开发模式无 X-User-Id → 归属默认测试用户（不再静默跳过校验）
# ============================================================
async def test_dev_default_binding_without_header(client):
    scene_ids, agent_ids = [], []
    try:
        # 无 X-User-Id 建场景 → 归属 user_dev_default
        r = await client.post(API_SCENE, headers=_headers(),
                              json={"scene_name": _unique("默认场景")})
        assert r.status_code == 201, f"建场景失败: {r.status_code} {r.text}"
        scene_id = r.json()["data"]["scene_id"]
        scene_ids = [scene_id]

        # 无 X-User-Id 注册智能体 → 归属 user_dev_default
        r = await client.post(f"{API_AGENT}/register", headers=_headers(),
                              json={"agent_name": _unique("默认客服"), "scene_id": scene_id})
        assert r.status_code == 201, f"注册失败: {r.status_code} {r.text}"
        body = r.json()["data"]
        assert body["user_id"] == DEFAULT_DEV_USER_ID
        agent_ids.append(body["agent_id"])

        # 控制台以默认测试用户身份能查到
        assert await _list_agent_ids(client, user_id=DEFAULT_DEV_USER_ID, scene_id=scene_id) == agent_ids
    finally:
        _delete_agents(agent_ids)
        _delete_scenes(scene_ids)


# ============================================================
# 2. 注册绑定注册者 user_id；列表按 user_id 隔离
# ============================================================
async def test_register_binds_caller_and_list_isolates(client):
    uid_a = _unique("user_a")
    uid_b = _unique("user_b")
    scene_ids, agent_ids = [], []
    try:
        # A 建场景
        r = await client.post(API_SCENE, headers=_headers(uid_a),
                              json={"scene_name": _unique("A场景")})
        assert r.status_code == 201, r.text
        scene_id = r.json()["data"]["scene_id"]
        scene_ids = [scene_id]

        # A 在该场景注册智能体
        r = await client.post(f"{API_AGENT}/register", headers=_headers(uid_a),
                              json={"agent_name": _unique("A智能体"), "scene_id": scene_id})
        assert r.status_code == 201, r.text
        body = r.json()["data"]
        assert body["user_id"] == uid_a
        agent_ids.append(body["agent_id"])

        # A 能查到；B 查不到（租户隔离）
        assert await _list_agent_ids(client, user_id=uid_a, scene_id=scene_id) == agent_ids
        assert await _list_agent_ids(client, user_id=uid_b, scene_id=scene_id) == []
    finally:
        _delete_agents(agent_ids)
        _delete_scenes(scene_ids)


# ============================================================
# 3. 无权在他人场景下注册 → 403
# ============================================================
async def test_register_under_other_users_scene_rejected(client):
    uid_a = _unique("user_a")
    uid_b = _unique("user_b")
    scene_ids, agent_ids = [], []
    try:
        r = await client.post(API_SCENE, headers=_headers(uid_a),
                              json={"scene_name": _unique("A场景")})
        assert r.status_code == 201, r.text
        scene_id = r.json()["data"]["scene_id"]
        scene_ids = [scene_id]

        # B 想在 A 的场景下注册 → 403
        r = await client.post(f"{API_AGENT}/register", headers=_headers(uid_b),
                              json={"agent_name": _unique("越权"), "scene_id": scene_id})
        assert r.status_code == 403, f"应拒绝越权注册，实际 {r.status_code}: {r.text}"
    finally:
        _delete_agents(agent_ids)
        _delete_scenes(scene_ids)


# ============================================================
# 4. 无主场景（历史数据）：允许注册，但智能体绑定注册者
# ============================================================
async def test_register_under_unowned_scene_binds_caller(client):
    uid_a = _unique("user_a")
    scene_id = _unique("scene_unowned")
    agent_ids = []
    try:
        # 直接落库一个无主场景（user_id = NULL，模拟迁移前数据）
        _insert_scene(scene_id, user_id=None)
        r = await client.post(f"{API_AGENT}/register", headers=_headers(uid_a),
                              json={"agent_name": _unique("无主场景智能体"), "scene_id": scene_id})
        assert r.status_code == 201, f"无主场景应允许注册: {r.status_code} {r.text}"
        body = r.json()["data"]
        assert body["user_id"] == uid_a
        agent_ids.append(body["agent_id"])

        # A 按自己的 user_id 能查到
        assert await _list_agent_ids(client, user_id=uid_a, scene_id=scene_id) == agent_ids
    finally:
        _delete_agents(agent_ids)
        _delete_scenes([scene_id])


# ============================================================
# 5. 历史智能体（user_id 为空）：列表按场景归属兜底可见
# ============================================================
async def test_legacy_agent_fallback_to_scene_owner(client):
    uid_a = _unique("user_a")
    uid_b = _unique("user_b")
    scene_id = _unique("scene_a")
    agent_id = _unique("agent_legacy")
    try:
        # A 的场景 + 无主历史智能体挂在它下面
        _insert_scene(scene_id, user_id=uid_a)
        _insert_legacy_agent(agent_id, scene_id, user_id=None)

        # A（场景 owner）能看到；B 看不到
        assert await _list_agent_ids(client, user_id=uid_a, scene_id=scene_id) == [agent_id]
        assert await _list_agent_ids(client, user_id=uid_b, scene_id=scene_id) == []
    finally:
        _delete_agents([agent_id])
        _delete_scenes([scene_id])
