# 存储迁移说明书：PostgreSQL(pgvector) + Qdrant → Oracle 26ai (AI Vector Search)

> 目标：把记忆系统的「关系表（原 PostgreSQL/pgvector）+ 向量检索（原 Qdrant）」**彻底切换**到
> 单个 **Oracle Database 26ai Free**，关系表与 AI 向量**同库同表**（`T_MEMORY.embedding` 用 Oracle
> `VECTOR` 类型做语义检索，关键词检索用 jieba 分词 + `INSTR`，不依赖外部中间件）。
>
> 迁移完成后：**PostgreSQL、Qdrant 全部弃用**（可停用对应容器）。

---

## 1. 迁移前环境

| 项 | 迁移前 | 迁移后 |
|----|--------|--------|
| 关系库 | PostgreSQL 16 + pgvector | Oracle 26ai Free（FREEPDB1） |
| 向量库 | Qdrant（dense + sparse BM25） | Oracle `VECTOR(1024)` + `VECTOR_DISTANCE` |
| 关键词 | Qdrant sparse | jieba 分词 + `INSTR(content, :tok)` |
| 连接驱动 | asyncpg | python-oracledb（`oracle+oracledb_async`） |
| 建表方式 | alembic 迁移 | `scripts/oracle_bootstrap.py`（幂等 `create_all`） |
| 端口 | PG:5432 / Qdrant:6333 | Oracle:1521（`FREEPDB1` / `DEVUSER`） |

---

## 2. 需要的产物

| 文件 | 作用 |
|------|------|
| `migration/setup_oracle_user.sh` | 用 oracledb 一键创建 DEVUSER 并授权（幂等） |
| `migration/01_oracle_setup.sql` | 等价手动 SQL（供 DBA 执行 / 存档） |
| `migration/migrate_env.py` | 自动迁移旧 `.env` → 新 Oracle `.env` |
| `migration/.env.after` | 迁移后 `.env` 参考样例 |
| `migration/verify_migration.sh` | 迁移后一键健康检查 |
| `memProject/scripts/oracle_bootstrap.py` | 幂等建表 + `embedding` 列 + 向量/全文索引 |

| `migration/verify_migration.sh` | 迁移后一键健康检查 |
| `migration/migrate_data.py` | **真实数据**迁移：旧 PG 表 + Qdrant 向量 → Oracle |
| `memProject/scripts/oracle_bootstrap.py` | 幂等建表 + `embedding` 列 + 向量/全文索引 |
---

## 3. 迁移步骤（一键）

在**仓库根目录**执行脚本（脚本会自动定位）：

```bash
cd /home/lc/agent_mem

# (可选项) 如果还没有 conda/python 环境，先准备（需 oracledb + SQLAlchemy + pydantic-settings）
#   conda create -n mem python=3.12
#   conda activate mem
#   pip install -r memProject/requirements.txt

# 第 0 步：确认 Oracle 已启动，端口 1521 可达，PDB=FREEPDB1
#   （参考 /home/lc/oracle-26ai-free-docker-compose： docker compose up -d）

# 第 1 步：创建 DEVUSER 并授权（幂等；需 SYSTEM/ORACLE_PWD，默认 OraclePassword123）
bash migration/setup_oracle_user.sh
# 参数示例： bash migration/setup_oracle_user.sh "127.0.0.1" 1521 "FREEPDB1" "SYSTEM" "OraclePassword123"

# 第 2 步：迁移 .env（读现有 .env，补 Oracle 配置；默认生成 .env.oracle 供审查）
python migration/migrate_env.py --in .env --out .env.oracle
# 确认无误后替换：
cp .env.oracle .env

# 第 3 步：幂等建表 + embedding 列 + 索引（读取 settings 里的 ORACLE_*）
cd memProject
PYTHONPATH=$PWD python scripts/oracle_bootstrap.py
cd ..

# 第 4 步：验证迁移
bash migration/verify_migration.sh
```

---

## 3.5 数据迁移 + 重新构建 + 部署 一键脚本（`migration.sh`）

