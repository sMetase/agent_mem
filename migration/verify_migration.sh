#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# 迁移后一键健康检查：
#   1) Oracle 1521 连通（SELECT 1 FROM dual）
#   2) 通过 settings（ORACLE_*）校验表、VECTOR 列、索引
#   3) .env 关键键校验
#   4) 应用能否干净 import（可选）
# 用法: bash migration/verify_migration.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PY="${PYTHON:-python3}"

echo "====================================="
echo " 迁移验证：PostgreSQL+Qdrant -> Oracle 26ai"
echo " 仓库根: $ROOT"
echo "====================================="

# 0) .env 键校验
ENV_FILE="$ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    echo "[1] .env 存在: 是"
    missing=""
    for k in ORACLE_HOST ORACLE_PORT ORACLE_USER ORACLE_PASSWORD ORACLE_SERVICE; do
        grep -qE "^${k}=" "$ENV_FILE" || missing="$missing $k"
    done
    if [ -n "$missing" ]; then
        echo "    ! 缺少键:$missing  (可运行: python migration/migrate_env.py --apply)"
    else
        echo "    Oracle 关键键: 齐全"
    fi
    # 提示弃用键
    for k in DB_HOST QDRANT_HOST POSTGRES_USER; do
        grep -qE "^${k}=" "$ENV_FILE" && echo "    ! 仍存在弃用键 ${k}=（建议移除）"
    done
else
    echo "[1] .env 不存在: 否（请先看 migration/README.md 第 2 步）"
fi

echo
echo "[2] Python 依赖"
"$PY" - <<'PY'
try:
    import oracledb, sqlalchemy, pydantic_settings, yaml, dotenv
    print("    oracledb", oracledb.__version__, "| sqlalchemy", sqlalchemy.__version__)
except ImportError as e:
    print("    ! 缺依赖:", e)
PY

echo
echo "[3] 连接 Oracle + 校验表/列/索引（使用 settings.yaml 的 ORACLE_*）"
cd "$ROOT/memProject"
PYTHONPATH="$ROOT/memProject" "$PY" - <<'PY'
import sys
from app.core.config import get_settings
s = get_settings()
db = s.database
print("    目标:", db.user, "@", db.host, ":", db.port, "/", db.service_name)
import sqlalchemy
eng = sqlalchemy.create_engine(db.sync_url, pool_pre_ping=True)
try:
    with eng.connect() as c:
        ok = c.execute(sqlalchemy.text("SELECT 1 FROM dual")).scalar()
        print("    SELECT 1 FROM dual =", ok)
        tables = [r[0] for r in c.execute(sqlalchemy.text(
            "SELECT table_name FROM user_tables WHERE table_name NOT LIKE 'DR$%' ORDER BY 1"))]
        emb = c.execute(sqlalchemy.text(
            "SELECT COUNT(*) FROM user_tab_columns WHERE table_name='T_MEMORY' AND column_name='EMBEDDING'")).scalar()
        idx = [r[0] for r in c.execute(sqlalchemy.text(
            "SELECT index_name FROM user_indexes WHERE index_name IN "
            "('T_MEMORY_CONTENT_IDX','T_MEMORY_EMBEDDING_IDX')"))]
    print("    业务表 (%d): %s" % (len(tables), ", ".join(tables[:25])))
    print("    T_MEMORY.EMBEDDING VECTOR 列存在: %s" % ("是" if emb else "否!!"))
    print("    索引:", idx if idx else "（无索引 → 关键词走 jieba+INSTR，向量走顺序扫描）")
except Exception as e:
    print("    !! 连接/校验失败:", str(e).splitlines()[0])
eng.dispose()
PY

echo
echo "[4] 应用 import（可选编译校验）"
cd "$ROOT/memProject"
PYTHONPATH="$ROOT/memProject" DEEPSEEK_API_KEY= SILICONFLOW_API_KEY= "$PY" -c "import app.main; print('    app.main import OK')" 2>&1 | tail -2

echo
echo "====================================="
echo " 验证完成。若第 3 步出现 !! 请检查 ORACLE_* 配置/用户权限。"
echo " 详细说明见 migration/README.md"
echo "====================================="
