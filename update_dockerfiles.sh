#!/bin/bash

# 脚本：去掉 Dockerfile 中的注释 pip/npm 源配置
# 用法: bash update_dockerfiles.sh

echo "开始更新 Dockerfile..."

# 1. agent-memory-frontend/Dockerfile - 去掉 npm registry 注释
echo "更新 agent-memory-frontend/Dockerfile..."
sed -i 's/^# RUN pnpm config set registry/RUN pnpm config set registry/' agent-memory-frontend/Dockerfile

# 2. memProject/Dockerfile - 去掉 pip registry 注释
echo "更新 memProject/Dockerfile..."
sed -i 's/^# RUN pip config set global\.index-url/RUN pip config set global.index-url/' memProject/Dockerfile

# 3. mem0_repo/openmemory/api/Dockerfile - 去掉 pip registry 注释
echo "更新 mem0_repo/openmemory/api/Dockerfile..."
sed -i 's/^# RUN pip config set global\.index-url/RUN pip config set global.index-url/' mem0_repo/openmemory/api/Dockerfile

echo "完成！所有 Dockerfile ��更新。"
echo ""
echo "变更摘要："
echo "1. agent-memory-frontend/Dockerfile: 启用 pnpm npm 源配置"
echo "2. memProject/Dockerfile: 启用 pip 源配置"
echo "3. mem0_repo/openmemory/api/Dockerfile: 启用 pip 源配置"
