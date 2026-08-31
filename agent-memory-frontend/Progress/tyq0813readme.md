# 智能体记忆系统前端 —— 项目统揽（tyq0813）

> 记录日期：2026-08-13
> 说明：本文档统揽整个项目，回答「项目做了什么、简介、目前是什么样子、还差什么」。面向不熟悉项目的人（新同事、老师、接手者）快速建立整体认知。详细方案与完成记录见文末「文档索引」。

---

## 一、项目简介

**项目名称**：agent-memory-frontend —— 智能体记忆系统前端控制台

**一句话定位**：面向大模型多智能体业务的**记忆管理中台**，覆盖记忆从"写入 → 管理 → 生成融合 → 检索 → 上下文返回"的全生命周期，并以控制台形式展示运行概览。

**重要边界**：本产品**不提供实时 AI 对话**。系统负责导入历史对话、会话摘要和任务过程，完成记忆写入、查询、检索、上下文返回及任务管理。

**技术栈**：

| 类别 | 选型 |
| --- | --- |
| 框架 | React 19.2 + Vite 8 + TypeScript 6 |
| UI | Ant Design 6.4 + @ant-design/icons |
| 状态 | Zustand 5 |
| 路由 | React Router 7 |
| 请求 | Axios |
| 图表 | @ant-design/plots 2.6.8（G2 v5） |
| 测试 | Vitest + oxlint |
| 包管理 | pnpm 11.7.0（通过 `corepack pnpm` 调用） |

**数据流闭环**：数据源（用户问题 / 任务 / 绘画）→ 系统存储 → 索引构建 → 记忆写入/生成 → 检索 → 返回给智能体使用。

**开发模式**：由前端负责人统一开发维护，不再按 A/B/C 划分页面；改动通过 PR 合入（规则见 README.md，但当前实际 git 历史尚未按该规则执行，见「八、git 现状」）。

---

## 二、项目背景与交付节奏

| 节点 | 事件 |
| --- | --- |
| 2026-08-10 | 6 人开发进度对齐会，提出五项前端改造意见（已落地，见 [0810.md](./0810.md)） |
| 2026-08-13 | 徐庸辉老师会议，提出六项改造 + 界面差异化要求（已落地，见 [0813.md](./0813.md)） |
| 8 月中旬 | 核心功能基本完成（当前已达成） |
| 8/20-21 前后 | 进入部署与测试 |
| 8/28 前 | 测试服务器全量部署 |
| 8/31 | 正式投入使用 |

---

## 三、已完成内容总览

### 3.1 界面：侧边栏 7 大分区 + 登录体系

侧边栏菜单（[route-config.tsx](../src/router/route-config.tsx)）共 7 个分区、约 20+ 个页面：

| # | 分区 | 页面 | 完成情况 |
| --- | --- | --- | --- |
| 1 | 智能体接入与记忆数据写入 | 智能体注册接入、场景标识配置、接口密钥配置、记忆数据导入、数据校验与标准化 | ✅ |
| 2 | 多层记忆管理 | 用户级 / 会话级 / 任务级 / 智能体级记忆 | ✅ |
| 3 | 记忆生成与去重融合 | 10 个预设（3 分析 + 7 文本，结果区差异化） | ✅ |
| 4 | 多信号融合记忆检索 | 语义 / 关键词 / 元数据 / 融合 / Top-K（5 模式差异化） | ✅ |
| 5 | 记忆上下文返回 | JSON / 文本 / 相关性 / 长度（4 模式差异化） | ✅ |
| 6 | 接口与监控 | 健康检查、调用状态监控、联调记录 | ✅ |
| 7 | 系统设置 | 基础连接设置、本地用户身份 | ✅ |

其他页面：**系统总览**（首页，实时监控看板）、**任务过程管理**、**登录 / 注册 / 密码找回 / 个人中心**（登录守卫 + mock 认证）、**视觉现代化原型**（不进入菜单，2026 设计趋势预览）。

### 3.2 两次会议意见落地

**0810 会议（已完成）**：菜单精简（删"通用记忆建模"）、首页实时监控看板（频次+成功率，按小时/天/周切换）、记忆页重构为"选择区 + 结果展示区"、注册与接入拆分为两个独立操作、导入强制关联 Agent ID、前端↔后端联通修复（本地后端 8000 端口 + 13 张表建表 + tzdata 修复）。

