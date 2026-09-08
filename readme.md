# 智能体记忆系统

面向大模型智能体的记忆管理中台，提供 REST API、异步记忆流水线和 memProject MCP Server。

## 架构概览

```text
智能体 / 前端
    ├── REST API  -> FastAPI Backend
    │                 ├── L0 原始交互记录
    │                 ├── L1 原子记忆抽取
    │                 ├── L2 场景聚合
    │                 └── L3 用户画像
    └── MCP       -> Backend /mcp/

Backend -> PostgreSQL + Qdrant + Redis + Kafka
Backend -> OpenMemory MCP（内部存储依赖）
```

## 快速开始

部署和环境配置请参阅 [deployment.md](deployment.md)。服务启动后，默认地址如下：

| 服务 | 地址 |
| --- | --- |
| 前端 | `http://localhost:8081` |
| Backend API | `http://localhost:8000` |
| API 文档 | `http://localhost:8000/docs` |
| MCP Server | `http://localhost:8000/mcp/` |
| 健康检查 | `http://localhost:8000/health` |

端口可以通过根目录 `.env` 中的 `BACKEND_PORT`、`FRONTEND_PORT` 等变量调整。

## REST API 使用

API 前缀为 `/api/v1`。开发环境 `AUTH_ENABLED=false` 时，可以使用 `X-Agent-Id` 指定智能体；生产环境需要使用 `X-API-Key` 鉴权。

### 写入对话历史

```bash
curl -X POST http://localhost:8000/api/v1/memory/write \
  -H "Content-Type: application/json" \
  -H "X-Agent-Id: agent_dev_default" \
  -d '{
    "user_id": "user_001",
    "scene_id": "customer_service",
    "session_id": "session_001",
    "interaction_type": "dialogue",
    "messages": [
      {"role": "user", "content": "我喜欢简洁的回答"},
      {"role": "assistant", "content": "好的，后续我会尽量简洁回答。"}
    ]
  }'
```

支持三种写入类型：

| 类型 | 用途 |
| --- | --- |
| `dialogue` | 写入当前对话消息，必须提供 `messages` |
| `session` | 导入历史会话，可附带 `session_time`、`session_source`、`session_summary` |
| `task_process` | 写入任务目标、进展和结果 |

接口返回 `accepted: true` 表示数据已经写入 L0。L1、L2、L3 记忆处理由后台 Worker 异步完成，不代表记忆已经立即抽取完成。

### 语义检索记忆

```bash
curl -X POST http://localhost:8000/api/v1/memory/search \
  -H "Content-Type: application/json" \
  -H "X-Agent-Id: agent_dev_default" \
  -d '{
    "query": "用户有什么回答偏好？",
    "user_id": "user_001",
    "scene_id": "customer_service",
    "top_k": 10,
    "include_scores": true
  }'
```

`/search` 返回结构化记忆列表，包含 `memory_id`、`content`、`memory_type`、`relevance_score`、`importance` 和 `confidence` 等字段。

### 获取 Prompt 上下文

如果需要把召回结果直接注入大模型 Prompt，使用 `/context`：

```bash
curl -X POST http://localhost:8000/api/v1/memory/context \
  -H "Content-Type: application/json" \
  -H "X-Agent-Id: agent_dev_default" \
  -d '{
    "query": "用户有什么回答偏好？",
    "user_id": "user_001",
    "scene_id": "customer_service",
    "top_k": 10,
    "max_tokens": 3000,
    "group_by_type": true
  }'
```

该接口返回 `formatted_text`、`memory_count` 和 `estimated_tokens`，其中 `formatted_text` 可直接拼接到 Prompt。

生产环境请求示例：

```http
X-API-Key: 你的AgentApiKey
X-User-Id: user_001
```

更多 REST API 参阅 [memProject/API接口文档.md](memProject/API接口文档.md)。

## MCP Server 使用

Backend 内置的 memProject MCP Server 使用 Streamable HTTP，与 REST API 共用端口，不需要单独启动 MCP 进程：

```text
http://localhost:8000/mcp/
```

可用工具：

| 工具 | 用途 |
| --- | --- |
| `create_session` | 创建会话 |
| `write_conversation` | 写入对话并异步抽取记忆 |
| `write_session_summary` | 写入历史会话摘要 |
| `search_memories` | 混合语义检索记忆 |
| `get_memory_context` | 获取可直接注入 Prompt 的上下文 |
| `close_session` | 关闭会话并执行会话记忆压缩 |

### MCP 客户端配置

#### 先通过网页注册并获取凭据

1. 打开前端：`http://localhost:8081/login`。首次使用时输入用户名和密码即可注册并登录。
2. 登录后进入“智能体注册接入”页面：`http://localhost:8081/access/agents`。
3. 注册智能体并选择所属场景。注册成功后保存弹窗中显示的 `api_key` 和 `agent_id`；API Key 只会明文返回一次。
4. 记下登录接口返回的 `user_id`。之后调用 MCP 时使用以下三个值：

```text
X-API-Key: 你的AgentApiKey
X-User-Id: user_001
X-Agent-Id: agent_xxx
```

其中 `X-API-Key` 是注册智能体返回的 `api_key`，`X-Agent-Id` 是返回的 `agent_id`，`X-User-Id` 是登录用户的 `user_id`。

当前内置 MCP Server 会将 MCP 客户端请求中的 `X-API-Key`、`X-User-Id` 和 `X-Agent-Id`
透传给内部 REST API，不需要额外配置 `MEMPROJECT_MCP_API_KEY`。

支持 Streamable HTTP 的 MCP 客户端可以配置：

```json
{
  "mcpServers": {
    "memProject": {
      "type": "http",
      "url": "http://localhost:8000/mcp/"
    }
  }
}
```

生产环境启用认证时，还需要配置以下请求头：

```text
X-API-Key: 你的AgentApiKey
X-User-Id: user_001
X-Agent-Id: agent_xxx
```

#### 配置 Claude Code

将下面命令中的三个占位值替换为网页注册后保存的凭据：

```bash
claude mcp add --transport http memProject http://localhost:8000/mcp/ \
  --header "X-API-Key: 你的AgentApiKey" \
  --header "X-User-Id: user_001" \
  --header "X-Agent-Id: agent_xxx"
```

配置完成后，可以使用以下命令检查 MCP Server 是否已添加：

```bash
claude mcp list
```

如果后端部署在其他机器，请将命令中的 `http://localhost:8000/mcp/` 替换为实际的 MCP 地址。

API Key 属于敏感凭据，请不要提交到代码仓库或分享命令历史。

推荐调用顺序：

```text
create_session
      -> write_conversation
      -> get_memory_context / search_memories
      -> close_session
```

`write_conversation` 是异步写入，返回 accepted 后仍需等待后台 Worker 完成记忆抽取，再进行召回。

MCP Server 的详细实现位于 [memProject/app/mcp_server.py](memProject/app/mcp_server.py)，Worker 说明位于 [memProject/docs/各层Worker工作说明.md](memProject/docs/各层Worker工作说明.md)。

## 相关文档

- [deployment.md](deployment.md)：Docker Compose、环境变量、端口和前端部署
- [memProject/API接口文档.md](memProject/API接口文档.md)：完整 REST API
- [memProject/docs/各层Worker工作说明.md](memProject/docs/各层Worker工作说明.md)：MQ Consumer、L1、L2、L3 工作机制
- [agent-memory-frontend/README.md](agent-memory-frontend/README.md)：前端本地开发
