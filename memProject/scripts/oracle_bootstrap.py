# -*- coding: utf-8 -*-
"""
Oracle 26ai 初始化脚本 — 幂等建表 + embedding VECTOR 列 + HNSW 向量索引 + Oracle Text 全文索引。

用法（在 memProject 目录 / app 同父路径，依赖已安装）:
    python scripts/oracle_bootstrap.py

连接配置取自 config/settings.yaml 的 database 段（默认 DEVUSER@FREEPDB1:1521）。
"""
import sys
from pathlib import Path

# 让 `python scripts/oracle_bootstrap.py` 能在任意 cwd 下找到 app 包
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import bootstrap_oracle_schema_sync


def main() -> int:
    settings = get_settings()
    print(f"Oracle 26ai bootstrap 开始:\t{settings.database.user}@{settings.database.host}:{settings.database.port}/{settings.database.service_name}")

    bootstrap_oracle_schema_sync()

    # 校验结果
    from sqlalchemy import create_engine
    eng = create_engine(settings.database.sync_url, pool_pre_ping=True)
    with eng.connect() as conn:
        tables = [r[0] for r in conn.execute(text(
            "SELECT table_name FROM user_tables ORDER BY table_name"
        ))]
        cols = [r[0] for r in conn.execute(text(
            "SELECT column_name FROM user_tab_columns WHERE table_name='T_MEMORY' AND column_name='EMBEDDING'"
        ))]
        indexes = [r for r in conn.execute(text(
            "SELECT index_name FROM user_indexes WHERE index_name IN "
            "('T_MEMORY_EMBEDDING_IDX','T_MEMORY_CONTENT_IDX')"
        ))]
    eng.dispose()

    print(f"建表 {len(tables)} 张: {', '.join(tables)}")
    print(f"T_MEMORY.EMBEDDING 列存在: {'是' if cols else '否（需检查，可能已存在则跳过）'}")
    print(f"向量/全文索引: {', '.join(i[0] for i in indexes)}")
    print("Oracle 26ai bootstrap 完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
