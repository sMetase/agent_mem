# -*- coding: utf-8 -*-
"""
MQ 消费者 — AIOKafka Consumer 守护进程（块 A 升级：只落 L0）。

职责（对应《多智能体改造方案》块 A 升级 Kafka）：
  - consume_loop(): 主循环，从 memory.write 消费消息
  - _dispatch_and_store(): 只落 L0（幂等，record_id ON CONFLICT DO NOTHING），不触发抽取
  - 抽取由 L1 worker 游标轮询消费 pending_extract 的 L0（不走 Kafka）
  - 指数退避重试（max 3 次），失败进 DLQ
  - 优雅关闭信号处理

启动方式:
  python -m app.services.mq_consumer
"""

import asyncio
import json
import os
import signal
import sys

# 确保项目根在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.logger import get_logger
from app.models.base import Session
from app.services.l0_store import build_l0_records, persist_l0, ensure_session_title
from app.services.mq_producer import mq_producer as _mq_producer

logger = get_logger("mq_consumer")

settings = get_settings()

# 重试配置
MAX_RETRIES = settings.kafka.max_retries
RETRY_BACKOFF_MS = settings.kafka.retry_backoff_ms


async def consume_loop(stop_event: asyncio.Event | None = None) -> None:
    """
    消费者主循环 — 连接 Kafka、拉取消息、只落 L0。

    Args:
        stop_event: 用于优雅关闭的 asyncio.Event
    """
    if stop_event is None:
        stop_event = asyncio.Event()

    logger.info(f"Kafka Consumer 启动中: {settings.kafka.bootstrap_servers}")

    consumer = AIOKafkaConsumer(
        settings.kafka.topic_memory_write,
        bootstrap_servers=settings.kafka.bootstrap_servers,
        group_id=settings.kafka.consumer_group,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_interval_ms=300000,    # 5 min — 处理可以较慢
        session_timeout_ms=30000,
        heartbeat_interval_ms=10000,
    )

    await consumer.start()
    logger.info("Kafka Consumer 已连接，开始消费...")

    try:
        while not stop_event.is_set():
            # poll 批量消息（非阻塞超时 1s）
            records = await consumer.getmany(timeout_ms=1000, max_records=50)

            for tp, msgs in records.items():
                for msg in msgs:
                    await _process_one_message(msg, consumer)

    except KafkaError as e:
        logger.error(f"Kafka Consumer 异常: {e}")
    except Exception as e:
        logger.error(f"Consumer 未知异常: {e}", exc_info=True)
    finally:
        try:
            await consumer.stop()
        except Exception:
            pass
        logger.info("Kafka Consumer 已关闭")


async def _process_one_message(msg, consumer) -> None:
    """
    处理单条消息 — 只落 L0，含重试逻辑。

    流程:
      1. 解析消息体
      2. 调用 _dispatch_and_store() 落 L0
      3. 如果失败：指数退避重试（最多 3 次）
      4. 3 次仍失败：投递 DLQ
      5. 手动提交 offset
    """
    message = msg.value
    request_id = message.get("request_id", "unknown")
    user_id = message.get("user_id", "unknown")
    agent_id = message.get("agent_id", "")
    body = message.get("body", {})

    logger.info(f"收到消息: request_id={request_id}, offset={msg.offset}")

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            count = await _dispatch_and_store(request_id, user_id, agent_id, body)
            logger.info(f"消息处理完成: request_id={request_id}, l0_count={count}")
            await consumer.commit()
            return  # 成功，退出重试循环

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                backoff = RETRY_BACKOFF_MS * (2 ** attempt) / 1000.0
                logger.warning(
                    f"消息处理失败 (attempt={attempt + 1}/{MAX_RETRIES}): "
                    f"request_id={request_id}, error={e}, backoff={backoff}s"
                )
                await asyncio.sleep(backoff)
            else:
                logger.error(
                    f"消息处理全部重试失败: request_id={request_id}, "
                    f"max_retries={MAX_RETRIES}, error={e}"
                )

    # 全部重试失败 → 投递 DLQ
    await _mq_producer.publish_to_dlq(
        request_id=request_id,
        user_id=user_id,
        body_dict=body,
        error=str(last_error),
        retries=MAX_RETRIES,
    )

    # 即使失败也提交 offset（避免阻塞后续消息）
    try:
        await consumer.commit()
    except Exception:
        pass


async def _dispatch_and_store(
    request_id: str,
    user_id: str,
    agent_id: str,
    body: dict,
) -> int:
    """
    只落 L0（幂等），不触发抽取。

    body 为 write 侧投递的 MemoryWriteRequest 全量字典，含 record_ids。
    record_id 由 write 侧预生成，ON CONFLICT DO NOTHING 保证重复消费幂等。

    Returns:
        实际落库条数
    """
    record_ids = body.get("record_ids") or []

    async with async_session_factory() as session:
        records = build_l0_records(
            body,
            user_id=body.get("user_id") or user_id,
            agent_id=body.get("agent_id") or agent_id,
            scene_id=body.get("scene_id"),
            session_id=body.get("session_id") or "",
            task_id=body.get("task_id"),
            record_ids=record_ids,
        )
        count = await persist_l0(session, records)

        # 更新 T_SESSION.message_count（Session 不存在时用真实归属字段创建）
        await _update_session_count(
            session,
            body.get("session_id"),
            count,
            user_id=body.get("user_id") or user_id,
            agent_id=body.get("agent_id") or agent_id,
            scene_id=body.get("scene_id"),
            task_id=body.get("task_id"),
        )

        # 首次落 L0 时生成会话 title（title 为空才设置）
        await ensure_session_title(session, body.get("session_id") or "", body.get("messages") or [])

        await session.commit()

    return count


async def _update_session_count(
    session,
    session_id_val: str,
    inc: int,
    user_id: str = "",
    agent_id: str | None = None,
    scene_id: str | None = None,
    task_id: str | None = None,
) -> None:
    """更新 T_SESSION.message_count；Session 不存在时用真实归属字段创建。"""
    from sqlalchemy import select, update
    result = await session.execute(
        select(Session.id, Session.message_count).where(
            Session.session_id == session_id_val
        ).limit(1)
    )
    row = result.first()
    if row:
        new_count = (row.message_count or 0) + inc
        await session.execute(
            update(Session)
            .where(Session.id == row.id)
            .values(message_count=new_count)
        )
    else:
        # Session 不存在，用消息真实归属字段创建（不再硬编码 consumer/system）
        session_obj = Session(
            session_id=session_id_val,
            user_id=user_id,
            agent_id=agent_id,
            scene_id=scene_id,
            task_id=task_id,
            status="active",
            message_count=inc,
        )
        session.add(session_obj)


# ============================================================
# 独立启动入口
# ============================================================

async def _main():
    """独立启动消费者进程"""
    stop_event = asyncio.Event()

    def _handle_signal(sig, frame):
        logger.info(f"收到信号 {sig}，开始优雅关闭...")
        stop_event.set()

    # Windows 使用 SIGINT (Ctrl+C)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    # 启动 Producer（用于发布 DLQ）
    await _mq_producer.start()

    try:
        await consume_loop(stop_event)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt，关闭中...")
    finally:
        await _mq_producer.stop()


if __name__ == "__main__":
    asyncio.run(_main())
