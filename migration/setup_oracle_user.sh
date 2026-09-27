#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# 用 python-oracledb 创建/校验 Oracle 26ai 应用用户（默认 DEVUSER）并授权（幂等）。
#
# 用法:
#   bash migration/setup_oracle_user.sh [HOST] [PORT] [SERVICE] [SYS_USER] [SYS_PWD] [APP_USER] [APP_PWD]
# 默认:
#   HOST=127.0.0.1  PORT=1521  SERVICE=FREEPDB1  SYS_USER=SYSTEM  SYS_PWD=OraclePassword123
#   APP_USER=DEVUSER  APP_PWD=DevPassword123
set -euo pipefail

HOST="${1:-127.0.0.1}"
PORT="${2:-1521}"
SERVICE="${3:-FREEPDB1}"
SYS_USER="${4:-SYSTEM}"
SYS_PWD="${5:-OraclePassword123}"
APP_USER="${6:-DEVUSER}"
APP_PWD="${7:-DevPassword123}"

# 定位仓库根（本脚本在 <root>/migration 下）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PY="${PYTHON:-python3}"

echo "==> 准备连接 $SYS_USER@$HOST:$PORT/$SERVICE 创建用户 $APP_USER"

"$PY" - "${HOST}" "${PORT}" "${SERVICE}" "${SYS_USER}" "${SYS_PWD}" "${APP_USER}" "${APP_PWD}" <<'PYEOF'
import sys
try:
    import oracledb
except ImportError:
    raise SystemExit("缺少 oracledb，请先: pip install oracledb (建议 >=26.0)")
host, port, service, sys_user, sys_pwd, app_user, app_pwd = sys.argv[1:8]
dsn = f"{host}:{port}/{service}"
app_user = app_user.upper()
try:
    c = oracledb.connect(user=sys_user, password=sys_pwd, dsn=dsn)
except Exception as e:
    raise SystemExit(f"连接失败(SYSTEM 凭据可能不对): {e}")

cur = c.cursor()
try:
    cur.execute("ALTER SESSION SET CURRENT_SCHEMA = %s" % app_user)
except Exception:
    pass

# 1) 幂等建用户/改密码
exists = cur.execute(
    "SELECT COUNT(*) FROM all_users WHERE username=:1", (app_user,)
).fetchone()[0]
if exists:
    cur.execute("ALTER USER %s IDENTIFIED BY %s" % (app_user, app_pwd))
    print("==> 用户 %s 已存在，已重置密码" % app_user)
else:
    cur.execute(
        "CREATE USER %s IDENTIFIED BY %s DEFAULT TABLESPACE USERS "
        "TEMPORARY TABLESPACE TEMP QUOTA UNLIMITED ON USERS" % (app_user, app_pwd)
    )
    print("==> 用户 %s 已创建" % app_user)

# 2) 授权（幂等）
def grant(priv):
    try:
        cur.execute("GRANT %s TO %s" % (priv, app_user))
    except Exception as e:
        print("   (skip) %s: %s" % (priv, str(e).splitlines()[0]))

for priv in ["CONNECT","RESOURCE","CREATE SESSION","UNLIMITED TABLESPACE",
             "CREATE TABLE","CREATE VIEW","CREATE SEQUENCE","CREATE PROCEDURE",
             "CREATE TRIGGER","CREATE TYPE","CREATE SYNONYM","CREATE DATABASE LINK",
             "CREATE MATERIALIZED VIEW","CREATE JOB",
             "SELECT ANY TABLE","INSERT ANY TABLE","UPDATE ANY TABLE","DELETE ANY TABLE",
             "EXECUTE ANY PROCEDURE","CREATE ANY TABLE","ALTER ANY TABLE","DROP ANY TABLE",
             "QUERY REWRITE","GLOBAL QUERY REWRITE","DEBUG CONNECT SESSION"]:
    grant(priv)

# 3) 校验默认表空间为 ASSM（USERS 是 ASSM，能放 VECTOR 列）
ts = cur.execute(
    "SELECT DEFAULT_TABLESPACE FROM dba_users WHERE username=:1", (app_user,)
).fetchone()
print("==> %s 默认表空间: %s (USERS=ASSM, 可存放 VECTOR)" % (app_user, ts[0] if ts else "?"))
if ts and ts[0].upper() != "USERS":
    print("  ! 注意: 若非 USERS，请确认该表空间是 ASSM，否则建 VECTOR 列会报 ORA-43853")
c.commit()
c.close()
print("==> DEVUSER 就绪: %s@%s:%s/%s" % (app_user, host, port, service))
PYEOF
