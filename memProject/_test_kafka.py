# -*- coding: utf-8 -*-
"""Kafka 改造验证脚本：Kafka 连接 / PG 连接 / persist_l0 幂等。"""
import asyncio

from app.core.logger import get_logger

logger = get_logger("test_kafka")


async def test_kafka_connection():
    """验证 Kafka producer 能连上 + 投递一条测试消息。"""
    from app.services.mq_producer import mq_producer
    await mq_producer.start()
    print(f"[Kafka] is_available={mq_producer.is_available}")
    if mq_producer.is_available:
        ok = await mq_producer.publish_memory_write(
            request_id="test_req_kafka_conn",
            user_id="test_user",
            agent_id="test_agent",
            body_dict={
                "interaction_type": "dialogue",
                "messages": [{"role": "user", "content": "连接测试"}],
                "record_ids": ["rec_kafka_conn_1"],
                "session_id": "sess_conn",
            },
        )
        print(f"[Kafka] publish_memory_write={ok}")
    await mq_producer.stop()


async def test_persist_idempotent():
    """验证 persist_l0 幂等：相同 record_id 第二次 ON CONFLICT 跳过。"""
    from app.core.database import async_session_factory
    from app.services.l0_store import build_l0_records, persist_l0, gen_record_ids

    body = {
        "interaction_type": "dialogue",
        "messages": [{"role": "user", "content": "幂等测试"}],
    }
    record_ids = gen_record_ids(1)
    records = build_l0_records(
        body, user_id="u_idem", agent_id="a_idem", scene_id="s_idem",
        session_id="sess_idem", task_id=None, record_ids=record_ids,
    )

    async with async_session_factory() as db:
        c1 = await persist_l0(db, records)
        await db.commit()
        c2 = await persist_l0(db, records)  # 相同 record_id，应被 ON CONFLICT 跳过
        await db.commit()
        print(f"[persist] 第一次落库={c1}, 第二次(应=0)={c2}")
        assert c1 == 1 and c2 == 0, f"幂等失败: c1={c1}, c2={c2}"
        print("[persist] 幂等验证通过：重复 record_id 不重复落库")


async def main():
    try:
        await test_kafka_connection()
    except Exception as e:
        print(f"[Kafka] 连接测试异常: {e}")
    try:
        await test_persist_idempotent()
    except Exception as e:
        print(f"[persist] 测试异常: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
