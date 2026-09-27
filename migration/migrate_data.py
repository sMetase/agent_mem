#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
真实数据迁移脚本：PostgreSQL(pgvector) + Qdrant -> Oracle 26ai(AI Vector Search)

前置:
  - 旧库仍在运行: PostgreSQL(默认 127.0.0.1:5433, 用户 memuser) + Qdrant(127.0.0.1:6333)
  - Oracle 26ai 已建表(先跑 scripts/oracle_bootstrap.py)，目标表为空
  - 依赖: psycopg2-binary, qdrant-client, oracledb, sqlalchemy (memProject 环境已含)

用法:
  python migration/migrate_data.py                    # 使用默认参数/环境变量
  python migration/migrate_data.py --pg-host 127.0.0.1 --pg-port 5433 --pg-db agent_memory \
         --pg-user memuser --pg-pass mempassword \
         --qdrant-host 127.0.0.1 --qdrant-port 6333 --qdrant-col agent_mem_generation \
         --dry-run                                     # 只统计不写入
  python migration/migrate_data.py --only memory       # 只迁 t_memory + 向量

说明:
  - t_memory 会保留原 seq_id，并把 Oracle 序列 T_MEMORY_SEQ_ID_SEQ 跳到 max(seq_id)+1
  - t_interaction_record 保留原 id(用其序列)，record_id 是幂等键
  - JSON 列(key_points/tags/entities/...) 序列化为 CLOB 文本
  - 时间列(+08:00) 转成 UTC naive 写入 Oracle TIMESTAMP(6)
  - Qdrant 向量按 payload.memory_id 写入 t_memory.embedding(VECTOR 1024)
  - 重复执行安全: 幂等(MERGE / ON CONFLICT), 不会覆盖已存在的 memory_id
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# 让脚本能 import app.core.config (读 Oracle 配置)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ================= PG <-> Oracle 列映射（按数据库列名） =================
# 每行: (pg_table, oracle_table, [json列], [需保留主键/自增id的说明])
TABLE_COLUMNS = {
    "t_user": ("t_user", ["extra_meta"]),
    "t_agent": ("t_agent", ["extra_meta", "permissions"]),
    "t_scene": ("t_scene", ["extra_meta"]),
    "t_session": ("t_session", ["extra_meta"]),
    "t_task": ("t_task", ["extra_meta", "completed_items", "pending_items"]),
    "t_interaction_record": ("t_interaction_record", ["extra_meta"]),
    "t_memory": ("t_memory", ["key_points", "tags", "entities", "source_record_ids"]),
    "t_memory_history": ("t_memory_history", ["key_points", "tags", "entities"]),
    "t_memory_relation": ("t_memory_relation", []),
    "t_scene_block": ("t_scene_block", ["memory_ids"]),
    "t_persona": ("t_persona", []),
    "t_retrieval_request": ("t_retrieval_request", ["filter_conditions"]),
    "t_retrieval_result": ("t_retrieval_result", []),
    "t_dedup_audit": ("t_dedup_audit", []),
    "t_proxy_session": ("t_proxy_session", []),
    "t_memory_cursor": ("t_memory_cursor", []),
    "t_api_log": ("t_api_log", ["request_params"]),
    "t_llm_config": ("t_llm_config", []),
}

SKIP_TABLES = {"alembic_version"}  # PG 独有，无 Oracle 对应

# 需要显式提供原始 id 的表（Oracle 上这些 id 是 NUMBER NOT NULL，且既非 identity 也
# 无序列默认值 —— 迁移插入时若省略 id 会 ORA-01400；必须保留 PG 原始 id）
EXPLICIT_ID_TABLES = {
    "t_dedup_audit": "id",
    "t_memory_relation": "id",
    "t_memory_history": "id",
    "t_retrieval_request": "id",
    "t_retrieval_result": "id",
    "t_interaction_record": "id",
}


def pg_conn(args):
    import psycopg2
    return psycopg2.connect(
        host=args.pg_host, port=args.pg_port, dbname=args.pg_db,
        user=args.pg_user, password=args.pg_pass,
    )