**0813 会议（已完成，详见 [0813.md](./0813.md)）**：
1. **多层记忆管理页彻底整改**：移除分析面板与手动 ID 输入；列表勾选常开；新增层级统计卡（`LevelStatCards`）、搜索 + 高级查询（`MemorySearchBar`）；统一"查看/修改/删除/更新"四操作列；三级字段适配。
2. **分析功能迁移到生成页**：新增可复用 `MemorySelector`（方案 B：选记忆→执行分析→展示结果，同页完成）；新增 `analysis.ts` 三分析引擎（用户偏好 / 关键事实 / 关键实体人物），动态字段 + 演示数据兜底；偏好=画像标签+雷达图、事实=条目列表+关联树、实体=实体卡片。
3. **智能体接入增强**：平台来源选择（Dify / Open WebUI / 阿里云 IMS / 智谱，字段动态切换）+ 采集频次配置（手动/定时）。
4. **首页看板追溯增强**：后端健康状态、请求路径统计、失败调用追溯（Trace ID）。
5. **检索结果完善**：空结果演示数据兜底 + 失败引导 + 相关度进度条。
6. **登录页**（最后做）：复用 `Graph-KnowledgeGraphPlatform` 结构，适配 React 19 + antd 6；mock 认证（admin/admin123、operator/operator123）+ 登录守卫 + GitHub OAuth2 占位 + 个人中心 + 三步密码找回。

**0813 界面差异化（已完成）**：生成模块 7 个文本预设、检索 6 模式、上下文 5 模式——结果展示区各自独立形态，不再共用同一套模板（时间线 / 决策卡 / 左右对比 / 分组卡 / 对照流 / 丢弃清单 / 命中高亮 / 信号权重条 / Token 预算等）。

### 3.3 后端接口接入情况

已接通真实接口：`/memory/write`、`/memory/search`、`/memory/list`、`/memory/update`、`/memory/delete`、`/memory/delete-all`、`/memory/context`、`/memory/generate`、`/memory/generate/batch`。

后端仍为占位、前端未启用：`/memory/async_write`、`/memory/generate/async`。

分析类、认证类、采集任务类接口后端尚未提供，前端用**演示数据 / mock / localStorage** 兜底并明确标注。

---

## 四、当前运行状态与验证结果

### 4.1 本地服务

| 服务 | 地址 | 状态 |
| --- | --- | --- |
| 前端 dev server | http://localhost:5173 | ✅（登录后进入控制台） |
| 后端（memProject uvicorn） | http://localhost:8000 | ✅ |
| PostgreSQL | localhost:5432 | ✅ |
| Qdrant | localhost:6333 | ✅ |

### 4.2 代码验证（0813 实跑）

| 检查项 | 结果 |
| --- | --- |
| `corepack pnpm lint` | ✅ 0 错误 0 警告 |
| `corepack pnpm test` | ✅ 45/45 通过（11 个测试文件） |
| `corepack pnpm build` | ✅ 构建成功（仅 1 个已知 chunk 体积警告） |

### 4.3 演示数据

数据库已由 [seed-demo-data.py](../scripts/seed-demo-data.py) 灌入演示数据：49 条四级记忆（主演示用户 `user_001`）、6 会话、5 任务、3 智能体、2 场景、2 用户、11 条检索日志、3 条记忆关联；`t_api_log` 约 2440 条（首页看板曲线）。

> **最重要的一个事实**：前端所有接口调用都是真实的（走后端），但数据库里的记忆数据是演示数据。这不是 bug，是当前阶段的预期状态。

---

## 五、还差什么（遗留事项）

### 5.1 后端能力未就绪（非前端问题，但影响完整演示）

| # | 事项 | 影响 | 归属 |
| --- | --- | --- | --- |
| 1 | `DEEPSEEK_API_KEY` / `SILICONFLOW_API_KEY` 为空 | 记忆写入/偏好抽取/向量检索走降级模式（`degraded` / `SKIP`） | 后端填 Key |
| 2 | pgvector 扩展缺失 | 向量列相关能力受限（非致命） | 后端装扩展 |
| 3 | Kafka / Redis 未运行 | 消息队列、异步回调降级（非致命） | 后端启动 |
| 4 | 无分析类专项接口 | 偏好/事实/实体生成为前端演示引擎 | 后端提供后切换 |
| 5 | `AUTH_ENABLED=false` | 登录/注册/找回/GitHub OAuth2 为前端 mock/占位 | 后端认证就绪后替换 |
| 6 | 无采集任务接口 | 智能体采集配置仅存 localStorage | 后端提供后对接 |
| 7 | `embedding_client.py` 缺 `import json`（已定位 bug） | embedding 调用必抛 `NameError`，检索走降级、上下文接口直接失败 | 后端修复 |
| 8 | `/memory/context` 无降级兜底 | 上下文模块 5 个差异化组件拿不到数据（页面/表单完好） | 后端加 DB-only 兜底或填 Key |
| 9 | 检索降级只扫最近 `top_k×2` 条 | 关键词搜不到较老记忆；测试时把「返回数量」调到 50 | 已知限制 |

### 5.2 前端遗留（低优先级）

1. **图表体积**：`@ant-design/plots` G2 运行时约 1.4MB（gzip 427KB），独立懒加载 chunk，可接受；如优化需按需引入原子图表。
2. **会话级/任务级列表字段**：「关联记忆条数」「会话主题摘要」等字段 `memory/list` 单条返回可能不足，前端先用 `memories.filter()` 聚合兜底，标注"待后端字段补充"。

### 5.3 后续计划

