# 智能体记忆系统依赖版本说明

本文档整理了该项目当前使用到的 Docker 镜像、核心依赖及部署方式，版本依据来自：

- docker-compose.yml
- memProject/Dockerfile
- mem0_repo/openmemory/api/Dockerfile
- agent-memory-frontend/Dockerfile
- memProject/requirements.txt

> 说明：Qdrant 和 Kafka UI 使用 `latest`，构建时可能随时间更新；其余基础镜像使用明确版本或由本地 Dockerfile 构建。

## 1. Docker 镜像清单

### 1.1 Compose 直接使用的镜像

| 服务 | 镜像 | 作用 | 容器端口 |
| --- | --- | --- | --- |
| PostgreSQL | `pgvector/pgvector:pg16` | 主数据库与 pgvector 向量扩展 | `5433 -> 5432` |
| Qdrant | `qdrant/qdrant:latest` | 向量检索引擎 | `6333 -> 6333`、`6334 -> 6334` |
| Redis | `redis:7-alpine` | 缓存与结果轮询 | `6379 -> 6379` |
| Kafka | `apache/kafka:3.7.2` | 消息总线与异步写入队列 | `9092 -> 9092`、`9093 -> 9093` |
| Kafka UI | `provectuslabs/kafka-ui:latest` | Kafka 管理界面 | `8080 -> 8080` |

### 1.2 项目自行构建的镜像

| 服务 | Dockerfile 基础镜像 | 作用 | 容器端口 |
| --- | --- | --- | --- |
| OpenMemory | `python:3.12-slim` | Mem0 MCP Server、记忆生成与向量写入 | `8765` |
| Backend | `python:3.12-slim` | FastAPI API、L1/L2/L3 worker | `8000` |
| Frontend 构建阶段 | `node:24.20.0-alpine3.24` | 安装 pnpm 依赖并构建 React/Vite | 仅构建阶段 |
| Frontend 运行阶段 | `nginx:1.27-alpine` | 托管前端静态文件 | `8081 -> 80` |

前端采用多阶段构建，最终运行容器只包含 `nginx:1.27-alpine` 和构建后的静态文件。OpenMemory 与 Backend 的最终镜像由项目 Dockerfile 基于 `python:3.12-slim` 构建，Compose 不需要单独拉取带有固定仓库名的业务镜像。

## 2. Python 运行时依赖

| 组件 | 版本 | 作用 |
| --- | --- | --- |
| FastAPI | `0.138.2` | Web API 框架 |
| SQLAlchemy | `2.0.51` | ORM / 数据访问层 |
| asyncpg | `0.31.0` | PostgreSQL 异步驱动 |
| psycopg2-binary | `2.9.12` | PostgreSQL Python 驱动 |
| aiokafka | `0.14.0` | Kafka 异步客户端 |
| qdrant-client | `1.18.0` | Qdrant Python 客户端 |
| redis | `5.0.1` | Redis 客户端/异步消息等待 |
| openai | `2.44.0` | OpenAI SDK / 兼容 API 调用 |
| ollama | `0.6.2` | 本地模型/嵌入服务客户端 |
| neo4j | `6.2.0` | 图数据库支持 |
| mem0ai | `2.0.10` | Mem0 记忆框架支持 |
| pydantic | `2.13.4` | 数据校验与配置模型 |
| uvicorn | `0.49.0` | ASGI 服务启动器 |

## 3. 关键技术栈概览

这个项目的核心技术栈可以概括为：

- 数据库：PostgreSQL + pgvector
- 向量检索：Qdrant
- 消息队列：Kafka
- 缓存：Redis
- MCP 服务：OpenMemory / Mem0
- API 框架：FastAPI
- 编排/运行：Docker Compose
- Python 依赖管理：requirements.txt

## 4. 需要注意的版本差异

- Qdrant 的 Docker 镜像使用 `latest`，因此不稳定，可能随时间更新；Python 端的 `qdrant-client` 则是固定到 `1.18.0`。
- Kafka 使用 Apache 官方镜像 `apache/kafka:3.7.2`，采用 KRaft 单节点模式；容器内服务通过 `kafka:9093` 连接，宿主机通过 `localhost:9092` 连接。
- PostgreSQL 是 `pgvector/pgvector:pg16`，说明项目使用 PostgreSQL 16 及其 pgvector 扩展。

## 5. 统一 Docker Compose 部署

在仓库根目录准备 `.env`，至少填写模型服务密钥：

```bash
DEEPSEEK_API_KEY=你的DeepSeek_Key
SILICONFLOW_API_KEY=你的SiliconFlow_Key
```

启动全部服务：

```bash
docker compose up -d --build
```

查看服务状态和日志：

```bash
docker compose ps
docker compose logs -f backend
```

后端容器启动时会先执行 `alembic upgrade head`，初始化当前完整数据库结构，再以单 worker 启动 FastAPI。常用访问地址：

| 服务 | 地址 |
| --- | --- |
| 前端 | `http://localhost:8081` |
| 后端健康检查 | `http://localhost:8000/health` |
| OpenMemory | `http://localhost:8765` |
| Kafka UI | `http://localhost:8080` |
| Qdrant | `http://localhost:6333` |

