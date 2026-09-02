# 智能体记忆系统依赖版本说明

本文档整理了该项目当前使用到的核心依赖及其版本，版本依据来自：

- memProject/docker-compose.yml
- memProject/requirements.txt

> 说明：Docker 镜像中有些组件使用的是 `latest`（如 Qdrant、Kafka UI），而 Python 侧依赖通常会固定版本号，因此实际运行环境建议以 `requirements.txt` 和容器镜像 tag 为准。

## 1. 容器/中间件依赖

| 组件 | 作用 | 版本/镜像 | 备注 |
| --- | --- | --- | --- |
| pgvector | 主数据库与向量扩展 | `pgvector/pgvector:pg16` | 端口映射 `5433:5432` |
| Qdrant | 向量检索引擎 | `qdrant/qdrant:latest` | 端口映射 `6333:6333`、`6334:6334` |
| Kafka | 消息总线 / 异步写入队列 | `bitnami/kafka:3.7` | 端口映射 `9092:9092` |
| Kafka UI | Kafka 管理界面 | `provectuslabs/kafka-ui:latest` | 端口映射 `8080:8080` |

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
- API 框架：FastAPI
- 编排/运行：Docker Compose
- Python 依赖管理：requirements.txt

## 4. 需要注意的版本差异

- Qdrant 的 Docker 镜像使用 `latest`，因此不稳定，可能随时间更新；Python 端的 `qdrant-client` 则是固定到 `1.18.0`。
- Kafka 镜像是 `bitnami/kafka:3.7`，对应的是 Kafka 3.7 系列。
- PostgreSQL 是 `pgvector/pgvector:pg16`，说明项目使用 PostgreSQL 16 及其 pgvector 扩展。

---

# 前后端部署步骤说明

本文档整理了本项目的前后端部署方式，依据的实际文件包括：

- [memProject/README.md](memProject/README.md)
- [agent-memory-frontend/智能体记忆系统前端部署说明.md](agent-memory-frontend/智能体记忆系统前端部署说明.md)
- [memProject/docker-compose.yml](memProject/docker-compose.yml)

## 1. 部署总览

该项目的部署大致分为 3 层：

1. 基础设施层：PostgreSQL + pgvector、Qdrant、Kafka
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
PostgreSQL + Qdrant + Kafka
```

## 2. 后端部署步骤

### 2.1 环境准备

后端所需环境：

- Python 3.12+
- Docker Desktop
- Git
- DeepSeek API Key
- 硅基流动 API Key

### 2.2 拉取代码并安装依赖

```bash
git clone <仓库地址>
cd memProject
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2.3 配置环境变量

在项目根目录创建或编辑 `.env`：

```env
DEEPSEEK_API_KEY=sk-你的Key
SILICONFLOW_API_KEY=sk-你的Key
```

### 2.4 启动基础设施

执行：

```bash
docker compose up -d
```

这一步会拉起：

- PostgreSQL + pgvector
- Qdrant
- Kafka
- Kafka UI

验证方式：

```bash
docker ps --filter "name=mem-"
```

### 2.5 初始化数据库

```bash
python -m alembic revision --autogenerate -m "init_schema"
python -m alembic upgrade head
```

### 2.6 启动 OpenMemory MCP Server

需要单独拉起 mem0 仓库并启动其 API：

```bash
cd ..
git clone https://github.com/mem0ai/mem0.git mem0_repo
cd mem0_repo/openmemory/api
pip install -r requirements.txt
```

随后按文档修补兼容性问题，再启动：

```bash
uvicorn main:app --host 0.0.0.0 --port 8765
```

成功后应能看到类似：

```text
Uvicorn running on http://0.0.0.0:8765
```

### 2.7 启动 FastAPI 服务

回到项目目录：

```bash
cd memProject
uvicorn app.main:app --reload --port 8000
```

### 2.8 验证后端

```bash
curl http://localhost:8000/health
```

也可以访问 Swagger：

```text
http://localhost:8000/docs
```

---

## 3. 前端部署步骤

### 3.1 准备环境

前端所需：

- Node.js
- Corepack
- pnpm（项目声明为 `pnpm@11.7.0`）
- nginx 或其他静态资源服务

### 3.2 安装依赖

```bash
cd agent-memory-frontend
corepack enable
corepack pnpm install
```

### 3.3 配置环境变量

创建或确认 `.env.production`：

```env
VITE_API_BASE_URL=https://你的后端域名
VITE_API_TIMEOUT_MS=30000
VITE_APP_TITLE=智能体记忆系统前端
```

如果前端和后端在同一域名下并由 nginx 转发，也可以设置为同源地址或空值。

### 3.4 构建前端

```bash
corepack pnpm build
```

构建成功后会生成 `dist/` 目录，作为静态部署产物。

### 3.5 部署到 nginx

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