仓库根的 `migration.sh` 只负责三件事：**迁移数据**（建表 + PG/Qdrant→Oracle）、**重新 build**、
**部署**（compose up + 健康检查）。**不含任何换源（NPM/PIP/Docker 镜像源）逻辑**。

**完整部署（首次 / 迁移后）**：

```bash
cd /home/lc/agent_mem
PYTHON=/home/lc/miniforge3/envs/mem/bin/python bash migration.sh
#   依次执行：幂等建表 -> 数据迁移 -> docker compose build -> docker compose up -d -> 健康检查
```

**拆分开关**：

| 参数 | 作用 |
|------|------|
| `--skip-build` | 不重建镜像（只迁移 + 部署） |
| `--skip-migrate` | 跳过数据迁移（只重建 + 部署） |
| `--skip-init-tables` | 跳过建表（只迁移数据 + 部署） |
| `--no-verify` | 部署后不做健康检查 |
| `--help` | 打印用法 |

要点：
- Oracle 在**宿主机**运行：`.env` 的 `ORACLE_HOST` 需填**本机/宿主机可路由 IP**（如 `211.87.232.203`），
  不能用 `127.0.0.1`（容器内 `127.0.0.1` 指向容器自身，连不上宿主 Oracle）。
- 数据迁移在旧库未运行/已迁移过时会提示"可忽略"错误，**不中断**后续 build/部署。
- Oracle 不可达 / 缺 oracledb 库时会先报错停下并提示。

---

## 4. Oracle 用户创建（第 1 步细节）

DEVUSER 需要的关键权限（脚本已自动授予）：

- `CONNECT`、`RESOURCE`、`CREATE SESSION`、`UNLIMITED TABLESPACE`
- `CREATE TABLE / VIEW / SEQUENCE / TYPE / ...`
- `CREATE VECTOR INDEX`（需要普通建表权限即可，无需额外向量权限）
- `ALTER ANY TABLE / DROP ANY TABLE / CREATE ANY TABLE`（便于 create_all 幂等管理）

> **重要**：`VECTOR` 列**必须建在 ASSM 表空间**（默认 `USERS` 即可）。
> 不要建在 `SYSTEM`：会报 `ORA-43853: VECTOR type cannot be used in non-ASSM tablespace`。

---

## 5. `.env` 迁移（第 2 步细节）

新 `.env` 关键变更：

| 旧键 | 新键 | 说明 |
|------|------|------|
| `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME` | `ORACLE_HOST/ORACLE_PORT/ORACLE_USER/ORACLE_PASSWORD/ORACLE_SERVICE` | Oracle 连接（SERVICE 用 PDB `FREEPDB1`） |
| `QDRANT_HOST/QDRANT_PORT/...` | （删除） | 向量存储并入 Oracle，不再需要 Qdrant |
| `POSTGRES_*` | （删除） | 不再需要 PostgreSQL |
| `REDIS_URL` | 保留 | Kafka/Redis 仍保留（可选降级路径） |
| `MCP_BASE_URL` | 保留 | openmemory 已移出 compose，连不上走降级（非致命） |

`migrate_env.py` 会：
- 保留原有 `DEEPSEEK_*` / `SILICONFLOW_*` / `SECRET_KEY` / `JWT_SECRET_KEY` / `VITE_*` / `KAFKA_*` / `REDIS_*` 等。
- 删除已弃用的 `DB_*` / `QDRANT_*` / `POSTGRES_*`。
- 追加/覆盖 `ORACLE_*`。

---

## 5.5 真实数据迁移：旧 PG 表 + Qdrant 向量 → Oracle（`migrate_data.py`）

前置：
- 旧库仍在运行：PostgreSQL（默认 `127.0.0.1:5433`，用户 `memuser`）+ Qdrant（`127.0.0.1:6333`）
- Oracle 已建表（先跑 `python memProject/scripts/oracle_bootstrap.py`），目标表为空
- 依赖：`psycopg2-binary`、`qdrant-client`、`oracledb`、`sqlalchemy`