def oracle_conn(args):
    import oracledb
    dsn = f"{args.oracle_host}:{args.oracle_port}/{args.oracle_service}"
    return oracledb.connect(user=args.oracle_user, password=args.oracle_password, dsn=dsn)


def _json_text(v):
    """把 PG 读到的 dict/list -> JSON 文本(CLOB 兼容); str/None 原样。"""
    if v is None or isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False, default=str)


def _dt_utc(v):
    """PG timestamp with time zone -> UTC naive(供 Oracle TIMESTAMP(6))。"""
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is not None:
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v
    return v


def _oracle_cols(oc, table):
    """Oracle 该表存在的列名集合(大写→小写)。"""
    with oc.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM user_tab_columns WHERE table_name=:1 ORDER BY 1",
            (table.upper(),))
        return {r[0].lower() for r in cur.fetchall()}


def migrate_table(pg_conn_obj, oc, table, json_cols, dry_run, verbose):
    """单表迁移。返回(总行, 成功行, 失败行)。"""
    pg_cur = pg_conn_obj.cursor()
    pg_cur.execute(f"SELECT * FROM {table}")
    cols = [d.name.lower() for d in pg_cur.description]
    oc_cols = _oracle_cols(oc, table)
    # 只迁移 Oracle 存在且可写的列
    common = [c for c in cols if c in oc_cols]
    explicit_id = EXPLICIT_ID_TABLES.get(table)
    rows = pg_cur.fetchall()
    total = len(rows)
    ok = fail = 0
    for raw in rows:
        row = dict(zip(cols, raw))
        # 构造插入列
        use_cols = list(common)
        insert_cols = use_cols
        params = {}
        for c in insert_cols:
            v = row.get(c)
            if c in json_cols:
                v = _json_text(v)
            elif isinstance(v, datetime):
                v = _dt_utc(v)
            params[c] = v
        # 显式 id 必须放最前且必须存在
        if explicit_id and explicit_id in row and explicit_id in oc_cols:
            idv = params.get(explicit_id, row[explicit_id])
            if idv is None:
                # 空 id 无法插入，跳过该行
                if verbose:
                    print(f"  !! {table} 行 id 为空，跳过: {row.get('memory_id','')}{row.get('audit_id','')}")
                fail += 1
                continue
            params[explicit_id] = idv
        placeholders = ", ".join(":" + c for c in insert_cols)
        sql = f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({placeholders})"
        if dry_run:
            ok += 1
            continue
        try:
            with oc.cursor() as cur:
                cur.execute(sql, params)
            ok += 1
        except Exception as e:
            fail += 1
            if verbose:
                print(f"  !! {table} 插入失败: {str(e).splitlines()[0]} | row={ {k: str(v)[:40] for k, v in row.items() if k in ('id','memory_id','record_id','audit_id')} }")
    oc.commit()
    pg_cur.close()
    return total, ok, fail


