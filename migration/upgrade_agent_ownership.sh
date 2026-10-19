#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# ============================================================================
# 智能体记忆系统 —— 部署侧平滑升级脚本（本轮修复: t_agent 增加 user_id 归属列）
#
# 背景
#   t_agent 此前没有 user_id，智能体归属只靠 scene_id → t_scene.user_id 间接推导，
#   且开发模式(AUTH_ENABLED=false)无 X-User-Id 时归属校验被整体跳过，导致
#   「用 API 注册的智能体在控制台『智能体管理』查不到」（用户反馈）。
#   本轮修复为 t_agent 增加 user_id 列并绑定注册者，控制台按 user_id 过滤即可查到。
#
# 本脚本在【部署侧】对线上 Oracle 做幂等升级：加列 + 建索引 + 回填历史数据。
#
# 数据零丢失 / 丝滑升级保证
#   - 只做 ADD 列 / CREATE INDEX / 回填 UPDATE，不 DROP、不 TRUNCATE、不改已有值
#   - 幂等：已升级过的库重复运行是 no-op；上线回滚后重跑同样安全
#   - 可在【新镜像上线前】预跑：旧代码不感知新列（加列是纯增量），无任何影响；
#     也可上线后随时重跑复核
#   - 回填语义与后端 bootstrap(app/core/database.py 3.2) 完全一致：
#       t_agent.user_id = 其场景 t_scene.user_id；
#       无主/无场景的智能体保持 NULL，由列表查询的「场景归属兜底」保证仍可见
#
# 用法（仓库根目录）
#   bash migration/upgrade_agent_ownership.sh                     # 自动读 .env 的 ORACLE_*
#   ORACLE_PASSWORD=xxx bash migration/upgrade_agent_ownership.sh # 覆盖某一连接参数
#
# 依赖: python3 + oracledb（与 setup_oracle_user.sh / migration.sh 相同）
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PY="${PYTHON:-python3}"

log() { echo -e "\033[1;34m[upgrade]\033[0m $*"; }
err() { echo -e "\033[1;31m[upgrade ERROR]\033[0m $*" >&2; }
die() { err "$*"; exit 1; }

