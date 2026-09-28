# 工作日志 — agent_mem 项目重建

> **2026-09-28 注**：项目已迁移至 Oracle 26ai，不再使用 PostgreSQL / pgvector / Qdrant / OpenMemory。
> 以下日志为迁移前的历史记录，仅作存档。

**日期**: 2026-07-03
**操作**: 按最新仓库教程完整重建

---

## 背景

远程仓库发生强制推送（forced update: `a5c564a` → `7e8c699`），项目从单体 FastAPI 重构为双服务架构：

- **memProject** — FastAPI 记忆管理中台（端口 8000）
- **mem0_repo** — Mem0 开源记忆层 + OpenMemory MCP Server（端口 8765）

旧文件（tools/pgsql, WORKLOG.md, start.bat 等）已通过 `git clean -fd` 清理。

---

## 完成事项

### 1. 代码同步
- 执行 `git reset --hard origin/master`，本地与远程一致
- 新结构：`memProject/` + `mem0_repo/` + `.claude/` + `tools/`

### 2. Docker Desktop
- WSL2 docker-desktop 已可用（上次会话因 WSL 未安装导致无法启动）
- 容器 `mem-postgres`（pgvector/pgvector:pg16）和 `mem-qdrant`（qdrant/qdrant:latest）已恢复运行
- 数据库 `agent_memory` 已有 13 张表（含 alembic_version）

### 3. Python 环境
- 使用 conda 环境 `agent_mem`（Python 3.12.13）
- memProject 依赖已安装（`pip install -r requirements.txt`）
- mem0_repo/openmemory/api 依赖已安装

### 4. 环境变量 (.env)
- 路径：`E:\AI Memory\agent_mem\.env` 和 `E:\AI Memory\agent_mem\memProject\.env`
- `DEEPSEEK_API_KEY`: `sk-83aa21679b634d9e90b866e9a94cc637` ✅
- `SILICONFLOW_API_KEY`: `sk-gsuqwhwfuajautyxuxvwenjhwszvzbbtizkjlugorlzuvqze` ✅
- 数据库连接、JWT Secret 均已配置

### 5. OpenMemory MCP Server 配置
- 三处代码补丁已内置在新代码中（无需手动修改）
- DeepSeek API Key 已更新到 `memory.py` 硬编码配置
- SQLite 数据库 `openmemory.db` 配置已写入，含 `openai_base_url`
  - LLM: deepseek-chat @ `https://api.deepseek.com/v1`
  - Embedder: BAAI/bge-m3 @ `https://api.siliconflow.cn/v1`

### 6. 验证结果

| 测试项 | 结果 |
|--------|------|
| DeepSeek LLM 连接 | ✅ |
| SiliconFlow Embedding (1024维) | ✅ |
| PostgreSQL 连接 | ✅ |
| Qdrant 连接 | ✅ |
| MCP add_memories（记忆写入+LLM提取） | ✅ |
| MCP search_memory（语义检索） | ✅ |
| MCP list_memories（列出记忆） | ✅ |
| MCP delete_all_memories（清除记忆） | ✅ |
| memProject API /health | ✅ `{"status":"ok"}` |
| memProject API /api/v1/memory/write → search | ✅ 全链路 |

---

## 启动命令

### 环境准备
```bash
# SSL 证书（必须）
export SSL_CERT_FILE="E:/anaconda3/envs/agent_mem/Lib/site-packages/certifi/cacert.pem"
```

### 启动数据库（Docker Desktop 须先运行）
```bash
docker start mem-postgres mem-qdrant
```

### 启动 OpenMemory MCP Server（端口 8765）
```bash
cd "E:/AI Memory/agent_mem/mem0_repo/openmemory/api"
source activate agent_mem
export SSL_CERT_FILE="E:/anaconda3/envs/agent_mem/Lib/site-packages/certifi/cacert.pem"
export QDRANT_HOST=localhost QDRANT_PORT=6333
export OPENAI_API_KEY=sk-83aa21679b634d9e90b866e9a94cc637
uvicorn main:app --host 0.0.0.0 --port 8765
```

### 启动 memProject FastAPI（端口 8000）
```bash
cd "E:/AI Memory/agent_mem/memProject"
source activate agent_mem
export SSL_CERT_FILE="E:/anaconda3/envs/agent_mem/Lib/site-packages/certifi/cacert.pem"
uvicorn app.main:app --reload --port 8000
```

