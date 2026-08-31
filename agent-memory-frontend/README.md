# agent-memory-frontend

面向多智能体业务的记忆管理控制台，基于 `React + Vite + TypeScript + Ant Design + Axios + Zustand`。

当前产品不提供实时 AI 对话。系统负责导入历史对话、会话摘要和任务过程，完成记忆写入、查询、检索、上下文返回及任务管理，并以控制台形式展示运行概览。

## 安装与启动

项目要求 Node.js，并通过 Corepack 使用仓库指定的 pnpm 版本：

```bash
corepack enable
corepack pnpm install
corepack pnpm dev
```

启动后访问 `http://localhost:5173`。如果系统已经能直接识别 `pnpm`，也可以省略 `corepack`。

常用命令：

```bash
corepack pnpm lint
corepack pnpm test
corepack pnpm build
corepack pnpm check
```

`check` 会依次执行代码规范检查、测试和生产构建，建议提交 PR 前运行。

## 环境配置

开发环境配置位于 `.env.development`：

- `VITE_API_BASE_URL`：后端服务地址。
- `VITE_API_TIMEOUT_MS`：请求超时时间，当前为 `30000` 毫秒。
- `VITE_APP_TITLE`：页面标题。

也可以在系统设置页覆盖 Base URL、用户、场景、Agent ID 和 API Key。配置保存在浏览器本地。

## 页面与功能

| 页面 | 路径 | 当前能力 |
| --- | --- | --- |
| 系统总览 | `/` | 关键指标、功能流程、记忆分布和运行概览 |
| 数据写入 | `/ingestion` | JSON/CSV 导入历史对话、会话摘要和任务过程 |
| 记忆管理 | `/memory` | 记忆列表、筛选、编辑和删除 |
| 多信号检索 | `/retrieval` | 类型、状态、数量和重排条件检索 |
| 生成与去重 | `/generation` | 单条/批量文本生成、抽取类型选择、去重融合统计和处理明细 |
| 上下文返回 | `/context` | 请求并预览供智能体使用的结构化上下文 |
| 任务管理 | `/task` | 任务创建、进度查询和状态更新 |
| 接口监控 | `/monitoring` | 健康检查、联调状态和异常提示 |
| 系统设置 | `/settings` | 联调地址及身份配置 |

总览和部分监控指标目前使用演示数据；写入、列表、检索、上下文、单条/批量生成、任务和健康检查通过 `src/api` 对接后端。

## 后端接口覆盖

当前前端已接入以下真实记忆接口：

- `POST /api/v1/memory/write`：写入对话记录、历史会话摘要和任务过程。
- `POST /api/v1/memory/search`：语义检索、类型与状态过滤、Top-K 和重排。
- `POST /api/v1/memory/list`：按用户、场景和任务分页查询记忆。
- `PUT /api/v1/memory/update`：修改内容、摘要、状态、重要性、置信度和标签。
- `DELETE /api/v1/memory/delete` 与 `POST /api/v1/memory/delete-all`：单条软删除和用户记忆清空。
- `POST /api/v1/memory/context`：按类型、状态、任务和长度预算生成上下文。
- `POST /api/v1/memory/generate` 与 `/generate/batch`：单条或最多 50 条文本的结构化记忆生成。

`/memory/async_write` 和 `/memory/generate/async` 仍是后端占位能力，当前前端不启用。冲突列表、人工融合决策、过滤规则和运行日志仍需要后端提供独立管理接口。

## 目录结构

```text
src/
  api/                  请求客户端、接口模块和数据类型
  components/
    business/           可复用业务组件
    common/             页面容器、状态、错误和确认组件
  constants/            路由与业务常量
  hooks/                API 与状态的轻量封装
  layouts/              控制台壳层和侧边导航
  pages/                各业务页面
  router/               路由、菜单元信息和异常路由
  store/                Zustand 全局状态
  utils/                配置、导入解析、提示和格式化工具
```

## 分支规则

- `main`：稳定、可演示版本，只接收经过验证的里程碑。
- `dev`：日常集成分支，所有功能先合入这里统一验证。
- `feature/*` 或 `codex/*`：从最新 `dev` 创建的功能分支，不直接在 `main` 开发。

推荐流程：

1. 同步最新 `dev`。
2. 创建独立功能分支。
3. 完成开发并运行 `corepack pnpm check`。
4. 提交 Pull Request，目标分支选择 `dev`。
5. 检查改动范围、接口兼容和验证结果后合并。
6. 阶段版本稳定后，再由 `dev` 提交 PR 到 `main`。

## 开发与维护方式

当前前端由项目负责人统一开发和维护，不再按 A/B/C 划分页面或目录。功能实现、公共层调整、接口适配和集成验证均以完整产品为单位推进。

- 页面功能统一放在 `src/pages`，公共能力优先沉淀到 `src/components/common`、`src/api`、`src/store` 和 `src/utils`。
- 新功能从最新 `dev` 创建独立分支，完成后通过 Pull Request 合入 `dev`，不要直接在 `main` 上开发。
- 修改接口字段时，先更新 `src/api/types.ts` 和对应接口模块，再调整页面展示和交互。
- 后端尚未提供的能力可以保留说明、流程或演示状态，但必须明确标注，避免与真实接口数据混淆。
- 产品不包含实时 AI 聊天，重点是记忆写入、管理、检索、生成去重、上下文返回及运行管理。

更详细的开发约定见 [开发流程文档](./docs/collaboration.md)。

## Pull Request 建议

- 一个 PR 只处理一个清晰主题，避免混入无关改动。
- 标题可使用中文，例如：`feat：完善记忆控制台与浏览器导入流程`。
- 描述写清改动内容、影响目录、后端依赖和验证结果。
- PR 目标通常是 `dev`，不要直接选择 `main`。
- 合并前至少确认无冲突，且 lint、test、build 全部通过。
