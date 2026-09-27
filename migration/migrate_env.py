#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
.env 迁移工具 —— 把旧 PG(pgvector)+Qdrant 配置迁移到 Oracle 26ai 配置。

功能:
  - 读取旧 .env
  - 保留原有 LLM/Embedding/安全/前端/Redis/Kafka 等键
  - 删除已弃用的 DB_*/QDRANT_*/POSTGRES_*
  - 追加/覆盖 ORACLE_* 配置（可用 --overwrite 决定是否覆盖已存在的 ORACLE_*）
  - 输出到目标文件（默认 .env.oracle）

用法:
  python migration/migrate_env.py                 # 读 .env -> 写 .env.oracle（不覆盖原文件）
  python migration/migrate_env.py --in x.env --out y.env
  python migration/migrate_env.py --oracle-host 10.0.0.5 --overwrite
  python migration/migrate_env.py --apply         # 直接覆盖 .env（谨慎）
"""
import argparse
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 键名大小写不敏感；保留顺序：按读到的顺序写回，新的 ORACLE_* 追加在弃用键原位。
DEPRECATED_KEYS = {
    "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
    "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME",
    "QDRANT_HOST", "QDRANT_PORT", "QDRANT_HTTP_PORT", "QDRANT_GRPC_PORT",
}
ORACLE_DEFAULTS = {
    "ORACLE_HOST": "127.0.0.1",
    "ORACLE_PORT": "1521",
    "ORACLE_USER": "DEVUSER",
    "ORACLE_PASSWORD": "DevPassword123",
    "ORACLE_SERVICE": "FREEPDB1",
}


def parse_env(text: str) -> list:
    """返回有序的 [(key_or_None_for_comment_or_blank, raw_line)]。"""
    entries = []
    for raw in text.splitlines():
        m = re.match(r"\s*export\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", raw)
        if m:
            key = m.group(1)
        else:
            m2 = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", raw)
            key = m2.group(1) if m2 else None
        entries.append((key, raw))
    return entries


def build_env(entries, oracle_cfg, overwrite: bool, add_header: bool) -> str:
    lines = list(entries)
    if add_header and not any(k == "ORACLE_HOST" for k, _ in lines):
        lines.insert(0, (None, "# ---- Oracle 26ai (关系表 + AI Vector Search 同库) ----"))

    for key, value in oracle_cfg.items():
        idx_upper = [i for i, (k, _) in enumerate(lines) if k and k.upper() == key]
        if idx_upper:
            i = idx_upper[0]
            if overwrite:
                lines[i] = (key, f"{key}={value}")
            # 已存在且不 overwrite：保留原值
        else:
            lines.append((key, f"{key}={value}"))
    return "\n".join(raw for _, raw in lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="迁移 .env 到 Oracle 26ai 配置")
    ap.add_argument("--in", dest="inp", type=Path, default=ROOT / ".env")
    ap.add_argument("--out", dest="out", type=Path, default=ROOT / ".env.oracle")
    ap.add_argument("--apply", action="store_true", help="直接覆盖 .env")
    ap.add_argument("--overwrite", action="store_true",
                    help="覆盖已存在的 ORACLE_* 键为默认值（否则保留原值）")
    for k, v in ORACLE_DEFAULTS.items():
        ap.add_argument(f"--{k.lower()}", dest=f"oc_{k}", default=None,
                        help=f"覆盖 {k}（默认 {v}）")
    args = ap.parse_args()

    inp = args.inp
    if not inp.exists():
        raise SystemExit(f"未找到源 .env: {inp.resolve()}")

    entries = parse_env(inp.read_text(encoding="utf-8", errors="replace"))

    # 删除弃用键
    kept = [(k, raw) for k, raw in entries if not (k and k.upper() in DEPRECATED_KEYS)]

    # 构造 Oracle 配置（CLI 优先，其次环境变量，再次默认）
    oracle_cfg = dict(ORACLE_DEFAULTS)
    for k, v in ORACLE_DEFAULTS.items():
        cli = getattr(args, f"oc_{k}")
        envval = os.environ.get(k)
        if cli:
            oracle_cfg[k] = cli
        elif envval:
            oracle_cfg[k] = envval

    out_text = build_env(kept, oracle_cfg, args.overwrite, add_header=True)

    out = args.inp if args.apply else args.out
    out.write_text(out_text, encoding="utf-8")
    print(f"已生成: {out.resolve()}")

    # 校验：必备 LLM 键
    keys = {k.upper() for k, _ in kept if k} | set(oracle_cfg)
    for need in ("DEEPSEEK_API_KEY", "SILICONFLOW_API_KEY"):
        if need not in keys:
            print(f"  ! 提示: {need} 缺失/为空，写库/检索会降级")
    print("迁移完成。")


if __name__ == "__main__":
    main()
