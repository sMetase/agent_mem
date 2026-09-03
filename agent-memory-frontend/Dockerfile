FROM harbor.goertek.com/g-eam/node:24.20.0-alpine3.24 AS builder

ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_API_TIMEOUT_MS=30000
ARG VITE_APP_TITLE=智能体记忆系统前端

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_API_TIMEOUT_MS=$VITE_API_TIMEOUT_MS \
    VITE_APP_TITLE=$VITE_APP_TITLE

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN corepack enable && corepack prepare pnpm@11.7.0 --activate
RUN pnpm config set registry http://10.10.41.127:8081/repository/npm-public
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM harbor.goertek.com/g-eam/nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