get_env() { grep -m1 "^$1=" "$ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '[:space:]' || true; }

# ---------------- 1) 连接参数（与 migration.sh 一致，支持环境变量覆盖） ----------------
if [[ ! -f "$ROOT/.env" ]]; then
  die "未找到 $ROOT/.env（请先按 migration/README.md 完成配置）"
fi
ORACLE_HOST="${ORACLE_HOST:-$(get_env ORACLE_HOST)}";  ORACLE_HOST="${ORACLE_HOST:-127.0.0.1}"
ORACLE_PORT="${ORACLE_PORT:-$(get_env ORACLE_PORT)}";  ORACLE_PORT="${ORACLE_PORT:-1521}"
ORACLE_SERVICE="${ORACLE_SERVICE:-$(get_env ORACLE_SERVICE)}"; ORACLE_SERVICE="${ORACLE_SERVICE:-FREEPDB1}"
ORACLE_USER="${ORACLE_USER:-$(get_env ORACLE_USER)}";  ORACLE_USER="${ORACLE_USER:-DEVUSER}"
ORACLE_PASSWORD="${ORACLE_PASSWORD:-$(get_env ORACLE_PASSWORD)}"; ORACLE_PASSWORD="${ORACLE_PASSWORD:-DevPassword123}"

"$PY" -c "import oracledb" 2>/dev/null || die "缺少 oracledb，请先: pip install oracledb"

log "==> 目标: $ORACLE_USER@$ORACLE_HOST:$ORACLE_PORT/$ORACLE_SERVICE"

# ---------------- 2) 执行幂等升级（加列→建索引→回填→校验报告） ----------------
"$PY" - "$ORACLE_HOST" "$ORACLE_PORT" "$ORACLE_SERVICE" "$ORACLE_USER" "$ORACLE_PASSWORD" <<'PYEOF'
import sys

try:
    import oracledb
except ImportError:  # pragma: no cover
    raise SystemExit("缺少 oracledb，请先: pip install oracledb")

host, port, service, user, password = sys.argv[1:6]
dsn = f"{host}:{port}/{service}"

try:
    conn = oracledb.connect(user=user, password=password, dsn=dsn)
except Exception as e:
    raise SystemExit(f"连接 Oracle 失败: {str(e).splitlines()[0]}")
cur = conn.cursor()


def table_exists(name: str) -> bool:
    return cur.execute(
        "SELECT COUNT(*) FROM user_tables WHERE table_name=:1", (name,)
    ).fetchone()[0] > 0


def col_exists(table: str, col: str) -> bool:
    return cur.execute(
        "SELECT COUNT(*) FROM user_tab_columns WHERE table_name=:1 AND column_name=:2",
        (table, col),
    ).fetchone()[0] > 0


def idx_exists(name: str) -> bool:
    return cur.execute(
        "SELECT COUNT(*) FROM user_indexes WHERE index_name=:1", (name,)
    ).fetchone()[0] > 0


# ---------- 0) 前置检查：表必须已初始化（全新库请先建表再升级） ----------
if not table_exists("T_AGENT"):
    print("[ABORT] 线上库还没有 T_AGENT 表（全新库未初始化）。请先执行: bash migration.sh（会先跑 oracle_bootstrap 建表）")
    sys.exit(2)
if not table_exists("T_SCENE"):
    print("[ABORT] 缺少 T_SCENE 表，无法回填归属。请先执行: bash migration.sh")
    sys.exit(2)

before_total = cur.execute("SELECT COUNT(*) FROM t_agent").fetchone()[0]
before_null = cur.execute("SELECT COUNT(*) FROM t_agent WHERE user_id IS NULL").fetchone()[0]
print(f"[1/4] 升级前: t_agent 共 {before_total} 条, user_id 为空 {before_null} 条")

# ---------- 1) 加列（幂等） ----------
if col_exists("T_AGENT", "USER_ID"):
    print("[2/4] 列 t_agent.user_id 已存在, 跳过")
else:
    cur.execute("ALTER TABLE t_agent ADD (user_id VARCHAR2(128))")
    print("[2/4] 已新增列 t_agent.user_id VARCHAR2(128)")

# ---------- 2) 建索引（幂等） ----------
if idx_exists("IX_T_AGENT_USER_ID"):
    print("[3/4] 索引 ix_t_agent_user_id 已存在, 跳过")
else:
    cur.execute("CREATE INDEX ix_t_agent_user_id ON t_agent(user_id)")
    print("[3/4] 已创建索引 ix_t_agent_user_id")

# ---------- 3) 回填（幂等; 语义与后端 bootstrap 一致, 标量子查询无行→NULL） ----------
cur.execute(
    """UPDATE t_agent a
          SET a.user_id = (SELECT s.user_id FROM t_scene s WHERE s.scene_id = a.scene_id)
        WHERE a.user_id IS NULL"""
)
n = cur.rowcount
conn.commit()
print(f"[4/4] 回填完成: 本次更新 {n} 条 (已有 user_id 的不动)")

# ---------- 4) 校验报告 ----------
after_total = cur.execute("SELECT COUNT(*) FROM t_agent").fetchone()[0]
owned = cur.execute("SELECT COUNT(*) FROM t_agent WHERE user_id IS NOT NULL").fetchone()[0]
still_null = cur.execute("SELECT COUNT(*) FROM t_agent WHERE user_id IS NULL").fetchone()[0]
fallback_visible = cur.execute(
    """SELECT COUNT(*) FROM t_agent a
       WHERE a.user_id IS NULL
         AND EXISTS (SELECT 1 FROM t_scene s
                      WHERE s.scene_id = a.scene_id AND s.user_id IS NOT NULL)"""
).fetchone()[0]

print(f"      校验: 总数 {after_total}, 已归属 {owned}, 仍为空 {still_null}")
if still_null:
    print(f"      剩余 {still_null} 条: 其中 {fallback_visible} 条场景有主 → 控制台按场景归属兜底仍可见;"
          f" 其余为无主/无场景的历史孤儿数据, 本次升级不动它们（原行为不变）")
else:
    print("      所有智能体均已归属, 无历史残留")
conn.close()
print("升级完成：零数据丢失、幂等、可重复执行。")
PYEOF
