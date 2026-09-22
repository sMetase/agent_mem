# -*- coding: utf-8 -*-
"""
pytest 配置 — 确定性测试数据 Fixtures（同步 SQLAlchemy 写入，避免 asyncpg 事件循环冲突）。
"""

import time
from datetime import datetime, timezone
from uuid import uuid4

import pytest


# ============================================================
# DEV 模式测试头
# ============================================================
TEST_AGENT_ID = "agent_test_fixture"
TEST_SCENE_ID = "scene_dev_default"


def _test_headers(user_id: str) -> dict:
    return {
        "X-Agent-Id": TEST_AGENT_ID,
        "X-Scene-Id": TEST_SCENE_ID,
        "X-User-Id": user_id,
        "Content-Type": "application/json",
    }


def _sync_engine():
    from sqlalchemy import create_engine
    from app.core.config import get_settings
    s = get_settings()
    return create_engine(s.database.sync_url)


# ============================================================
# Fixture: Stats 测试数据 — 12 条跨 4 层记忆
# ============================================================

@pytest.fixture(scope="module")
def stats_test_data():
    """
    创建 12 条确定性记忆（同步 SQLAlchemy 直接写入）。
    覆盖 4 种 scope、active/deleted、多种 memory_type。
    测试结束后 DELETE BY user_id 清理。
    """
    import time
    from sqlalchemy import text

    engine = _sync_engine()
    conn = engine.connect()
    trans = conn.begin()

    try:
        uid = f"test_stats_{int(time.time())}_{uuid4().hex[:6]}"
        memory_ids = []

        def _insert(**kw):
            defaults = dict(
                id=f"id_{uuid4().hex[:16]}", memory_id=f"mem_{uuid4().hex[:16]}",
                user_id=uid, agent_id="agent_test_fixture", scene_id="scene_dev_default",
                content="test", memory_type="fact", status="active",
                importance=0.5, confidence=0.5, memory_scope="user",
                source_type="test", created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            defaults.update(kw)
            cols = ", ".join(defaults.keys())
            vals = ", ".join(f":{k}" for k in defaults)
            conn.execute(text(f"INSERT INTO t_memory ({cols}) VALUES ({vals})"), defaults)
            memory_ids.append(defaults["memory_id"])

        # user 层级 4 条
        for i, mt in enumerate(["fact", "preference", "decision", "task_state"]):
            _insert(memory_scope="user", memory_type=mt, content=f"Stats user #{i}")

        # session 层级 3 条
        for i, mt in enumerate(["fact", "task_state", "constraint"]):
            _insert(memory_scope="session", memory_type=mt,
                    session_id=f"sess_{uuid4().hex[:12]}", content=f"Stats session #{i}")

        # task 层级 3 条
        sess = f"sess_{uuid4().hex[:12]}"
        for i, mt in enumerate(["fact", "decision", "constraint"]):
            _insert(memory_scope="task", memory_type=mt,
                    session_id=sess, task_id=f"task_{uuid4().hex[:12]}", content=f"Stats task #{i}")

        # agent 层级 2 条
        for i, mt in enumerate(["fact", "process"]):
            _insert(memory_scope="agent", memory_type=mt,
                    agent_id="agent_other", scene_id="scene_other", content=f"Stats agent #{i}")

        # 第 1 条 deleted
        conn.execute(text("UPDATE t_memory SET status='deleted', deleted_at=SYSTIMESTAMP WHERE memory_id=:mid"),
                     {"mid": memory_ids[0]})

        trans.commit()
        yield uid, _test_headers(uid), memory_ids, 11  # 11 active, 1 deleted

        conn.execute(text(f"DELETE FROM t_memory WHERE user_id='{uid}'"))
        conn.commit()
    finally:
        conn.close()
        engine.dispose()


# ============================================================
# Fixture: Context 测试数据 — 20 条
# ============================================================

@pytest.fixture(scope="module")
def context_test_data():
    """
    创建 20 条确定性记忆用于 Context API 测试。
    覆盖 preference/fact/decision/task_state/低相关/deleted/archived。
    """
    from sqlalchemy import text

    engine = _sync_engine()
    conn = engine.connect()
    trans = conn.begin()

    try:
        uid = f"test_ctx_{int(time.time())}_{uuid4().hex[:6]}"

        def _insert(**kw):
            defaults = dict(
                id=f"id_{uuid4().hex[:16]}", memory_id=f"mem_{uuid4().hex[:16]}",
                user_id=uid, agent_id="agent_test_fixture", scene_id="scene_dev_default",
                content="test", memory_type="fact", status="active",
                importance=0.5, confidence=0.5, memory_scope="user",
                source_type="test", created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            defaults.update(kw)
            cols = ", ".join(defaults.keys())
            vals = ", ".join(f":{k}" for k in defaults)
            conn.execute(text(f"INSERT INTO t_memory ({cols}) VALUES ({vals})"), defaults)

        # 4 preference
        for pref in ["喜欢编程", "喜欢阅读", "偏好Python开发", "偏好敏捷开发流程"]:
            _insert(memory_type="preference", content=pref)

        # 5 fact
        for f in ["用户所在城市北京", "职位软件工程师", "工作经验5年", "学历硕士", "英语流利"]:
            _insert(memory_type="fact", content=f)

        # 3 decision
        for i in range(3):
            _insert(memory_type="decision", content=f"用户决定采用技术方案{i}")

        # 3 task_state
        for i in range(3):
            _insert(memory_type="task_state", content=f"项目{i}当前进度{i*30}%")

        # 3 低相关
        for i in range(3):
            _insert(memory_type="fact", content=f"无关记录{i}", importance=0.1)

        # 1 deleted
        mid_del = f"mem_{uuid4().hex[:16]}"
        _insert(memory_id=mid_del, memory_type="fact", content="已删除记忆", status="deleted")
        conn.execute(text("UPDATE t_memory SET deleted_at=SYSTIMESTAMP WHERE memory_id=:mid"), {"mid": mid_del})

        # 1 archived
        _insert(memory_type="fact", content="归档记忆", status="archived")

        trans.commit()
        yield uid, _test_headers(uid), None

        conn.execute(text(f"DELETE FROM t_memory WHERE user_id='{uid}'"))
        conn.commit()
    finally:
        conn.close()
        engine.dispose()


# ============================================================
# Fixture: P13 测试数据 — 单条记忆
# ============================================================

@pytest.fixture
def p13_test_memory():
    """创建一条确定性记忆用于 P13 删除/恢复测试。"""
    from sqlalchemy import text

    engine = _sync_engine()
    conn = engine.connect()

    try:
        uid = f"test_p13_{int(time.time())}_{uuid4().hex[:6]}"
        mid = f"mem_{uuid4().hex[:16]}"
        conn.execute(text("""
            INSERT INTO t_memory (id, memory_id, user_id, agent_id, scene_id,
                content, memory_type, status, memory_scope, source_type,
                created_at, updated_at)
            VALUES (:id, :mid, :uid, 'agent_test_fixture', 'scene_dev_default',
                'P13测试', 'fact', 'active', 'user', 'test',
                SYSTIMESTAMP, SYSTIMESTAMP)
        """), {"id": f"id_{uuid4().hex[:16]}", "mid": mid, "uid": uid})
        conn.commit()
        yield uid, mid, _test_headers(uid)

        conn.execute(text(f"DELETE FROM t_memory WHERE user_id='{uid}'"))
        conn.commit()
    finally:
        conn.close()
        engine.dispose()