```bash
cd /home/lc/agent_mem

# 0) 先统计不写（dry-run）
PYTHONPATH=$PWD/memProject python migration/migrate_data.py --dry-run --verbose

# 1) 真实迁移（写入 Oracle）
PYTHONPATH=$PWD/memProject python migration/migrate_data.py --verbose

# 仅迁记忆+向量（t_memory + qdrant 的 embedding）
PYTHONPATH=$PWD/memProject python migration/migrate_data.py --only memory --verbose
```

迁移内容：
| 数据源 | 落点 | 处理 |
|--------|------|------|
| 全部有数据的 PG 表（t_memory/t_user/t_session/t_interaction_record/t_scene_block/t_persona/t_memory_cursor/t_dedup_audit/t_api_log 等） | 同名 Oracle 表 | JSON 列→CLOB 文本；时间列(+08:00)→UTC naive TIMESTAMP(6) |
| Qdrant `agent_mem_generation` 的 dense 向量 | `t_memory.embedding`（`VECTOR(1024)`） | 按 `payload.memory_id` 匹配，稳定取 dense（忽略 bm25 稀疏向量） |
| `t_memory.seq_id` | 保留原值 | 并把 Oracle `T_MEMORY_SEQ_ID_SEQ` 跳到 max+1 |
| `t_interaction_record.id` 等 | 保留原 id | 把对应 Oracle 序列调到 max+1 |

⚠ 注意：
- **不是幂等的**：重复执行会因主键冲突失败，请先清空 Oracle 目标表再迁移
  （或只跑 `--only memory` 增量补向量）。
- `migrate_data.py` 会读取 `app.core.config`（即 `ORACLE_*` 环境变量/.env），Oracle 连接参数也可用 `--oracle-*` 显式覆盖。

---

## 6. compose / Dockerfile 说明

- `docker-compose.yml`：已移除 `postgres`、`qdrant`、`openmemory` 三个服务；backend 通过
  `extra_hosts: host.docker.internal` 访问**宿主机** Oracle（Linux 亦可）。
- `memProject/Dockerfile`：`CMD` 由 `alembic upgrade head` 改为
  `python scripts/oracle_bootstrap.py && exec uvicorn ...`（先建表再启动）。

---

## 7. 已知注意事项 / 已知取舍

1. **HNSW 向量索引在本机 Free 容器可能建不起来**（`ORA-51962: vector memory area out of space`）：
   Free 版默认 `VECTOR_MEMORY_SIZE` 很小。应用已做**容错降级为顺序扫描**（`VECTOR_DISTANCE` 排序检索仍然可用）。
   如需启用索引：以 SYS 调大 `VECTOR_MEMORY_SIZE`（见下）。
2. **mem0 双写**：`mem0ai==2.0.10` 自带的 `MemoryConfig` 不认 `oracledb` provider → mem0 初始化失败，
   应用走**自研检索/向量路径**（已验证），mem0 双写降级为非致命。
   如果后续升级 mem0 支持 Oracle 提供者，可切回。
3. **Kafka 不可用时 write 自动降级**为同步落 L0（`degraded: true`）。
4. **时间列精度**：应用现用 `TIMESTAMP(6)`（微秒）替代 Oracle `DATE`（秒），修复 L3 增量游标同秒漏判。
5. **旧容器**（`mem-postgres`、`mem-qdrant`、`mem-backend`、`mem-openmemory`）为迁移前旧栈，可停用清理。

### 启用 HNSW 向量索引（可选，需 SYS）
```sql
-- 以 SYS 连 CDB 执行
ALTER SYSTEM SET vector_memory_size=100M SCOPE=BOTH;
ALTER PLUGGABLE DATABASE ALL SAVE STATE;   -- 使 PDB 恢复时保持 OPEN
```
然后重跑 `python memProject/scripts/oracle_bootstrap.py` 建索引。

---

## 8. 验证项速查

见 `migration/verify_migration.sh`，会自动检查：
- Oracle 1521 连通（`SELECT 1 FROM dual`）
- 18 张业务表存在、`T_MEMORY.EMBEDDING` VECTOR 列存在
- 索引（`T_MEMORY_CONTENT_IDX` 全文 / `T_MEMORY_EMBEDDING_IDX` 向量，后者可能未建=顺序扫描）
- `.env` 关键键齐全
