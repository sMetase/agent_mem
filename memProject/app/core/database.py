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


def _ensure_seq_for_server_defaults(sync_engine) -> None:
    """为模型里所有 `server_default=text('xxx_seq.nextval')` 确保对应序列存在（幂等）。

    解决 Oracle 迁移的一个真实问题：SQLAlchemy 在 Oracle 上对 `autoincrement=True` 的
    BigInteger 主键只生成普通 `NUMBER NOT NULL` 列、不绑定序列，导致 ORM 插入时
    `RETURNING ... INTO` 拿到 NULL，报 ORA-01400。修复方式：在这些 id 列上显式
    server_default='<table>_id_seq.nextval'，并在 bootstrap 先建齐这些序列。
    """
    import re as _re
    seq_names = set()
    for table in Base.metadata.tables.values():
        for col in table.columns:
            sd = getattr(col, "server_default", None)
            if sd is None:
                continue
            try:
                raw = str(sd.arg)
            except Exception:
                continue
            m = _re.search(r"([A-Za-z0-9_]+)\.nextval", raw)
            if m:
                seq_names.add(m.group(1).upper())
    for seq in seq_names:
        with sync_engine.connect() as _conn:
            _cnt = _conn.execute(text(
                "SELECT COUNT(*) FROM user_sequences WHERE sequence_name = :s"
            ), {"s": seq}).scalar() or 0
        if _cnt == 0:
            with sync_engine.begin() as conn:
                conn.execute(text(f"CREATE SEQUENCE {seq} START WITH 1 INCREMENT BY 1 NOMAXVALUE"))


def _apply_server_defaults_on_tables(sync_engine) -> None:
    """为「模型声明了 server_default 但已有表列缺默认值」的列补 ALTER ... DEFAULT。

    create_all 对已存在的表不做任何变更，因此 Oracle 迁移初期用 `autoincrement=True`
    建出的 id 列（NUMBER NOT NULL，无 default）需要补上 '<table>_id_seq.nextval'，
    否则 ORM 插入报 ORA-01400。幂等：仅当库里该列 data_default 为空才 MODIFY。
    """
    import re as _re
    empty_default = {}
    with sync_engine.connect() as conn:
        for r in conn.execute(text(
            "SELECT table_name, column_name FROM user_tab_columns "
            "WHERE (data_default IS NULL OR data_default = '')"
        )):
            empty_default[(str(r[0]).upper(), str(r[1]).upper())] = True
    for table_name, table in Base.metadata.tables.items():
        for col in table.columns:
            sd = getattr(col, "server_default", None)
            if sd is None:
                continue
            try:
                raw = str(sd.arg)
            except Exception:
                continue
            if ".nextval" not in raw:
                continue
            key = (table_name.upper(), str(col.name).upper())
            if key in empty_default:
                try:
                    with sync_engine.begin() as conn:
                        conn.execute(text(
                            f"ALTER TABLE {table_name} MODIFY ({col.name} DEFAULT {raw})"
                        ))
                    log_warn(f"已为 {table_name}.{col.name} 补 DEFAULT {raw}")
                except Exception as e:
                    log_warn(f"为 {table_name}.{col.name} 补 DEFAULT 失败: {str(e).splitlines()[0]}")


def _collect_timestamp_columns(sync_engine) -> list[tuple[str, str]]:
    """找出「模型用 OracleDateTime（→TIMESTAMP）但库里当前是 DATE」的列，返回 [(表,列)]。

    用于把早期 DATE(秒精度) 的列升级为 TIMESTAMP(6)(微秒)，修复增量游标同秒漏判。
    """
    from app.models.base import OracleDateTime
    upgrade: list[tuple[str, str]] = []
    try:
        with sync_engine.connect() as conn:
            cur_cols = {}
            for t in conn.execute(text(
                "SELECT table_name, column_name FROM user_tab_columns WHERE data_type = 'DATE'"
            )):
                cur_cols[(str(t[0]).upper(), str(t[1]).upper())] = True
        for table_name, table in Base.metadata.tables.items():
            for col in table.columns:
                ttype = col.type
                if isinstance(ttype, OracleDateTime):
                    key = (table_name.upper(), str(col.name).upper())
                    if key in cur_cols:
                        upgrade.append((table_name.upper(), str(col.name).upper()))
    except Exception as e:  # pragma: no cover
        log_warn(f"收集时间列升级清单失败（跳过）: {str(e).splitlines()[0]}")
    return upgrade


