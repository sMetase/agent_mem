# -*- coding: utf-8 -*-
"""Kafka 端到端验证：write 投递 → consumer 消费 → 落 L0 → L1 worker 抽取。"""
import asyncio
import json

from aiokafka import AIOKafkaConsumer

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.logger import get_logger
from app.services.l0_store import gen_record_ids, build_l0_records
from app.services.mq_producer import mq_producer

logger = get_logger("test_kafka_e2e")
settings = get_settings()


async def main():
    # 1. 用 producer 投递一条带 record_ids 的消息（模拟 write 投递）
    await mq_producer.start()
    body = {
        "interaction_type": "dialogue",
        "user_id": "user_e2e",
        "agent_id": "agent_e2e",
        "scene_id": "scene_e2e",
        "session_id": "sess_e2e",
        "task_id": None,
        "messages": [
            {"role": "user", "content": "端到端测试：我喜欢用 Python"},
            {"role": "assistant", "content": "好的，已记录"},
        ],
    }
    record_ids = gen_record_ids(2)
    body["record_ids"] = record_ids

    request_id = "req_e2e_test"
    published = await mq_producer.publish_memory_write(
        request_id=request_id, user_id="user_e2e", agent_id="agent_e2e", body_dict=body,
    )
    print(f"[1] producer 投递: published={published}, record_ids={record_ids}")

    # 2. 手动消费这条消息，调用 _dispatch_and_store 落 L0
    consumer = AIOKafkaConsumer(
        settings.kafka.topic_memory_write,
        bootstrap_servers=settings.kafka.bootstrap_servers,
        group_id="test-e2e-consumer-group",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    await consumer.start()

    from app.services.mq_consumer import _dispatch_and_store
    got = False
    for _ in range(10):  # 最多 poll 10 秒
        records = await consumer.getmany(timeout_ms=1000, max_records=10)
        for tp, msgs in records.items():
            for msg in msgs:
                m = msg.value
                if m.get("request_id") == request_id:
                    count = await _dispatch_and_store(
                        m.get("request_id"), m.get("user_id"), m.get("agent_id"), m.get("body"),
                    )
                    print(f"[2] consumer 消费落 L0: count={count}")
                    got = True
                    break
            if got:
                break
        if got:
            break
    await consumer.stop()
    assert got, "未消费到测试消息"
    assert count == 2, f"落 L0 条数错误: {count}"

    # 3. 验证 DB 里 L0 已落库（status=pending_extract）
    from sqlalchemy import select, func
    from app.models.base import InteractionRecord
    async with async_session_factory() as db:
        cnt = (await db.execute(
            select(func.count()).select_from(InteractionRecord)
            .where(InteractionRecord.session_id == "sess_e2e")
        )).scalar()
        print(f"[3] DB 中 sess_e2e 的 L0 条数: {cnt}")
        assert cnt == 2, f"L0 未正确落库: {cnt}"

    # 4. 调用 L1 worker 抽取该 session，验证 pending_extract → L1
    from app.services.l1_worker import _process_group
    full_batch = await _process_group("user_e2e", "agent_e2e", "sess_e2e")
    from sqlalchemy import select as _sel, func as _f
    from app.models.base import Memory
    async with async_session_factory() as db:
        mem_cnt = (await db.execute(
            _sel(_f.count()).select_from(Memory).where(Memory.session_id == "sess_e2e")
        )).scalar()
        l0_processed = (await db.execute(
            _sel(_f.count()).select_from(InteractionRecord)
            .where(InteractionRecord.session_id == "sess_e2e", InteractionRecord.status == "processed")
        )).scalar()
        print(f"[4] L1 抽取结果: L1记忆数={mem_cnt}, L0已处理数={l0_processed}")

    await mq_producer.stop()
    print("\n端到端验证完成：write投递 → consumer落L0 → L1抽取 链路通")


if __name__ == "__main__":
    asyncio.run(main())
