# -*- coding: utf-8 -*-
"""降级路径验证：Kafka 不可用 → write 降级同步落 L0。"""
import asyncio
import uuid

from sqlalchemy import select, func

from app.core.database import async_session_factory
from app.models.base import InteractionRecord
from app.services.l0_store import gen_record_ids, count_l0_records, build_l0_records, persist_l0
from app.services.mq_producer import mq_producer


async def main():
    user_id = "user_degrade"
    session_id = f"sess_degrade_{uuid.uuid4().hex[:8]}"

    # 1. 启动 producer（Kafka 已停，应不可用）
    await mq_producer.start()
    print(f"[1] Kafka 停止后 is_available={mq_producer.is_available}")

    # 2. 模拟 write 端点逻辑：预生成 record_id → 投递 → 失败降级
    body_dict = {
        "interaction_type": "dialogue",
        "user_id": user_id,
        "agent_id": "agent_degrade",
        "scene_id": "scene_degrade",
        "session_id": session_id,
        "task_id": None,
        "messages": [{"role": "user", "content": "降级测试：Kafka 挂了我也能写"}],
    }
    record_ids = gen_record_ids(count_l0_records(body_dict))
    body_dict["record_ids"] = record_ids

    published = await mq_producer.publish_memory_write(
        request_id=f"req_degrade_{uuid.uuid4().hex[:8]}",
        user_id=user_id,
        agent_id="agent_degrade",
        body_dict=body_dict,
    )
    print(f"[2] publish_memory_write={published}（Kafka 停止，应=False）")
    assert published is False, f"Kafka 停了但 publish 返回 {published}，降级未触发"

    # 3. 降级分支：同步落 L0（与 memory.py 降级逻辑一致）
    async with async_session_factory() as db:
        records = build_l0_records(
            body_dict,
            user_id=user_id, agent_id="agent_degrade",
            scene_id="scene_degrade", session_id=session_id,
            task_id=None, record_ids=record_ids,
        )
        count = await persist_l0(db, records)
        await db.commit()
        print(f"[3] 降级同步落 L0: count={count}")

    # 4. 验证 L0 已落库（status=pending_extract，供 L1 worker 轮询兜底）
    async with async_session_factory() as db:
        cnt = (await db.execute(
            select(func.count()).select_from(InteractionRecord)
            .where(InteractionRecord.session_id == session_id)
        )).scalar()
        print(f"[4] DB 中 {session_id} 的 L0 条数: {cnt}（应=1）")
        assert cnt == 1, f"降级落 L0 失败: {cnt}"

    await mq_producer.stop()
    print("降级路径验证通过：Kafka 不可用 → write 降级同步落 L0")


if __name__ == "__main__":
    asyncio.run(main())