def bootstrap_oracle_schema_sync() -> None:
    """同步方式创建 Oracle 26ai 表结构与向量/全文索引（幂等，可重复执行）。

    步骤：
      1. 创建 t_memory_seq_id_seq 序列（Memory.seq_id 默认值依赖它，须在建表前存在）
      2. Base.metadata.create_all 建全部关系表；并把模型 OracleDateTime 列从 DATE 升级为 TIMESTAMP(6)
      3. 为 t_memory 添加 embedding VECTOR 列（缺失时才加）
      4. 创建 HNSW 向量索引 + Oracle Text CONTEXT 全文索引（best-effort）
    """
    from sqlalchemy import create_engine

    sync_engine = create_engine(settings.database.sync_url, pool_pre_ping=True)

    def _exists(schema_owner: str, query: str) -> bool:
        with sync_engine.connect() as conn:
            row = conn.execute(text(query)).scalar()
            return bool(row)

    # 0) 注册模型元数据（必须在扫描 server_default 序列之前，否则 Base.metadata 为空）
    import app.models.base as _models  # noqa: F401  确保模型已注册
    # 1) 序列：Memory.seq_id 依赖的序列必须建在 create_all 之前（t_memory DEFAULT 引用它）
    if not _exists("SEQ", "SELECT COUNT(*) FROM user_sequences WHERE sequence_name = 'T_MEMORY_SEQ_ID_SEQ'"):
        with sync_engine.begin() as conn:
            conn.execute(text("CREATE SEQUENCE t_memory_seq_id_seq START WITH 1 INCREMENT BY 1 NOMAXVALUE"))
    # 1.1) 所有模型里 server_default 引用的 `xxx_id_seq.nextval` 序列都必须先存在（create_all 前），
    #      否则 Oracle 建 DEFAULT 列会因序列缺失报 ORA-02289。
    _ensure_seq_for_server_defaults(sync_engine)
    # 2) 表（create_all 幂等：已存在则跳过）
    Base.metadata.create_all(sync_engine)
    # 2.1) 裸 SQL 写入用到的自增主键序列（Oracle create_all 只建序列、不建服务端默认值；
    #      裸 MERGE 落 t_interaction_record 不带 id 时必须显式 nextval，否则 ORA-01400。
    #      放在 create_all 之后确保，全新库上不会与 SQLAlchemy 自己建的同名序列冲突。）
    if not _exists("SEQ", "SELECT COUNT(*) FROM user_sequences WHERE sequence_name = 'T_INTERACTION_RECORD_ID_SEQ'"):
        with sync_engine.begin() as conn:
            conn.execute(text("CREATE SEQUENCE t_interaction_record_id_seq START WITH 1 INCREMENT BY 1 NOMAXVALUE"))
    # 2.2) 给已存在的 autoincrement 主键列补上序列 DEFAULT（create_all 不会改已有列）。
    #      解决 ORM 插入 ORA-01400 的真实问题（见 _ensure_seq_for_server_defaults 说明）。
    _apply_server_defaults_on_tables(sync_engine)
    # 3) 升级：模型里的时间列（OracleDateTime→TIMESTAMP）若库里还是 DATE（秒精度），
    #     ALTER 为 TIMESTAMP(6)（微秒）。修复 L3 增量游标同秒漏判的问题。
    #     幂等：仅当某列当前类型为 DATE 才 MODIFY。
    upgrade_ts = _collect_timestamp_columns(sync_engine)
    for table, col in upgrade_ts:
        with sync_engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} MODIFY ({col} TIMESTAMP(6))"))
    if upgrade_ts:
        log_warn(f"已升级 {len(upgrade_ts)} 个时间列 DATE→TIMESTAMP(6): {upgrade_ts}")
    # 3.1) embedding VECTOR 列
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
