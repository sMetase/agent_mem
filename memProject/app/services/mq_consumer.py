# -*- coding: utf-8 -*-
"""
MQ 消费者 — AIOKafka Consumer 守护进程。

职责:
  - consume_loop(): 主循环，从 memory.write 消费消息
  - _dispatch_and_store(): 按 interaction_type 分流落库
  - 指数退避重试（max 3 次），失败进 DLQ
  - 处理完成后通过 Redis 发布结果（供 result_waiter 使用）
  - 优雅关闭信号处理

消费三种数据类型:
  - dialogue:     对话记录 → T_INTERACTION_RECORD 批量写入
  - session:      历史会话 → T_INTERACTION_RECORD + T_SESSION 更新
  - task_process: 任务过程 → T_INTERACTION_RECORD + T_TASK 更新

启动方式:
  python -m app.services.mq_consumer
"""

import asyncio
import json
import os
import signal
import sys
import time as time_module
from uuid import uuid4

# 确保项目根在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.logger import get_logger
from app.models.base import InteractionRecord, Session, Task
from app.services.mq_producer import mq_producer as _mq_producer

logger = get_logger("mq_consumer")

settings = get_settings()

# 重试配置
MAX_RETRIES = settings.kafka.max_retries
RETRY_BACKOFF_MS = settings.kafka.retry_backoff_ms