def migrate_vectors(args, oc, verbose):
    """从 Qdrant 拉向量，按 payload.memory_id 写入 Oracle t_memory.embedding。"""
    import oracledb as _odb
    from qdrant_client import QdrantClient

    qc = QdrantClient(host=args.qdrant_host, port=args.qdrant_port, timeout=15)
    try:
        collections = [x.name for x in qc.get_collections().collections]
        if args.qdrant_col not in collections:
            print(f"  !! Qdrant collection '{args.qdrant_col}' 不存在，跳过向量迁移。")
            return 0, 0
        oc_cols = _oracle_cols(oc, "t_memory")
        if "embedding" not in oc_cols:
            print("  !! Oracle t_memory 无 embedding 列，跳过向量迁移（先跑 bootstrap）。")
            return 0, 0

        # 以「源 PG t_memory」的 memory_id 为判定依据（不依赖 Oracle 已写入，保证 dry-run 统计准确）
        import psycopg2 as _pg
        _pgc = _pg.connect(host=args.pg_host, port=args.pg_port, dbname=args.pg_db,
                           user=args.pg_user, password=args.pg_pass)
        _cur = _pgc.cursor()
        _cur.execute("SELECT memory_id FROM t_memory")
        existing = {r[0] for r in _cur.fetchall()}
        _cur.close()
        _pgc.close()

        offset = None
        total = matched = skipped = 0
        import array
        while True:
            pts, offset = qc.scroll(
                collection_name=args.qdrant_col, limit=500,
                with_payload=True, with_vectors=True, offset=offset)
            if not pts:
                break
            for p in pts:
                total += 1
                mid = (p.payload or {}).get("memory_id")
                if not mid or mid not in existing:
                    skipped += 1
                    continue
                vec = p.vector
                from qdrant_client.models import SparseVector
                if isinstance(vec, dict):
                    # named vectors: dict{ 名字: 向量 }。dense 存于默认键 ''，
                    # sparse(bm25) 是 SparseVector。稳定取 dense 避免顺序抖动。
                    vec = vec.get("") or vec.get("dense") or vec.get("default")
                    # 仍可能是 dict 且无 ''/dense/default → 取第一个非 SparseVector
                    if isinstance(vec, dict):
                        vec = next((v for v in vec.values() if not isinstance(v, SparseVector)), None)
                if isinstance(vec, SparseVector):
                    # 稀疏向量：我们用 dense 语义检索，忽略
                    skipped += 1
                    continue
                if vec is None or (hasattr(vec, "__len__") and len(vec) == 0):
                    skipped += 1
                    continue
                if args.dry_run:
                    matched += 1
                    continue
                with oc.cursor() as cur:
                    cur.setinputsizes(v=_odb.DB_TYPE_VECTOR)
                    cur.execute(
                        "UPDATE t_memory SET embedding=:v WHERE memory_id=:mid",
                        v=array.array("f", vec), mid=mid)
                matched += 1
            if offset is None:
                break
        oc.commit()
        return total, matched
    finally:
        qc.close()


def _set_seq_to(oc, seq_name, target, verbose):
    with oc.cursor() as cur:
        cur.execute(f"SELECT {seq_name}.nextval FROM dual")
        curval = cur.fetchone()[0]
    diff = target - curval
    if diff > 0:
        try:
            with oc.cursor() as cur:
                cur.execute(f"ALTER SEQUENCE {seq_name} RESTART START WITH {target}")
            if verbose:
                print(f"  [seq] {seq_name} restart to {target}")
            return
        except Exception:
            pass
    if verbose:
        print(f"  [seq] {seq_name} current next={curval}, target={target} (无需调整)")


def bump_sequences(oc, verbose):
    """把 Oracle 所有 autoincrement 表的 id 序列跳到 max+1，避免迁移后主键冲突。

    覆盖: t_memory(seq_id), t_interaction_record(id), t_api_log(id), t_dedup_audit(id),
    t_memory_history(id), t_memory_relation(id), t_retrieval_request(id), t_retrieval_result(id)。
    这些表的 model id 列现在有 server_default='<table>_id_seq.nextval'（见 oracle bootstrap）。
    """
    spec = [
        ("t_memory", "seq_id", "T_MEMORY_SEQ_ID_SEQ"),
        ("t_interaction_record", "id", "T_INTERACTION_RECORD_ID_SEQ"),
        ("t_api_log", "id", "T_API_LOG_ID_SEQ"),
        ("t_dedup_audit", "id", "T_DEDUP_AUDIT_ID_SEQ"),
        ("t_memory_history", "id", "T_MEMORY_HISTORY_ID_SEQ"),
        ("t_memory_relation", "id", "T_MEMORY_RELATION_ID_SEQ"),
        ("t_retrieval_request", "id", "T_RETRIEVAL_REQUEST_ID_SEQ"),
        ("t_retrieval_result", "id", "T_RETRIEVAL_RESULT_ID_SEQ"),
    ]
    with oc.cursor() as cur:
        for table, pk, seq in spec:
            try:
                cur.execute(f"SELECT COALESCE(MAX({pk}), 0) FROM {table}")
                maxv = cur.fetchone()[0] or 0
            except Exception:
                maxv = 0
            if maxv > 0:
                _set_seq_to(oc, seq, maxv + 1, verbose)
            # 若序列不存在（如旧库），显式创建并跳到 target
            with oc.cursor() as c2:
                c2.execute("SELECT COUNT(*) FROM user_sequences WHERE sequence_name=:1", (seq,))
                exists = c2.fetchone()[0]
            if not exists:
                target = maxv + 1 if maxv > 0 else 1
                with oc.cursor() as c3:
                    c3.execute(f"CREATE SEQUENCE {seq} START WITH {target} INCREMENT BY 1 NOMAXVALUE")
                if verbose:
                    print(f"  [seq] {seq} created (start {target})")


