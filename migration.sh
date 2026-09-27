#!/usr/bin/env bash
# ============================================================================
# 智能体记忆系统 —— 数据迁移 + 重新构建 + 部署 一键脚本
#
# 职责（仅这三项，不含任何换源/改 Dockerfile 逻辑）：
#   1) 迁移数据：旧 PostgreSQL(pgvector) + Qdrant -> Oracle 26ai (AI Vector Search)
#      （含幂等建表 + VECTOR 列 + 全文索引）
#   2) 重新 build：docker compose build
#   3) 部署：docker compose up -d + 健康检查
#
# 用法（在仓库根目录）:
#   bash migration.sh                        # 建表+迁移数据 + 重建镜像 + 部署 + 健康检查
#   bash migration.sh --skip-build           # 不重建镜像（只迁移+部署）
#   bash migration.sh --skip-migrate         # 跳过数据迁移（只重建+部署）
#   bash migration.sh --skip-init-tables     # 跳过建表（只迁移数据）
#   bash migration.sh --no-verify            # 部署后不跑健康检查
#   bash migration.sh --help
#
# 说明：
#   - Oracle 26ai 在【宿主机】独立运行（.env 的 ORACLE_HOST 需填本机可路由 IP，如 211.87.232.203）。
#   - backend 容器内通过该 IP 访问宿主机 Oracle。
# ============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ---------------- 参数解析 ----------------
DO_BUILD=1
DO_MIGRATE=1
DO_INIT_TABLES=1
DO_VERIFY=1
PYTHON_BIN="${PYTHON:-python3}"

usage() {
  sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build)          DO_BUILD=0;;
    --skip-migrate)        DO_MIGRATE=0;;
    --skip-init-tables)    DO_INIT_TABLES=0;;
    --no-verify)           DO_VERIFY=0;;
    -h|--help)             usage;;
    *) echo "未知参数: $1"; usage;;
  esac
  shift
done

log() { echo -e "\033[1;34m[migration]\033[0m $*"; }
err() { echo -e "\033[1;31m[migration ERROR]\033[0m $*" >&2; }
die() { err "$*"; exit 1; }

get_env() { grep -m1 "^$1=" .env 2>/dev/null | cut -d= -f2- | tr -d '[:space:]' || true; }

# ---------------- 前置检查 ----------------
log "==> 检查工具链"
command -v docker >/dev/null || die "缺少 docker"
"$PYTHON_BIN" -c "import oracledb" 2>/dev/null || \
  die "缺少 oracledb 库：请先 pip install -r memProject/requirements.txt (或指定 PYTHON=<解释器>)"

if [[ ! -f .env ]]; then
  log "==> 未找到 .env，从 .env.example 复制（请用真实 Key 替换 DEEPSEEK_API_KEY / SILICONFLOW_API_KEY）"
  cp .env.example .env || die "复制 .env 失败"
fi

ORACLE_HOST="${ORACLE_HOST-$(get_env ORACLE_HOST)}";  ORACLE_HOST="${ORACLE_HOST:-127.0.0.1}"
ORACLE_PORT="${ORACLE_PORT-$(get_env ORACLE_PORT)}";  ORACLE_PORT="${ORACLE_PORT:-1521}"
ORACLE_SERVICE="${ORACLE_SERVICE-$(get_env ORACLE_SERVICE)}"; ORACLE_SERVICE="${ORACLE_SERVICE:-FREEPDB1}"
ORACLE_USER="${ORACLE_USER-$(get_env ORACLE_USER)}";  ORACLE_USER="${ORACLE_USER:-DEVUSER}"
ORACLE_PASSWORD="${ORACLE_PASSWORD-$(get_env ORACLE_PASSWORD)}"; ORACLE_PASSWORD="${ORACLE_PASSWORD:-DevPassword123}"

log "==> 检查 Oracle 可达: $ORACLE_HOST:$ORACLE_PORT/$ORACLE_SERVICE (user=$ORACLE_USER)"
if ! timeout 5 bash -c "cat < /dev/null > /dev/tcp/$ORACLE_HOST/$ORACLE_PORT" 2>/dev/null; then
  die "Oracle $ORACLE_HOST:$ORACLE_PORT 不可达。请确认 .env 的 ORACLE_HOST 填的是本机/宿主机可路由 IP（如 211.87.232.203），并确认宿主机 Oracle 已启动"
fi
log "   ✓ Oracle 端口可达"

export ORACLE_HOST ORACLE_PORT ORACLE_SERVICE ORACLE_USER ORACLE_PASSWORD

# ---------------- 1) 建表 + 数据迁移 ----------------
if [[ "$DO_INIT_TABLES" == "1" ]]; then
  log "==> 幂等建表 + VECTOR 列 + 全文索引 (memProject/scripts/oracle_bootstrap.py)"
  ( cd memProject && PYTHONPATH="$PWD" "$PYTHON_BIN" scripts/oracle_bootstrap.py ) \
      && log "   建表完成" || die "建表失败，见上方错误"
fi

if [[ "$DO_MIGRATE" == "1" ]]; then
  log "==> 数据迁移：旧 PG(pgvector) + Qdrant -> Oracle（migration/migrate_data.py）"
  if [[ -f migration/migrate_data.py ]]; then
    if "$PYTHON_BIN" -c "import psycopg2" 2>/dev/null; then
      PYTHONPATH="$REPO_ROOT/memProject" "$PYTHON_BIN" migration/migrate_data.py --verbose || \
          err "数据迁移返回非 0（旧库可能未运行/无数据/已迁移过；可忽略并手动迁移）"
    else
      log "   跳过：未检测到 psycopg2（旧 PG 数据迁移依赖它），仅建表"
    fi
  else
    log "   跳过：缺少 migration/migrate_data.py"
  fi
fi

# ---------------- 2) 重新 build ----------------
if [[ "$DO_BUILD" == "1" ]]; then
  log "==> 重新构建镜像（docker compose build）"
  docker compose build || die "镜像构建失败"
else
  log "==> 跳过重建（--skip-build）"
fi

# ---------------- 3) 部署 ----------------
log "==> 启动部署（docker compose up -d）"
docker compose up -d || die "compose up 失败"
log "   ✓ compose 已启动 (redis / kafka / kafka-ui / backend / frontend)"

# ---------------- 4) 健康检查（可选） ----------------
if [[ "$DO_VERIFY" == "1" ]]; then
  log "==> 等待后端就绪 (最多 90 秒)"
  BACKEND_PORT_V="$(get_env BACKEND_PORT)"
  BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT_V:-8000}}"
  ok=0
  for i in $(seq 1 18); do
    if curl -sf -m 3 "$BACKEND_URL/api/v1/health" >/dev/null 2>&1; then
      log "   ✓ 后端健康检查通过: $BACKEND_URL/api/v1/health"
      ok=1
      break
    fi
    sleep 5
  done
  if [[ "$ok" != "1" ]]; then
    err "后端 $i/18 未就绪。查看: docker compose logs -f backend"
  fi
  log "==> 迁移验证（migration/verify_migration.sh）"
  if [[ -f migration/verify_migration.sh ]]; then
    PYTHON="$PYTHON_BIN" bash migration/verify_migration.sh || true
  fi
fi

log "==============================================="
log " ✓ 部署完成"
log "   前端: http://localhost:$(get_env FRONTEND_PORT)"
log "   后端: http://localhost:$(get_env BACKEND_PORT)"
log "==============================================="
