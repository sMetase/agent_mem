# 面向大模型智能体的记忆系统

基于 [mem0](https://github.com/mem0ai/mem0) 构建的智能体记忆管理中台，提供 REST API 和 memProject MCP Server。

## 架构

```
智能体 / 前端
    │
    ├── REST  → memProject FastAPI (:8000) ─┐
    │                                       ├── OpenMemory MCP (:8765, 内部存储)
    │                                       ├── PostgreSQL / Qdrant
    └── MCP   → memProject MCP (:8000/mcp/) ─┴── 高级工具适配层
```

## 从零开始

### 前置条件

| 软件 | 说明 |
|------|------|
| Python 3.12+ | 运行环境 |
| Docker Desktop | PostgreSQL + Qdrant |
| Git | 拉代码 |
| DeepSeek API Key | [platform.deepseek.com](https://platform.deepseek.com) 注册获取 |
| 硅基流动 API Key | [siliconflow.cn](https://siliconflow.cn) 注册获取 |

---

### 第一步：克隆项目

```bash
git clone <本仓库地址>
cd memProject
```

### 第二步：安装 Python 依赖

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 第三步：配置环境变量

```bash
cp .env .env
```

编辑 `.env`，填入你的 API Key：

```env
DEEPSEEK_API_KEY=sk-你的Key
SILICONFLOW_API_KEY=sk-你的Key
```

### 第四步：启动基础设施

```bash
docker compose up -d
```

确认容器运行：

```bash
docker ps --filter "name=mem-"
# 应看到 mem-postgres 和 mem-qdrant
```

### 第五步：创建数据库表

```bash
python -m alembic revision --autogenerate -m "init_schema"
python -m alembic upgrade head
```

---

### 第六步：启动 FastAPI

```bash
cd memProject
# Conda
conda run -n mem python -m uvicorn app.main:app --reload --port 8000

# 或已激活 mem 环境时
python -m uvicorn app.main:app --reload --port 8000
```

---

### 第七步：使用 backend 内置的 memProject MCP Server

MCP Server 使用 Streamable HTTP，与 REST API 共用 backend 进程，默认地址为 `http://127.0.0.1:8000/mcp/`。
它调用 memProject 的 REST API，复用 backend 连接的 OpenMemory MCP、PostgreSQL、Qdrant 和异步记忆流水线；OpenMemory 只作为内部存储，不作为外部 MCP 入口。

不需要单独启动 MCP 进程，启动 FastAPI backend 后即可使用。MCP 工具定义位于 `app/mcp_server.py`，由 `app/main.py` 挂载。

可通过环境变量配置 backend 内部调用地址：

```bash
export MEMPROJECT_API_URL=http://127.0.0.1:8000
```

VS Code 用户运行 `dev:preview` 即可同时启动前端和包含 MCP 的 backend。

#### MCP 工具

| 工具 | 用途 |
|------|------|
| `create_session` | 创建会话 |
| `write_conversation` | 写入对话消息，异步抽取记忆 |
| `write_session_summary` | 写入历史会话摘要 |
| `search_memories` | 混合语义检索记忆 |
| `get_memory_context` | 获取可直接注入 Prompt 的上下文 |
| `close_session` | 关闭会话并执行会话记忆压缩 |

#### MCP 客户端配置示例

支持 Streamable HTTP 的 MCP 客户端配置为：

```json
{
    "mcpServers": {
        "memProject": {
            "type": "http",
            "url": "http://127.0.0.1:8000/mcp/"
        }
    }
}
```

生产环境启用认证时，客户端需要同时传递：

```text
X-API-Key: 你的AgentApiKey
X-User-Id: user_001
X-Agent-Id: agent_xxx
```

MCP Server 会将客户端传入的认证请求头透传给内部 REST API，不需要配置额外的 `MEMPROJECT_MCP_API_KEY`。

#### 推荐调用顺序

```text
create_session
            ↓
write_conversation
            ↓
get_memory_context / search_memories
            ↓
close_session
```

`write_conversation` 是异步写入，返回 accepted 不代表记忆已经完成抽取。检索前应等待后台 worker 完成，或先通过 REST 接口确认处理状态。

Settings 页面中的“异步记忆消费时间”会通过 `PUT /api/v1/config/extraction-schedule` 更新运行时配置，并原子写入 `config/settings.yaml`。因此 backend 重启后仍会保留最近一次保存的消费模式、时间窗口和时区。写入只修改 `generation` 区块中的四个字段，不会覆盖其它配置或环境变量占位符。

---

### 第八步：验证

```bash
# 健康检查
curl http://localhost:8000/health

# Swagger 文档
# 浏览器打开 http://localhost:8000/docs

# 检查 MCP 工具是否注册
conda run -n mem python -c "import asyncio; from app.mcp_server import mcp; print([t.name for t in asyncio.run(mcp.list_tools())])"
```

---

## 项目结构

```
memProject/
├── app/
│   ├── main.py                  # FastAPI 入口
│   ├── core/                    # 配置、数据库、异常、安全、日志
│   ├── api/v1/                  # 6 组路由（agent/scene/session/task/memory/admin）
│   ├── models/base.py           # 12 张表 ORM
│   ├── schemas/                 # 请求/响应 Pydantic
│   ├── services/mem0_client.py  # mem0 直连（已弃用，保留备用）
│   ├── mcp_server.py            # memProject MCP Server（Streamable HTTP）
│   ├── mcp_client.py            # 旧 OpenMemory 兼容客户端（内部备用）
│   └── middleware/              # 日志、认证、异常处理
├── config/settings.yaml         # 全局配置
├── alembic/                     # 数据库迁移
├── tests/
│   ├── test_api.py              # DeepSeek/SiliconFlow 连通性
│   ├── test_mcp_4tools.py       # MCP 4 工具全量测试
│   └── debug/                   # 调试脚本
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## API 清单

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/memory/write` | 写入记忆 |
| POST | `/api/v1/memory/search` | 检索记忆 |
| POST | `/api/v1/memory/list` | 列出全部 |
| POST | `/api/v1/memory/delete-all` | 清除全部 |
| POST | `/api/v1/agent/register` | 注册智能体 |
| ... | ... | 共 33 个端点，详见 `/docs` |

## 常见问题

**Q: 8765 端口被占用？**
```bash
netstat -ano | findstr 8765
taskkill /F /PID <进程ID>
```

**Q: add_memories 返回 "Memory system is currently unavailable"？**
A: Qdrant 未启动或配置错误。确认 Docker 运行且 `docker ps` 能看到 Qdrant。

**Q: 延迟很高？**
A: `add_memories` 调用了 DeepSeek API 做记忆抽取，耗时 5-10 秒是正常的。测试时可用 `"infer": false` 跳过大模型，直存原文。

**Q: search_memory 报错？**
A: 确认已打补丁 3（删除 `limit=10` 参数）。

---