停止服务：

```bash
docker compose down
```

如需清空数据库、向量和消息队列数据，才使用：

```bash
docker compose down -v
```

---

# 前后端部署步骤说明

本文档整理了本项目的统一 Docker Compose 部署方式，依据的实际文件包括：

- [docker-compose.yml](docker-compose.yml)
- [memProject/Dockerfile](memProject/Dockerfile)
- [mem0_repo/openmemory/api/Dockerfile](mem0_repo/openmemory/api/Dockerfile)
- [agent-memory-frontend/Dockerfile](agent-memory-frontend/Dockerfile)
- [agent-memory-frontend/智能体记忆系统前端部署说明.md](agent-memory-frontend/智能体记忆系统前端部署说明.md)

## 1. 部署总览

该项目的部署大致分为 3 层：

1. 基础设施层：PostgreSQL + pgvector、Qdrant、Redis、Kafka
2. 后端服务层：FastAPI + OpenMemory MCP Server
3. 前端静态层：React/Vite 构建产物 + nginx

整体结构如下：

```text
浏览器
  ↓
nginx / 前端静态站点
  ↓
后端 API (FastAPI)
  ↓
PostgreSQL + Qdrant + Redis + Kafka
```

## 2. 后端部署步骤

### 2.1 环境准备

后端所需环境：

- Python 3.12+
- Docker Desktop
- Git
- DeepSeek API Key
- 硅基流动 API Key

### 2.2 配置环境变量

在仓库根目录创建或编辑 `.env`：

```env
DEEPSEEK_API_KEY=sk-你的Key
SILICONFLOW_API_KEY=sk-你的Key
```

### 2.3 构建并启动全部服务

执行：

```bash
docker compose up -d --build
```

Compose 会拉起以下服务：

- PostgreSQL + pgvector
- Qdrant
- Redis
- Kafka
- Kafka UI
- OpenMemory MCP Server
- Backend FastAPI
- Frontend nginx

验证方式：

```bash
docker ps --filter "name=mem-"
```

### 2.4 数据库初始化

Backend 容器启动时自动执行：

```bash
python -m alembic upgrade head
```

然后以单 worker 启动 FastAPI，避免 L1/L2/L3 后台任务重复运行。

### 2.5 验证后端

```bash
curl http://localhost:8000/health
```

也可以访问 Swagger：

```text
http://localhost:8000/health
```

---

## 3. 前端访问与开发构建

生产部署已由 Compose 中的 `frontend` 服务完成，不需要单独安装 nginx。访问：

```text
http://localhost:8081
```

### 3.1 前端镜像构建过程

前端 Dockerfile 使用多阶段构建：

1. `node:24.20.0-alpine3.24` 安装 pnpm 依赖并执行构建；
2. `nginx:1.27-alpine` 托管最终 `dist/` 静态文件。

如需脱离 Docker 在本地开发，才执行以下步骤。

### 3.2 本地开发环境

前端所需：

- Node.js
- Corepack
- pnpm（项目声明为 `pnpm@11.7.0`）
- nginx 或其他静态资源服务

### 3.3 安装依赖

```bash
cd agent-memory-frontend
corepack enable
corepack pnpm install
```

### 3.4 配置环境变量

创建或确认 `.env.production`：

```env
VITE_API_BASE_URL=https://你的后端域名
VITE_API_TIMEOUT_MS=30000
VITE_APP_TITLE=智能体记忆系统前端
```

如果前端和后端在同一域名下并由 nginx 转发，也可以设置为同源地址或空值。

### 3.5 构建前端

```bash
corepack pnpm build
```

构建成功后会生成 `dist/` 目录，作为静态部署产物。

### 3.6 手工部署到 nginx（可选）

示例配置：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    root /var/www/agent-memory-frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 3.6 HTTPS 配置

如果要求 HTTPS，则在 nginx 中配置证书，并确保前端与后端使用一致的安全协议，避免混合内容问题。

---

## 4. 推荐部署方式

最常见的部署架构是：

```text
浏览器
  ↓
nginx
  ├── 前端页面
  ├── /api/* -> 后端 API
  └── /health -> 健康检查
  ↓
FastAPI
  ↓
PostgreSQL + Qdrant + Kafka
```

这种方式最适合生产部署，也最符合前端部署说明中的实践。

## 5. 部署后检查项

部署完成后建议依次检查：

1. 前端主页能正常打开
2. 刷新子路由不出现 404
3. 健康检查接口返回正常
4. 能执行记忆写入
5. 能执行记忆检索
6. 能看到列表和上下文返回

---

## 6. 结论

- 后端部署的核心是先启动 Docker 基础设施，再初始化数据库，然后启动 mem0 MCP Server 和 FastAPI。
- 前端部署的核心是构建静态站点并通过 nginx 代理到后端 API。
- 实际运行时，前端本身不直接依赖 Kafka / Qdrant 等中间件，它依赖的是后端 API 以及后端的后端中间件环境。

如果需要，我还可以继续把这份部署说明整理成更适合复制到项目首页的“简版部署手册”。