### 运行测试
```bash
# API 连通性测试
cd "E:/AI Memory/agent_mem/memProject"
source activate agent_mem
export SSL_CERT_FILE="E:/anaconda3/envs/agent_mem/Lib/site-packages/certifi/cacert.pem"
python tests/test_api.py

# MCP 四工具测试
python tests/test_mcp_4tools.py
```

---

## 关键文件路径

| 文件 | 路径 |
|------|------|
| memProject 根目录 | `E:\AI Memory\agent_mem\memProject\` |
| MCP Server 根目录 | `E:\AI Memory\agent_mem\mem0_repo\openmemory\api\` |
| MCP 配置文件（硬编码） | `.../api/app/utils/memory.py` |
| MCP Server 入口 | `.../api/app/mcp_server.py` |
| SQLite 配置数据库 | `.../api/openmemory.db` |
| memProject MCP Client | `memProject/app/mcp_client.py` |
| 环境变量 | `E:\AI Memory\agent_mem\.env` |
| Docker Compose | `memProject/docker-compose.yml` |

---

## 架构图

```
memProject (FastAPI :8000)            OpenMemory MCP Server (:8765)
┌──────────────────────┐    MCP      ┌───────────────────────────┐
│ app/mcp_client.py    │──Streamable─→│ add_memories              │
│ app/api/v1/memory.py │   HTTP      │ search_memory            │
│                      │             │ list_memories            │
│ PostgreSQL :5432     │             │ delete_all_memories      │
│ (agent_memory DB)    │             │     ↓                    │
└──────────────────────┘             │ DeepSeek (deepseek-chat) │
                                     │ SiliconFlow (bge-m3)     │
                                     │ Qdrant :6333             │
                                     │ SQLite (openmemory.db)   │
                                     └───────────────────────────┘
```

---

# 工作日志 — 记忆生成与去重融合功能实现

**日期**: 2026-07-06

## 背景

按设计文档实现「记忆生成与去重融合」完整模块：关键记忆抽取 + 结构化记忆生成 + 去重融合处理。

## 新增文件 (14 个)

| 文件 | 说明 |
|------|------|
| `app/prompts/__init__.py` | Prompt 导出 |
| `app/prompts/key_fact_extraction.py` | 关键事实抽取 Prompt |
| `app/prompts/task_state_extraction.py` | 任务状态抽取 Prompt |
| `app/prompts/decision_extraction.py` | 历史决策抽取 Prompt |
| `app/prompts/memory_generation.py` | 记忆生成 Prompt |
| `app/services/llm_client.py` | DeepSeek LLM 客户端（JSON mode + 重试 + regex 降级） |
| `app/services/embedding_client.py` | SiliconFlow 嵌入客户端（bge-m3, 1024 维） |
| `app/services/memory_extractor.py` | 三大抽取器 + Facade 并行调度 |
| `app/services/memory_generator.py` | 结构化记忆生成 |
| `app/services/memory_dedup.py` | 六阶段去重引擎 |
| `app/services/memory_pipeline.py` | 完整流水线编排 |
| `app/core/qdrant_client.py` | Qdrant gRPC 单例 |
| `app/schemas/generation.py` | Pydantic 请求/响应模型 |
| `app/api/v1/generation.py` | 4 个 API 端点 |

## 修改文件 (2 个)

- `app/api/v1/router.py` — +1 行注册 generation 路由
- `app/services/__init__.py` — 合并上游 validation_service + 新服务导出

## 测试

- `tests/test_memory_generation.py` — 24 个单元测试，全部通过
- `tests/debug/test_generation_e2e.py` — E2E 演示（basic/full/dedup 三种模式）

## 验证

| 项目 | 结果 |
|------|------|
| DeepSeek LLM 连接 | ✅ |
| SiliconFlow Embedding | ✅ |
| 关键事实/任务状态/决策抽取 | ✅ |
| 结构化记忆生成（含评分） | ✅ |
| 去重决策矩阵 (4 路径) | ✅ |
| Git push (fe98a45) | ✅ |

## API 端点

- POST `/api/v1/memory/generate` — 同步生成
- POST `/api/v1/memory/generate/batch` — 批量生成
- POST `/api/v1/memory/generate/async` — 异步提交
- GET `/api/v1/memory/generate/{id}/status` — 查询状态

## 流程

```
extract(text) → generate(extraction) → dedup(candidates) → store(PG + Qdrant)
```
