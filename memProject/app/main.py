# -*- coding: utf-8 -*-
"""
FastAPI 应用入口 — 智能体记忆系统（开发阶段）。
"""

# ── 必须在所有导入之前：抑制 websockets 库的弃用警告 ──
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets")
warnings.filterwarnings("ignore", message=".*websockets.legacy.*")

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import check_db_connection, create_pgvector_extension
from app.core.logger import setup_logging, get_logger
from app.middleware import LoggingMiddleware, register_exception_handlers, AuthMiddleware, ApiLogMiddleware
from app.services.mem0_client import mem0_client
from app.services.l1_worker import l1_worker_loop
from app.services.l2_worker import l2_worker_loop
from app.services.l3_worker import l3_worker_loop

settings = get_settings()
setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Starting {settings.app.name} v{settings.app.version}")

    db_ok = await check_db_connection()
    if not db_ok:
        logger.error("Database connection failed")
    else:
        logger.info("Database connection OK")
        await create_pgvector_extension()

    # 初始化 mem0 客户端
    try:
        mem0_ok = mem0_client.initialize()
        if mem0_ok:
            logger.info("mem0 client initialized OK")
        else:
            logger.warning("mem0 client init failed — mem0 双写降级")
    except Exception as e:
        logger.warning(f"mem0 client init failed (non-fatal): {e}")

    # 尝试启动 MQ Producer + Consumer（可选，Kafka 不可用时 write 走降级路径）
    consumer_stop = asyncio.Event()
    consumer_task = None
    try:
        from app.services.mq_producer import mq_producer
        await mq_producer.start()
        if mq_producer.is_available:
            logger.info("MQ Producer started — Kafka available")
            # Kafka 可用才启动 Consumer（只落 L0，抽取走 L1 worker 游标轮询）
            from app.services.mq_consumer import consume_loop
            consumer_task = asyncio.create_task(consume_loop(consumer_stop))
            logger.info("MQ Consumer 已启动")
        else:
            logger.warning("MQ Producer not available — Kafka may not be running，write 走降级同步落 L0")
    except Exception as e:
        logger.warning(f"MQ init failed (non-fatal): {e}")

    # 启动 L1 异步抽取 worker
    worker_stop = asyncio.Event()
    worker_task = asyncio.create_task(l1_worker_loop(worker_stop))
    logger.info("L1 异步抽取 worker 已启动")

    # 启动 L2 场景聚合 worker
    l2_stop = asyncio.Event()
    l2_task = asyncio.create_task(l2_worker_loop(l2_stop))
    logger.info("L2 场景聚合 worker 已启动")

    # 启动 L3 画像 worker
    l3_stop = asyncio.Event()
    l3_task = asyncio.create_task(l3_worker_loop(l3_stop))
    logger.info("L3 画像 worker 已启动")

    logger.info("Application startup complete")
    yield
    # 停止 L1 worker
    worker_stop.set()
    try:
        await worker_task
    except Exception:
        pass
    # 停止 L2 worker
    l2_stop.set()
    try:
        await l2_task
    except Exception:
        pass
    # 停止 L3 worker
    l3_stop.set()
    try:
        await l3_task
    except Exception:
        pass
    # 停止 MQ Consumer
    if consumer_task is not None:
        consumer_stop.set()
        try:
            await consumer_task
        except Exception:
            pass
    # 关闭 MQ Producer
    try:
        from app.services.mq_producer import mq_producer
        await mq_producer.stop()
    except Exception:
        pass
    from app.mcp_client import mcp_client as mc
    await mc.close_all()
    logger.info("Application shutting down")


app = FastAPI(
    title=settings.app.name,
    version=settings.app.version,
    docs_url="/docs" if settings.app.debug else None,
    redoc_url="/redoc" if settings.app.debug else None,
    lifespan=lifespan,
)

register_exception_handlers(app)
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(ApiLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "app": settings.app.name, "version": settings.app.version}


@app.get("/api/v1/health", tags=["system"])
async def api_health_check():
    return {
        "status": "ok",
        "app": settings.app.name,
        "version": settings.app.version,
        "database": await check_db_connection(),
    }


from app.api.v1.router import api_router
app.include_router(api_router, prefix="/api/v1")

from app.api.v1.proxy import router as proxy_router
app.include_router(proxy_router)  # Proxy 路径自带 /proxy/{spaceId}/v1/...，不加 /api/v1 前缀


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.server.host, port=settings.server.port, reload=settings.app.debug)
