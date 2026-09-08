#!/bin/bash

# 脚本：更新 Dockerfile 中的 pip/npm 源配置
# 用法: bash update_dockerfiles.sh

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "开始更新 Dockerfile..."
echo ""

# 1. agent-memory-frontend/Dockerfile
echo "更新 1/3: agent-memory-frontend/Dockerfile"
cat > "$REPO_ROOT/agent-memory-frontend/Dockerfile" << 'EOF'
FROM node:24.20.0-alpine3.24 AS builder

ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_API_TIMEOUT_MS=30000
ARG VITE_APP_TITLE=智能体记忆系统前端

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_API_TIMEOUT_MS=$VITE_API_TIMEOUT_MS \
    VITE_APP_TITLE=$VITE_APP_TITLE

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
ARG NPM_REGISTRY=http://10.10.41.127:8081/repository/npm-public
RUN npm install --global pnpm@11.7.0 --registry="$NPM_REGISTRY" && \
    pnpm config set registry "$NPM_REGISTRY"
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
EOF
echo "✓ 完成"

# 2. memProject/Dockerfile
echo "更新 2/3: memProject/Dockerfile"
cat > "$REPO_ROOT/memProject/Dockerfile" << 'EOF'
FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .

RUN pip config set global.index-url http://10.10.41.127:8081/repository/pypi-group/simple && pip config set global.trusted-host 10.10.41.127
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 非 root 运行
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000 9090

CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
EOF
echo "✓ 完成"

# 3. mem0_repo/openmemory/api/Dockerfile
echo "更新 3/3: mem0_repo/openmemory/api/Dockerfile"
cat > "$REPO_ROOT/mem0_repo/openmemory/api/Dockerfile" << 'EOF'
FROM python:3.12-slim

LABEL org.opencontainers.image.name="mem0/openmemory-mcp"

WORKDIR /usr/src/openmemory

COPY requirements.txt .
RUN pip config set global.index-url http://10.10.41.127:8081/repository/pypi-group/simple && pip config set global.trusted-host 10.10.41.127
RUN pip install -r requirements.txt

COPY config.json .
COPY . .

EXPOSE 8765
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765"]
EOF
echo "✓ 完成"


find . -type f -name 'Dockerfile' -exec sed -i.bak -E 's|^([[:space:]]*FROM[[:space:]]+)([^[:space:]/]+/)?([^[:space:]]+)|\1harbor.goertek.com/g-eam/\3|' {} +


echo ""
echo "=========================================="
echo "✓ 所有 Dockerfile 已成功更新！"
echo "=========================================="
echo ""
echo "变更摘要："
echo "1. agent-memory-frontend/Dockerfile"
echo "   - 添加 NPM_REGISTRY 参数"
echo "   - 更新 pnpm 安装命令使用自定义 registry"
echo ""
echo "2. memProject/Dockerfile"
echo "   - 取消注释 pip 源配置"
echo ""
echo "3. mem0_repo/openmemory/api/Dockerfile"
echo "   - 取消注释 pip 源配置"
