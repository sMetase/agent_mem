# 部署说明

本文档说明智能体记忆系统的 Docker Compose 部署、本地开发和手工前端部署方式。

## 1. 部署架构

系统由三层组成：

1. 基础设施层：PostgreSQL + pgvector、Qdrant、Redis、Kafka
2. 后端服务层：FastAPI Backend，内置对外 memProject MCP Server，以及内部 OpenMemory MCP 依赖
3. 前端静态层：React/Vite 构建产物和 nginx

```text
浏览器
  ↓
Frontend nginx
  ↓
Backend FastAPI + memProject MCP
  ↓
PostgreSQL + Qdrant + Redis + Kafka
```

## 2. 前置条件

- Docker Engine 或 Docker Desktop
- Docker Compose v2
- Git
- DeepSeek API Key
- SiliconFlow API Key

Python 3.12+ 和 Node.js 仅在不使用 Docker、进行本地开发时需要。

## 3. 配置环境变量

在仓库根目录创建或编辑 `.env`。可以从示例文件开始：

```bash
cp .env.example .env
```

至少配置模型服务密钥：

```env
DEEPSEEK_API_KEY=你的DeepSeek_Key
SILICONFLOW_API_KEY=你的SiliconFlow_Key
```

常用服务配置：

```env
DB_HOST=postgres
DB_PORT=5432
QDRANT_HOST=qdrant
QDRANT_PORT=6333
REDIS_URL=redis://redis:6379/0
KAFKA_BOOTSTRAP_SERVERS=kafka:9093
BACKEND_PORT=8000
FRONTEND_PORT=8081
KAFKA_UI_PORT=8080
```

容器之间使用 Compose 服务名通信，例如 `postgres`、`qdrant`、`redis` 和 `kafka`；不要在容器内使用 `localhost` 访问这些服务。

## 4. Docker Compose 部署

### 4.1 启动全部服务

```bash
docker compose up -d --build
```

Compose 会启动：

- PostgreSQL + pgvector
- Qdrant
- Redis
- Kafka
- Kafka UI
- OpenMemory MCP（Backend 内部）
- Backend FastAPI 和对外 memProject MCP
- Frontend nginx

### 4.2 查看状态和日志

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
```

Backend 启动时会先执行数据库迁移：

```bash
python -m alembic upgrade head
```

然后以单个 Uvicorn worker 启动 FastAPI，避免 L1/L2/L3 后台任务重复运行。

### 4.3 验证服务

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/health
```

默认访问地址：

| 服务 | 默认地址 |
| --- | --- |
| 前端 | `http://localhost:8081` |
| Backend API | `http://localhost:8000` |
| Swagger | `http://localhost:8000/docs` |
| memProject MCP | `http://localhost:8000/mcp/` |
| Backend 健康检查 | `http://localhost:8000/health` |
| Kafka UI | `http://localhost:8080` |
| Qdrant | `http://localhost:6333` |
| PostgreSQL | `localhost:5433` |

如果 `.env` 修改了 `BACKEND_PORT` 或 `FRONTEND_PORT`，访问地址也要使用对应端口。

### 4.4 停止服务

```bash
docker compose down
```

仅当需要删除数据库、向量库和 Kafka 数据时才使用：

```bash
docker compose down -v
```

该命令会删除 Compose 管理的持久化卷，请谨慎使用。

## 5. 端口冲突排查

每个宿主机端口只能被一个容器占用。常见冲突是 Backend 和 Kafka UI 同时绑定 `8080`。

检查端口占用：

```bash
sudo ss -ltnp | grep ':8000\|:8080\|:8081'
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

推荐端口配置：

```env
BACKEND_PORT=8000
KAFKA_UI_PORT=8080
FRONTEND_PORT=8081
```

修改 `.env` 后重新创建容器：

```bash
docker compose down --remove-orphans
docker compose up -d --build
```

如果必须让 Backend 使用 `8080`，则将 Kafka UI 改为其他宿主机端口，例如：

```env
BACKEND_PORT=8080
KAFKA_UI_PORT=8082
```

容器内部端口不需要修改，修改的是宿主机映射端口。

## 6. 本地后端开发

不使用 Backend Docker 镜像时，需要 Python 3.12+：

```bash
cd memProject
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Windows 激活虚拟环境：

```powershell
.venv\Scripts\activate
```

本地运行 Backend 时，`.env` 中的数据库地址应根据运行位置配置：

- Backend 在宿主机运行：`DB_HOST=localhost`，PostgreSQL 使用映射端口 `5433`
- Backend 在 Compose 容器运行：`DB_HOST=postgres`，数据库使用容器端口 `5432`

## 7. 前端本地开发和构建

前端需要 Node.js、Corepack 和 pnpm 11.7.0：

```bash
cd agent-memory-frontend
corepack enable
corepack pnpm install
corepack pnpm dev
```

默认开发地址为 `http://localhost:5173`。

常用前端环境变量：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_API_TIMEOUT_MS=30000
VITE_APP_TITLE=智能体记忆系统前端
```

构建生产静态文件：

```bash
corepack pnpm build
```

Docker 部署使用多阶段构建：

1. `node:24.20.0-alpine3.24` 安装依赖并构建 Vite 项目
2. `nginx:1.27-alpine` 托管生成的 `dist/`

## 8. 手工 nginx 部署

如果不使用 Compose 的 frontend 服务，可以将 `dist/` 部署到 nginx：

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

启用 HTTPS 时，应同时配置证书，并确保前端 API 地址使用 HTTPS，避免混合内容错误。

## 9. 服务和镜像清单

| 服务 | 镜像或构建基础 | 作用 |
| --- | --- | --- |
| PostgreSQL | `pgvector/pgvector:pg16` | 主数据库和 pgvector |
| Qdrant | `qdrant/qdrant:latest` | 向量检索 |
| Redis | `redis:7-alpine` | 缓存和结果轮询 |
| Kafka | `apache/kafka:3.7.2` | 异步消息队列 |
| Kafka UI | `provectuslabs/kafka-ui:latest` | Kafka 管理界面 |
| Backend | `python:3.12-slim` | FastAPI、MCP、L1/L2/L3 Worker |
| OpenMemory | `python:3.12-slim` | Backend 内部记忆存储 MCP |
| Frontend | `node:24.20.0-alpine3.24` + `nginx:1.27-alpine` | 构建并托管前端 |

Qdrant 和 Kafka UI 使用 `latest`，镜像内容可能随时间变化；Python 依赖版本见 `memProject/requirements.txt`。

## 10. 主要 Python 依赖

| 组件 | 版本 | 作用 |
| --- | --- | --- |
| FastAPI | `0.138.2` | Web API 框架 |
| SQLAlchemy | `2.0.51` | ORM 和数据访问层 |
| asyncpg | `0.31.0` | PostgreSQL 异步驱动 |
| psycopg2-binary | `2.9.12` | PostgreSQL 同步驱动 |
| aiokafka | `0.14.0` | Kafka 异步客户端 |
| qdrant-client | `1.18.0` | Qdrant 客户端 |
| redis | `5.0.1` | Redis 客户端 |
| openai | `2.44.0` | OpenAI 兼容模型接口 |
| mem0ai | `2.0.10` | Mem0 记忆框架 |
| pydantic | `2.13.4` | 数据校验和配置模型 |
| uvicorn | `0.49.0` | ASGI 服务启动器 |