async def consume_loop(stop_event: asyncio.Event | None = None) -> None:
    """
    消费者主循环 — 连接 Kafka、拉取消息、分发处理。

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
    处理单条消息 — 含重试逻辑。

    流程:
      1. 解析消息体
      2. 调用 _dispatch_and_store() 落库
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
            results = await _dispatch_and_store(request_id, user_id, agent_id, body)

            # 通过 Result Waiter 发布结果（如果有 Redis 可用）
            await _publish_result_via_redis(request_id, results)

            # 通过 Kafka 发布结果
            await _mq_producer.publish_memory_result(request_id, user_id, results)

            logger.info(
                f"消息处理完成: request_id={request_id}, "
                f"results={len(results) if results else 0}"
            )

            # 手动提交 offset
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
) -> list[dict]:
    """
    按 interaction_type 分流处理并落库。

    Returns:
        [{id, memory, event}, ...] 处理结果
    """
    itype = body.get("interaction_type", "dialogue")
    messages = body.get("messages", [])
    session_id_val = body.get("session_id")

    async with async_session_factory() as session:
        now = _utcnow()
        records_to_insert = []

        if itype == "dialogue":
            records_to_insert = _build_dialogue_records(
                body, messages, user_id, agent_id, session_id_val, now
            )
        elif itype == "session":
            records_to_insert = _build_session_records(
                body, messages, user_id, agent_id, session_id_val, now
            )
        elif itype == "task_process":
            records_to_insert = _build_task_process_records(
                body, messages, user_id, agent_id, session_id_val, now
            )

        # 批量写入 InteractionRecord
        if records_to_insert:
            from sqlalchemy import insert
            await session.execute(insert(InteractionRecord), records_to_insert)

        # 更新 T_SESSION（message_count）
        await _update_session_count(session, session_id_val, len(records_to_insert))

        await session.commit()

    # 记忆提取：默认走真实 Pipeline（extract→generate→dedup→store），
    # 仅当显式配置 use_mock_extraction=True 时使用开发期正则 Mock
    if settings.generation.use_mock_extraction:
        from app.services.mock_extractor import mock_extract_results
        logger.warning(f"[Mock] Consumer 使用正则提取(非真实Pipeline): request_id={request_id}")
        return mock_extract_results(messages)

    text = _build_content_text(itype, body, messages)
    if not text.strip():
        return []

    from app.services.memory_pipeline import memory_pipeline
    async with async_session_factory() as pipe_session:
        pipeline_result = await memory_pipeline.run(
            text=text,
            user_id=user_id,
            agent_id=agent_id or None,
            scene_id=body.get("scene_id"),
            session_id=session_id_val,
            task_id=body.get("task_id"),
            extraction_types=["key_fact", "task_state", "decision"],
            task_context=body.get("metadata"),
            db=pipe_session,
        )
    return _pipeline_to_results(pipeline_result)


def _build_content_text(itype: str, body: dict, messages: list) -> str:
    """将消息体拼接为 Pipeline 输入文本（与 MemoryWriteRequest.get_content_text 对齐）"""
    parts = []
    for i, m in enumerate(messages):
        parts.append(f"[{m.get('role', 'user')}](轮次{i + 1}): {m.get('content', '')}")
    if itype == "session":
        if body.get("session_summary"):
            parts.append(f"[历史会话摘要]: {body['session_summary']}")
        if body.get("session_source"):
            parts.append(f"[会话来源]: {body['session_source']}")
        if body.get("session_time"):
            parts.append(f"[会话时间]: {body['session_time']}")
    if itype == "task_process":
        if body.get("task_goal"):
            parts.append(f"[任务目标]: {body['task_goal']}")
        if body.get("task_progress"):
            parts.append(f"[任务进展]: {body['task_progress']}")
        if body.get("task_result"):
            parts.append(f"[执行结果]: {body['task_result']}")
    return "\n".join(parts) if parts else ""


def _pipeline_to_results(pipeline_result) -> list[dict]:
    """
    PipelineResult.details → [{id, memory, event}]。

    映射规则（与 api/v1/memory._pipeline_to_write_results 一致）:
      keep_new                   → ADD
      update_existing            → UPDATE
      merge                      → MERGE
      discard                    → SKIP
    """
    results = []
    for d in pipeline_result.details:
        action = d.get("action", "keep_new")
        memory_id = d.get("memory_id", "") or ""
        content = d.get("content_preview", "") or ""

        if action == "discard":
            results.append({"id": "", "memory": content, "event": "SKIP"})
        elif action == "merge":
            results.append({"id": memory_id, "memory": content, "event": "MERGE"})
        elif action == "update_existing":
            results.append({"id": memory_id, "memory": content, "event": "UPDATE"})
        else:  # keep_new
            results.append({"id": memory_id, "memory": content, "event": "ADD"})
    return results


# ============================================================
# 辅助函数
# ============================================================

def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _build_dialogue_records(body, messages, user_id, agent_id, session_id_val, now) -> list[dict]:
    """构建对话记录字典列表（用于批量 insert）"""
    records = []
    task_id = body.get("task_id")
    scene_id = body.get("scene_id")
    extra_meta = body.get("metadata") or {}

    for i, msg in enumerate(messages):
        records.append({
            "record_id": f"rec_{uuid4().hex[:24]}",
            "user_id": user_id,
            "agent_id": agent_id,
            "scene_id": scene_id,
            "session_id": session_id_val,
            "task_id": task_id,
            "interaction_type": "dialogue",
            "turn_index": i,
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
            "content_type": "text",
            "processed": False,
            "status": "pending_extract",
            "recorded_at": now,
            "extra_meta": extra_meta,
        })
    return records


def _build_session_records(body, messages, user_id, agent_id, session_id_val, now) -> list[dict]:
    """构建历史会话记录字典列表"""
    records = []
    task_id = body.get("task_id")
    scene_id = body.get("scene_id")
    extra_meta = body.get("metadata") or {}

    if body.get("session_time"):
        extra_meta["session_time"] = body["session_time"]
    if body.get("session_source"):
        extra_meta["session_source"] = body["session_source"]

    for i, msg in enumerate(messages):
        records.append({
            "record_id": f"rec_{uuid4().hex[:24]}",
            "user_id": user_id,
            "agent_id": agent_id,
            "scene_id": scene_id,
            "session_id": session_id_val,
            "task_id": task_id,
            "interaction_type": "session",
            "turn_index": i,
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
            "content_type": "text",
            "processed": False,
            "status": "pending_extract",
            "recorded_at": now,
            "extra_meta": extra_meta,
        })

    if body.get("session_summary"):
        records.append({
            "record_id": f"rec_{uuid4().hex[:24]}",
            "user_id": user_id,
            "agent_id": agent_id,
            "scene_id": scene_id,
            "session_id": session_id_val,
            "task_id": task_id,
            "interaction_type": "session",
            "turn_index": len(messages),
            "role": "session_summary",
            "content": body["session_summary"],
            "content_type": "session_summary",
            "processed": False,
            "status": "pending_extract",
            "recorded_at": now,
            "extra_meta": extra_meta,
        })
    return records


def _build_task_process_records(body, messages, user_id, agent_id, session_id_val, now) -> list[dict]:
    """构建任务过程记录字典列表"""
    records = []
    task_id = body.get("task_id")
    scene_id = body.get("scene_id")
    extra_meta = body.get("metadata") or {}

    for i, msg in enumerate(messages):
        records.append({
            "record_id": f"rec_{uuid4().hex[:24]}",
            "user_id": user_id,
            "agent_id": agent_id,
            "scene_id": scene_id,
            "session_id": session_id_val,
            "task_id": task_id,
            "interaction_type": "task_process",
            "turn_index": i,
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
            "content_type": "text",
            "processed": False,
            "status": "pending_extract",
            "recorded_at": now,
            "extra_meta": extra_meta,
        })

    turn_offset = len(messages)
    task_fields = [
        ("task_goal", body.get("task_goal")),
        ("task_progress", body.get("task_progress")),
        ("task_result", body.get("task_result")),
    ]
    for j, (role_name, content) in enumerate(task_fields):
        if content:
            records.append({
                "record_id": f"rec_{uuid4().hex[:24]}",
                "user_id": user_id,
                "agent_id": agent_id,
                "scene_id": scene_id,
                "session_id": session_id_val,
                "task_id": task_id,
                "interaction_type": "task_process",
                "turn_index": turn_offset + j,
                "role": role_name,
                "content": content,
                "content_type": "task_process",
                "processed": False,
                "status": "pending_extract",
                "recorded_at": now,
                "extra_meta": extra_meta,
            })
    return records


async def _update_session_count(session, session_id_val: str, inc: int) -> None:
    """更新 T_SESSION.message_count"""
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
        # Session 不存在，创建一个
        session_obj = Session(
            session_id=session_id_val,
            user_id="consumer",
            agent_id="system",
            status="active",
            message_count=inc,
        )
        session.add(session_obj)


async def _publish_result_via_redis(request_id: str, results: list[dict]) -> None:
    """通过 Redis Pub/Sub 发布处理结果（供 result_waiter 使用）"""
    try:
        from app.services.result_waiter import publish_result
        await publish_result(request_id, results)
    except Exception as e:
        logger.warning(f"Redis 结果发布失败（非致命）: {e}")


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

    # 启动 Producer（用于发布结果和 DLQ）
    await _mq_producer.start()

    try:
        await consume_loop(stop_event)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt，关闭中...")
    finally:
        await _mq_producer.stop()


if __name__ == "__main__":
    asyncio.run(_main())
