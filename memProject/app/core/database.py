# -*- coding: utf-8 -*-
"""
数据库引擎与 Session 管理 — async SQLAlchemy + Oracle 26ai（关系表 + AI Vector Search 同库）。

连接串使用 oracle+oracledb_async，连接 Oracle 26ai Free 的 FREEPDB1（用户 DEVUSER）。
建表/向量索引/全文索引由 scripts/oracle_bootstrap.py 或 ensure_oracle_schema() 完成。
"""

from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database.url,
    pool_size=settings.database.pool_size,
    max_overflow=settings.database.max_overflow,
    pool_recycle=settings.database.pool_recycle,
    echo=settings.app.debug,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM dual"))
        return True
    except Exception:
        return False


def log_warn(msg: str) -> None:
    """bootstrap 内轻量日志辅助（延迟 import 避免启动期循环依赖）。"""
    try:
        from app.core.logger import get_logger
        get_logger("database").warning(msg)
    except Exception:
        import logging
        logging.getLogger("database").warning(msg)


def bootstrap_oracle_schema_sync() -> None:
    """同步方式创建 Oracle 26ai 表结构与向量/全文索引（幂等，可重复执行）。

    步骤：
      1. 创建 t_memory_seq_id_seq 序列（Memory.seq_id 默认值依赖它，须在建表前存在）
      2. Base.metadata.create_all 建全部关系表
      3. 为 t_memory 添加 embedding VECTOR 列（缺失时才加）
      4. 创建 HNSW 向量索引 + Oracle Text CONTEXT 全文索引
    """
    from sqlalchemy import create_engine

    sync_engine = create_engine(settings.database.sync_url, pool_pre_ping=True)

    def _exists(schema_owner: str, query: str) -> bool:
        with sync_engine.connect() as conn:
            row = conn.execute(text(query)).scalar()
            return bool(row)

    # 1) 序列：Memory.seq_id 依赖的序列必须建在 create_all 之前（t_memory DEFAULT 引用它）
    if not _exists("SEQ", "SELECT COUNT(*) FROM user_sequences WHERE sequence_name = 'T_MEMORY_SEQ_ID_SEQ'"):
        with sync_engine.begin() as conn:
            conn.execute(text("CREATE SEQUENCE t_memory_seq_id_seq START WITH 1 INCREMENT BY 1 NOMAXVALUE"))
    # 2) 表（create_all 幂等：已存在则跳过）
    import app.models.base as _models  # noqa: F401  确保模型已注册
    Base.metadata.create_all(sync_engine)
    # 2.1) 裸 SQL 写入用到的自增主键序列（Oracle create_all 只建序列、不建服务端默认值；
    #      裸 MERGE 落 t_interaction_record 不带 id 时必须显式 nextval，否则 ORA-01400。
    #      放在 create_all 之后确保，全新库上不会与 SQLAlchemy 自己建的同名序列冲突。）
    if not _exists("SEQ", "SELECT COUNT(*) FROM user_sequences WHERE sequence_name = 'T_INTERACTION_RECORD_ID_SEQ'"):
        with sync_engine.begin() as conn:
            conn.execute(text("CREATE SEQUENCE t_interaction_record_id_seq START WITH 1 INCREMENT BY 1 NOMAXVALUE"))
    # 3) embedding VECTOR 列
    if not _exists("COL", "SELECT COUNT(*) FROM user_tab_columns WHERE table_name = 'T_MEMORY' AND column_name = 'EMBEDDING'"):
        with sync_engine.begin() as conn:
            conn.execute(text("ALTER TABLE t_memory ADD (embedding VECTOR(1024, FLOAT32))"))
    # 4) 向量 HNSW 索引（best-effort：不同 Oracle 版本语法有差异，失败不阻塞启动，仍可用顺序扫描检索）
    if not _exists("IDX_VEC", "SELECT COUNT(*) FROM user_indexes WHERE index_name = 'T_MEMORY_EMBEDDING_IDX'"):
        vec_sql = (
            "CREATE VECTOR INDEX t_memory_embedding_idx ON t_memory(embedding) "
            "ORGANIZATION INMEMORY NEIGHBOR GRAPH DISTANCE COSINE"
        )
        try:
            with sync_engine.begin() as conn:
                conn.execute(text(vec_sql))
        except Exception as e:
            log_warn(f"Oracle 向量索引创建失败（可用顺序扫描，不影响功能）: {str(e).splitlines()[0]}")
    # 5) Oracle Text 全文索引（best-effort：中文词检索改用 jieba+INSTR，不依赖该索引）
    if not _exists("IDX_TXT", "SELECT COUNT(*) FROM user_indexes WHERE index_name = 'T_MEMORY_CONTENT_IDX'"):
        try:
            with sync_engine.begin() as conn:
                conn.execute(text(
                    "CREATE INDEX t_memory_content_idx ON t_memory(content) INDEXTYPE IS CTXSYS.CONTEXT"
                ))
        except Exception as e:
            log_warn(f"Oracle Text 全文索引创建失败（关键词检索由 jieba+INSTR 兜底）: {str(e).splitlines()[0]}")
    sync_engine.dispose()


async def ensure_oracle_schema() -> None:
    """异步入口：在线程池内执行建表/索引 bootstrap（幂等）。"""
    import asyncio
    await asyncio.to_thread(bootstrap_oracle_schema_sync)