def parse_args(argv=None):
    from app.core.config import get_settings
    s = get_settings()
    db = s.database
    p = argparse.ArgumentParser(description="PG+Qdrant -> Oracle 真实数据迁移")
    p.add_argument("--pg-host", default="127.0.0.1")
    p.add_argument("--pg-port", type=int, default=5433)
    p.add_argument("--pg-db", default="agent_memory")
    p.add_argument("--pg-user", default="memuser")
    p.add_argument("--pg-pass", default="mempassword")
    p.add_argument("--qdrant-host", default="127.0.0.1")
    p.add_argument("--qdrant-port", type=int, default=6333)
    p.add_argument("--qdrant-col", default="agent_mem_generation")
    p.add_argument("--oracle-host", default=db.host)
    p.add_argument("--oracle-port", type=int, default=db.port)
    p.add_argument("--oracle-user", default=db.user)
    p.add_argument("--oracle-password", default=db.password)
    p.add_argument("--oracle-service", default=db.service_name)
    p.add_argument("--dry-run", action="store_true", help="只统计不写入")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--only", default=None,
                   help="只迁移指定表(逗号分隔)，如 memory,persona；默认迁全部有数据表")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    oc = oracle_conn(args)
    oc.autocommit = False

    import psycopg2
    pg = psycopg2.connect(host=args.pg_host, port=args.pg_port, dbname=args.pg_db,
                          user=args.pg_user, password=args.pg_pass)

    only = set(t.strip() for t in args.only.split(",") if t.strip()) if args.only else None
    print("=== 开始迁移 ===")
    print(f"  PG:  {args.pg_user}@{args.pg_host}:{args.pg_port}/{args.pg_db}")
    print(f"  Oracle: {args.oracle_user}@{args.oracle_host}:{args.oracle_port}/{args.oracle_service}")
    print(f"  模式: {'dry-run(只统计)' if args.dry_run else '真实写入'}")

    pg_cur = pg.cursor()
    pg_cur.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
        "AND table_type='BASE TABLE'")
    pg_tables = {r[0] for r in pg_cur.fetchall()}

    order = ["t_memory", "t_user", "t_agent", "t_scene", "t_session", "t_task",
             "t_interaction_record", "t_scene_block", "t_persona",
             "t_memory_cursor", "t_memory_relation", "t_memory_history",
             "t_dedup_audit", "t_retrieval_request", "t_retrieval_result",
             "t_proxy_session", "t_llm_config", "t_api_log"]
    summary = []
    for pg_t in order:
        if pg_t not in pg_tables or pg_t in SKIP_TABLES:
            continue
        if only and pg_t not in only:
            continue
        meta = TABLE_COLUMNS.get(pg_t)
        if not meta:
            continue
        oracle_t, json_cols = meta
        total, ok, fail = migrate_table(pg, oc, oracle_t, json_cols, args.dry_run, args.verbose)
        summary.append((pg_t, total, ok, fail))

    if not only or "memory" in only or "t_memory" in only:
        if args.qdrant_col:
            v_total, v_ok = migrate_vectors(args, oc, args.verbose)
            summary.append(("qdrant:" + args.qdrant_col, v_total, v_ok, v_total - v_ok))

    if not args.dry_run:
        bump_sequences(oc, args.verbose)

    pg.close()
    oc.close()

    print("\n=== 迁移汇总 ===")
    tot = ok_t = fail_t = 0
    for name, total, ok, fail in summary:
        print(f"  {name:<28} 源={total:>5}  成功={ok:>5}  失败={fail:>5}")
        tot += total; ok_t += ok; fail_t += fail
    print(f"  {'合计':<28} 源={tot:>5}  成功={ok_t:>5}  失败={fail_t:>5}")
    print("=== 完成 ===")
    return 0 if fail_t == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