1. 本地修复后端 `import json`（可选，仅联调）；如需演示上下文模块，后端给 context 加 DB-only 兜底或填 Key。
2. 后端分析 / 认证 / 采集接口就绪后，替换前端演示数据兜底与 mock。
3. 测试服务器（8/19 前后）到位后，`.env` 后端地址从 `http://localhost:8000` 切到测试服务器地址。
4. 8/28 全量部署前：逐页验收 + 前后端联调确认所有展示字段。
5. 按 [前端测试指南-0813.md](./前端测试指南-0813.md) 向老师汇报演示。

---

## 六、如何运行

```bash
# 安装依赖（node 在 C:\Program Files\nodejs，可能不在 Git Bash PATH）
export PATH="/c/Program Files/nodejs:$PATH"

# 开发
corepack pnpm dev          # → http://localhost:5173

# 验证（注意：不要跑 `corepack pnpm check`，其内部调用的 pnpm 不在 PATH，会失败；分步跑）
corepack pnpm lint
corepack pnpm test
corepack pnpm build
```

登录账号：`admin / admin123`（或 `operator / operator123`）。

**已知环境坑**：
- 浏览器 localStorage 会覆盖 `.env` 的后端地址（`src/api/client.ts` 优先读 localStorage）。改了 `.env` 后需到「系统设置→基础连接设置」改地址，或 `localStorage.removeItem('agent-memory-app-config')` 后刷新。
- Windows + Git Bash 里 `??` 和 `||` 不能混用（写 `(a ?? b) || c`）。
- Python 造数脚本需用后端 venv 的 Python 运行（需 asyncpg/sqlalchemy）。

---

## 七、目录结构速览

```text
src/
  api/                  接口层（client.ts 拦截器读 localStorage baseUrl；modules/ 分业务）
  components/
    business/           业务组件（MemorySelector 可复用选择器等）
    common/             通用组件（PageContainer / FeedbackState / EmptyState 等）
  constants/            路由 / generation 预设 / platform 平台字段 / storage key
  hooks/                useAgentInit / useMemorySearch / useTaskProgress
  layouts/              AppLayout（顶栏接登录态）+ SidebarMenu
  pages/                业务页面（Overview / Memory / Generation / Retrieval / Context /
                        AgentAccess / Ingestion / Login / Task / Monitoring / Settings …）
    Generation/         index + PresetBrief（预设场景卡）+ demo-results（演示兜底）
                        + AnalysisWorkbench（选记忆→分析）+ analysis（分析引擎）+ DifferentiatedResult（差异化）
  router/               routes / route-config（菜单）/ RequireAuth（登录守卫）
  store/                appStore / authStore / memoryStore / taskStore
  utils/                配置 / 导入解析 / 格式化 / storage 等
scripts/
  seed-demo-data.py     演示数据造数脚本（幂等）
tests/                  11 个测试文件（45 用例）
Progress/               进度记录（本文档 + 0810 / 0813 / HANDOVER / 前端测试指南）
```

---

## 八、git 现状（值得注意）

- **当前分支**：`main`，仅 1 个 commit（`55eb9bb feat: 智能体记忆系统前端控制台`）。
- **远端**：`origin` → Gitee（zhanping66/agent-memory-frontend）。
- **与 README 分支规则的差距**：README 约定 `main`（稳定）/ `dev`（集成）/ `feature/*`（功能分支）三层分支，但**本地实际只有 main**，尚未按此规则建分支开发。后续如需多人协作或里程碑管理，建议先建立 `dev` 分支并让功能从 `dev` 派生。

---

## 九、文档索引

| 文档 | 内容 |
| --- | --- |
| [Progress/0810.md](./0810.md) | 0810 会议意见、五项改造方案、前后端联通修复记录 |
| [Progress/0813.md](./0813.md) | 0813 会议六项改造 + 界面差异化方案与完成记录 |
| [Progress/HANDOVER-0813.md](./HANDOVER-0813.md) | 给新会话的交接文档：背景/现状/卡点/下一步/踩坑 |
| [Progress/前端测试指南-0813.md](./前端测试指南-0813.md) | 逐页「输入什么→期望看到什么」测试指南 |
| [Progress/tyq0813readme.md](./tyq0813readme.md) | 本文档（项目统揽） |
| [README.md](../README.md) | 项目根 README：安装启动、分支规则、开发约定 |
| [API接口文档.md](../API接口文档.md) | 后端全部接口契约 |
| [智能体接入接口.pdf](../智能体接入接口.pdf) | 各平台接入字段（梁闯提供） |
| [docs/](../docs/) | 协作方案、部署说明、问题文档、预研文档等 |
| [智能体记忆系统前端部署说明.md](../智能体记忆系统前端部署说明.md) | 部署相关 |
| [智能体记忆系统前端使用说明.md](../智能体记忆系统前端使用说明.md) | 使用说明 |

---

*本文档由前端负责人维护，为项目统揽快照（0813）。代码状态以当日 lint / test / build 实测为准，遗留事项见第五节，交接细节见 HANDOVER-0813.md。*
