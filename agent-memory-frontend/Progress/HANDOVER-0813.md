# 智能体记忆系统前端 —— 会话交接文档（HANDOVER）

> 记录日期：2026-08-13（0820 已追加前后端联动改造记录）
> 本文档写给**完全没有上下文的新会话**：说明我们在做什么、已完成什么、当前状态、卡在哪、下一步、以及踩过的坑。接手前请先通读本文档 + `Progress/0820.md`（0820 前后端联动改造）+ `Progress/前端测试指南-0813.md` + `Progress/0813.md` + `Progress/0810.md`。

---

## 〇、一分钟速览

- **项目**：面向多智能体的记忆系统前端控制台（React 19 + Vite 8 + TS + Ant Design 6 + Zustand + React Router 7）。
- **我们负责**：**只改前端**（`D:\PythonProject\agent-memory-frontend-dev`），后端在 `D:\PythonProject\agent_mem-master\memProject`（FastAPI，他人维护，我们仅用于联调）。
- **核心任务**：落实徐庸辉老师 0810/0813 两次会议意见——前端六项改造 + 三个模块界面差异化，**全部已完成**，lint/test/build 通过。
- **0813 晚补充（本会话）**：① 造了一套完整演示数据（49 条四级记忆 + 会话/任务/智能体/检索日志）并写了《前端测试指南》；② 修复检索关键词高亮 bug；③ 生成页删除冗余五阶段卡、改为每预设专属场景卡 + 单行轻量进度条；④ 6 个文本预设加演示数据兜底，**无需后端 Key 即可向老师演示全部差异化组件**。
- **0820 前后端联动改造（已全部完成）**：对齐后端新契约（write 异步、hybrid 检索、generate 废弃、真实登录、5 类记忆类型），共 15 项任务。**生成模块整体删除**、检索收敛为单页、登录对接真实 `/auth/login`、新增记忆画像页。详见 `Progress/0820.md`。
- **当前状态**：项目已收敛到**远程后端 `http://120.27.207.238:8000`**（后端团队测试环境，全部接口可用）；前端 dev server http://localhost:5173 运行中；**本地后端已停且代码旧（无 `/auth/login`），不再使用**。
- **最重要的一个事实**：**登录已改为真实认证**（`/auth/login`，登录即注册），登录后 `userId` 由后端派生（admin → `user_796ac3c9cf51`），不再手动配置；远程库暂无记忆数据（记忆页空态是正常的），等后端批量导入。

---

## 一、我们在做什么（任务背景）

### 1.1 产品定位

面向大模型智能体的记忆管理中台，**不提供实时 AI 聊天**。围绕记忆全生命周期：智能体接入 → 记忆写入 → 多层记忆管理 → 记忆生成与去重融合 → 多信号融合检索 → 上下文返回 → 运行监控。

### 1.2 老师两次会议的核心要求

**0810 会议**（已落地，见 `Progress/0810.md`）：
1. 菜单精简：删「通用记忆建模」，统一为「多层记忆管理」。
2. 首页实时监控看板：接口调用频次 + 成功率曲线，按小时/天/周切换。
3. 记忆页重构：单一输入框 → 「选择区 + 结果展示区」。
4. 注册与接入拆分为两个独立操作。
5. 导入强制关联 Agent ID。

**0813 会议**（已落地，见 `Progress/0813.md`）：
1. **多层记忆管理页彻底整改**：移除分析功能、列表联动勾选、搜索+高级查询、层级统计、标准列表（查看/修改/删除/更新）、三层级字段适配。
2. **分析功能迁移到「3. 记忆生成与去重融合」**：选记忆→执行分析→展示结果，新增关键实体人物生成。
3. **智能体接入增强**：平台来源选择（Dify/OpenWebUI/阿里云IMS/智谱）+ 采集频次配置。
4. **首页看板追溯增强**：健康状态、请求路径、失败调用追溯。
5. **检索结果展示完善**：结构化结果列表 + 演示数据兜底。
6. **登录页**（今天最后做）：复用知识图谱项目、登录守卫、mock 认证、个人中心、密码找回。

**0813 追加**（界面差异化，全部完成）：
- 生成模块 7 个文本预设、检索模块 6 模式、上下文模块 5 模式——**结果展示区各自差异化**，不再共用同一套模板。

---

## 二、已完成的内容（代码层面）

### 2.1 项目技术栈

- React 19.2 + Vite 8 + TypeScript 6 + Ant Design 6.4 + Zustand 5 + React Router 7 + Axios。
- 图表库：`@ant-design/plots@2.6.8`（基于 G2 v5，从 `@ant-design/charts` 调整而来，去掉了未使用的 graphs）。
- 包管理：pnpm（版本 11.7.0，通过 `corepack pnpm` 调用）。

### 2.2 六项改造（0813）+ 登录（已完成）

| 模块 | 关键文件 | 说明 |
| --- | --- | --- |
| 记忆管理页整改 | `src/pages/Memory/index.tsx`、`components/LevelStatCards.tsx`、`components/MemorySearchBar.tsx`、`types.ts` | 移除分析面板/手动ID输入；列表勾选常开；层级统计卡；搜索+高级查询；标准操作列 |
| 分析功能迁移 | `src/pages/Generation/AnalysisWorkbench.tsx`、`analysis.ts`、`src/components/business/MemorySelector/index.tsx` | 选记忆（方案B 内嵌选择器）→ 分析 → 差异化结果（偏好=雷达图+标签、事实=列表+树、实体=卡片） |
| 实体人物生成 | `src/constants/generation.ts` 新增 `entity` 预设 | 菜单新增「关键实体人物生成」 |
| 智能体接入增强 | `src/pages/AgentAccess/index.tsx`、`src/constants/platform.ts` | 平台来源选择（按 PDF 字段动态切换）+ 采集频次（手动/定时/每小时/每天/自定义） |
| 首页看板追溯 | `src/pages/Overview/RealTimeMonitorCard.tsx`、`monitor-series.ts` | 后端健康状态、请求路径统计、失败调用追溯（Trace ID） |
| 检索结果完善 | `src/pages/Retrieval/index.tsx` | 空结果演示数据兜底 + 失败引导 + 相关度进度条 |
| 登录体系 | `src/pages/Login/index.tsx`、`ForgotPassword/index.tsx`、`Profile/index.tsx`、`src/router/RequireAuth.tsx`、`src/store/authStore.ts` | 登录守卫、mock 认证（admin/admin123、operator/operator123）、个人中心、密码找回、GitHub OAuth2 占位 |

### 2.3 界面差异化（0813 追加，全部完成）

| 模块 | 文件 | 差异化结果形态 |
| --- | --- | --- |
| 生成（7 预设） | `src/pages/Generation/DifferentiatedResult.tsx` | 任务状态=时间线；决策=决策卡片；冲突=左右对比；冲突去重=解决清单；相似去重=分组卡片；融合=前后对照；低价值=丢弃清单 |
| 检索（6 模式） | `src/pages/Retrieval/DifferentiatedResult.tsx` | 语义=相似度排序；关键词=命中高亮；元数据=筛选面板；融合=信号权重条；Top-K=截断条；全部=综合仪表盘 |
| 上下文（5 模式） | `src/pages/Context/DifferentiatedResult.tsx` | JSON=结构树；文本=可注入卡片；相关性=分级列表；长度=Token预算；全部=综合视图 |

### 2.4 环境联通（0810 已解决）

- 前端 `.env.development` / `.env.production` 后端地址改为 `http://localhost:8000`。
- 后端数据库 13 张表已建（初始迁移是 stub，需 `Base.metadata.create_all` 建表）。
- 后端已安装 `tzdata`（Windows 时区库），修复 dashboard 500。
- `t_api_log` 表灌了 ~2440 条演示日志，首页看板有曲线可看。

### 2.5 验证结果

- `corepack pnpm lint`：✅ 0 错误 0 警告。
- `corepack pnpm test`：✅ 45/45 通过（更新了 generation 菜单 views 9→10 的断言）。
- `corepack pnpm build`：✅ 通过。
- 前端 dev server：http://localhost:5173；后端：http://localhost:8000，均可访问。

### 2.6 0813 晚补充（演示数据 + 界面优化，已完成）

| 项 | 文件 | 说明 |
| --- | --- | --- |
| 造数脚本 | `scripts/seed-demo-data.py`（新增） | 绕过无 Key 的 LLM 管道，直插后端库：49 条四级记忆 + 6 会话 + 5 任务 + 3 智能体 + 2 场景 + 2 用户 + 11 检索日志 + 3 记忆关联；幂等可重跑 |
| 前端测试指南 | `Progress/前端测试指南-0813.md`（新增） | 逐页「输入什么 → 期望看到什么」+ 数据对应关系 + 后端限制说明，演示/验收前通读 |
| 检索关键词高亮修复 | `src/pages/Retrieval/DifferentiatedResult.tsx` | 原实现 `split(keyword).join('⟦kw⟧')` 后只按左括号 split，导致高亮永不生效且漏出 `⟧` 字符；改为带捕获组的正则 `split`，命中片段正确进 `<mark>` |
| 生成页去阶段卡 | `src/pages/Generation/index.tsx`、`PresetBrief.tsx`（新增） | 删除全预设共用的「01~05 五阶段流水线卡」，改为每预设独有的「生成场景」卡：本次抽取类型 + 重点关注结果 + 三步业务流转示意（11 个预设文案各自不同） |
| 单行轻量进度条 | `src/pages/Generation/index.tsx` | 同步生成时结果区显示一条细进度条（抽取→生成→去重→入库），替代原大号居中 loading 块；异步沿用真实进度卡 |
| 文本预设演示兜底 | `src/pages/Generation/demo-results.ts`（新增） | 6 个文本预设（任务状态/决策/冲突/去重/融合/低价值）打开即自动渲染该预设的差异化结果组件，顶部「真实 Pipeline」标签变橙「演示数据」并显示提示条；提交真实文本或恢复异步任务后自动清除 |

验证：`lint` ✅ 0 警告 / `test` ✅ 45/45 / `build` ✅。接口实测：`memory/list`、`stats`、`search`（top_k=50 关键词命中）、`admin/dashboard` 均返回真实演示数据。

---

## 三、当前状态（此刻在跑什么）

| 服务 | 地址 | 状态 |
| --- | --- | --- |
| 前端 dev server | http://localhost:5173 | ✅ 运行中（默认连远程后端） |
| **远程后端（目标环境）** | http://120.27.207.238:8000 | ✅ 运行中，全部新接口可用（login/list/search/profile/context 等） |
| 本地后端（memProject uvicorn） | http://localhost:8000 | ⚠️ 已停止，且本地代码旧（**无 `/auth/login`**），不再使用 |
| PostgreSQL | localhost:5432 | ✅ 运行中（本地演示数据所在） |
| Qdrant | localhost:6333 | ✅ 运行中 |

**关于数据**：0813 造的 49 条演示数据在**本地库**（user_001 名下）；远程库几乎为空（4 智能体 / 2 场景 / 4 记忆）。登录后 userId 由后端派生，所以远程登录用户暂无记忆数据——这是「链路打通、待导入」状态，等后端批量导入。

> 前端 dev server 启动：`cd D:\PythonProject\agent-memory-frontend-dev && corepack pnpm dev`（`.env.development` 已指向远程 `120.27.207.238:8000`）。

---

## 四、当前卡在哪里（阻塞项 / 遗留）

### 4.1 后端能力未就绪（非前端问题，但影响演示）

1. **mem0 智能链路未配置**：`DEEPSEEK_API_KEY`、`SILICONFLOW_API_KEY` 为空 → 记忆写入/偏好抽取/向量检索等依赖 LLM/Embedding 的能力不可用，走降级。**需后端填 Key**。
2. **pgvector 扩展缺失**：PostgreSQL 上 `vector` 扩展不可用（非致命 warning）。需安装 pgvector。
3. **Kafka / Redis 未运行**：消息队列、异步回调降级（非致命）。
4. ~~**后端无分析类接口**~~ ✅ 已随 0820 处理：生成模块（分析功能）已随 generate 废弃整体移除，无此问题。
5. ~~**后端认证接口未就绪**~~ ✅ 已随 0820 处理：登录已对接真实 `POST /auth/login`（登录即注册），`authStore` mock 已删除；找回密码/GitHub OAuth2 仍为占位。
6. **平台采集任务接口未就绪**：智能体接入的采集配置仅存 localStorage，后端采集任务接口（保存/手动触发/定时调度）未提供。
7. **`embedding_client.py` 缺 `import json`（已定位的 bug）**：`_call_api` 异常处理里引用 `json` 但未导入，导致 embedding 调用必然抛 `NameError`。影响：检索永远走降级、上下文接口直接失败。本地联调可在 `memProject/app/services/embedding_client.py` 顶部补 `import json`，正式环境需后端修复。
8. **`/memory/context` 无降级兜底**：embedding 失败时直接返回 `CONTEXT_FAILED`，前端上下文模块 5 个差异化组件拿不到数据（页面/表单完好）。需后端加 DB-only 兜底或填 Key 才能看到效果。
9. **检索降级只扫最近 `top_k×2` 条**：`memory_store._db_only_search` 先取最近 top_k×2 条再做关键词匹配（`relevance_score = 命中词数 / 关键词数`）。测试时把检索「返回数量」调到 **20/50** 才能覆盖全部演示记忆；默认 10 只搜最近 20 条，可能返回不相关记忆（前端会用演示数据兜底并标注）。

### 4.2 前端遗留（低优先级）

1. **图表体积**：`@ant-design/plots` 的 G2 运行时 ~1.4MB（gzip 427KB），独立懒加载 chunk，可接受；如需优化需按需引入原子图表。
2. **会话级/任务级列表字段**：「关联记忆条数」「会话主题摘要」「结束时间」等字段 `memory/list` 单条返回可能不足，前端先用 `memories.filter()` 聚合兜底，标注"待后端字段补充"。

---

## 五、下一步计划

> **前端已与远程后端链路打通**（登录/列表/检索/画像/看板实测可用）。记忆生成模块已随 generate 废弃而移除。

1. **导入数据**：通过「记忆数据导入」页或后端批量导入，往远程库写入记忆（write 异步，落库后列表/检索可见）。
2. **联调收尾**：逐页对照 `Progress/0820.md` 的 15 项确认；上下文模块（hybrid 检索）在远程验证；画像页需给智能体绑定场景（否则 `SCENE_REQUIRED`）。
3. **8/28 全量部署前**：前端部署到测试服务器（目标连远程后端），逐页验收所有展示字段。
4. **给老师汇报**：0813 六项改造 + 差异化已完成；0820 前后端联动改造已完成，可按 `Progress/0820.md` 汇报。

---

## 六、踩过的坑（新会话务必避开）

### 6.1 命令 / 环境坑

1. **`corepack enable` 会报 EPERM**（无权写 `C:\Program Files\nodejs`）。**不要运行 `corepack enable`**，直接 `corepack pnpm <命令>` 即可。
2. **`pnpm check` 脚本内部直接调 `pnpm`，但本机 pnpm 不在 PATH**。`corepack pnpm check` 会失败（找不到 pnpm）。**分步跑**：`corepack pnpm lint` → `corepack pnpm test` → `corepack pnpm build`。
3. **Windows + Git Bash 里 `??` 和 `||` 不能混用**（`a ?? b || c` 会报 esbuild 解析错误）。需要写成 `(a ?? b) || c`。
4. **Windows 控制台 GBK 编码**：跑 Python 脚本时 `print` 中文/emoji（如 ✅）会报 `UnicodeEncodeError: 'gbk' codec`。脚本输出用 ASCII（`seed-demo-data.py` 末尾已改），或 `PYTHONIOENCODING=utf-8`。

### 6.2 前后端联通坑

5. **浏览器 localStorage 会覆盖 `.env` 的后端地址**（`src/api/client.ts` 拦截器优先读 localStorage）。改了 `.env` 后浏览器仍连旧地址 → 页面接口全失败但 curl 正常。**解决**：前端「系统设置→基础连接设置」改地址，或 `localStorage.removeItem('agent-memory-app-config')` 后刷新。
6. **后端 `admin/api-logs` 单页 `page_size` 上限 100**，前端请求 500 会 422。已改为循环分页拉全量（每页 100）。
7. **Windows 上 Python `zoneinfo` 找不到时区**（`Asia/Shanghai` → dashboard 500）。后端 venv 需 `pip install tzdata`。**测试服务器若是 Windows 也要装**。
8. **后端数据库表可能为空**：初始迁移 `50bedfeed277` 是 stub（"表由外部脚手架创建"），`alembic upgrade head` 会中途失败。建表用 `Base.metadata.create_all`（async 引擎 `run_sync`），生成 13 张表。
9. **检索降级只扫最近 `top_k×2` 条**：`/memory/search` 在无 Key 时走 `_db_only_search`，先取最近 top_k×2 条再关键词匹配。搜不到更早的关键词（如「冷链」）不一定是数据问题——检索页把「返回数量」调到 50 即可覆盖全量。
10. **造数脚本要用后端 venv 的 Python 跑**（需 asyncpg/sqlalchemy）：`D:\PythonProject\agent_mem-master\memProject\.venv\Scripts\python.exe scripts\seed-demo-data.py`。该脚本幂等，可重跑刷新数据。

### 6.3 图表 / 组件坑

11. **图表库选 `@ant-design/plots`，不要用 `@ant-design/charts`**：后者 re-export 了未使用的 graphs 子库，打包冗余。`@ant-design/plots` 是 G2 v5 新 API（`xField`/`yField`/`colorField`/`children`），和旧版 G2Plot 配置不同。
12. **DualAxes 的 `children` prop 会触发 oxlint `react/no-children-prop` 警告**。已在 `children` 行尾加 `// oxlint-disable-line react/no-children-prop -- DualAxes 图表配置属性` 豁免。
13. **页面要差异化时，改「结果展示区」而非「输入区」**：老师认可前置流程统一（选记忆→勾选→触发分析），同质化问题只在结果区。做法是建独立渲染组件按 preset/mode 路由。
14. **React Router 7 的 `lazy` 是路由级懒加载函数**，不是 `React.lazy`。路由对象里用 `lazy: async () => ({ Component: (await import('@/pages/X')).default })`。

### 6.4 其他

15. **`useMemo` 依赖处理器函数（handleXxx）会触发 exhaustive-deps 警告**，且处理器每次渲染重建导致 memo 失效。直接去掉 useMemo 用普通函数/IIFE 更干净。
16. **杀掉旧 dev server 后要确认端口释放**：曾有 5173/5174 两个 dev server 并存，可能看错端口。重启后确认只监听 5173。
17. **前端是 SPA**，curl 拿到的 index.html 只是空壳（`<title>` 能拿到但页面内容 JS 渲染）。验证前端改动看 dev server 日志（HMR 是否应用、有无编译错误），别靠 curl 看页面内容。

### 6.5 0820 改造后（新会话必看）

18. **登录是硬门槛且走真实 `/auth/login`**：登录页在登录墙后，若浏览器 localStorage 的 `agent-memory-app-config` 指向了**没有该接口的后端**（如本地旧后端），登录会 404，且**进不了设置页改回来**（死锁）。解决：DevTools 执行 `localStorage.removeItem('agent-memory-app-config'); location.reload()` 恢复 `.env` 指向的远程后端。
19. **记忆类型收敛为 5 类**：`fact / preference / task_state / process / correction`。旧的 `decision / constraint / feedback` 已废弃（后端会忽略/报错），前端任何下拉/过滤都不要再发旧值。
20. **`/memory/list` 是 POST 不是 GET**：接口文档写过 GET，后端实现是 `@router.post("/list")`，前端必须 POST（0820 已修）。
21. **`/memory/write` 已异步**：只落 L0，`session_id` 必填，响应 `{accepted, session_id, l0_count, record_ids}`，不再有 `results[]`，也别设长超时。
22. **生成模块已删**：`/memory/generate` 系列 404，前端「生成与去重融合」菜单/页面/相关类型已全部移除；检索已收敛为单页（6 mode 删除）。

---

## 七、目录结构与关键约定

```
scripts/
  seed-demo-data.py     造数脚本（后端 venv Python 运行，幂等；类型已对齐 5 类）
src/
  api/                  接口层（client.ts 拦截器读 localStorage baseUrl；身份走 Header）
    modules/auth.ts     （0820 新增）真实登录 /auth/login
  components/
    business/           业务组件（ConfigForm 等）
    common/             通用组件（PageContainer/FeedbackState/EmptyState 等）
  constants/            常量（routes/platform/storage；generation.ts 已删）
  layouts/              AppLayout（顶栏接登录态）+ SidebarMenu
  pages/                Overview/Memory/MemoryProfile(0820新增)/Retrieval/Context/AgentAccess/Ingestion/Login/...
    Retrieval/          index.tsx（单页检索，6 mode 已收敛）
    Context/            index.tsx + DifferentiatedResult.tsx（5 模式差异化）
  router/               routes.tsx（含登录路由+守卫）/ route-config.tsx（菜单，无生成模块）
  store/                appStore/authStore(真实登录)/memoryStore/taskStore
  utils/                storage/feedback/config 等
Progress/               0810.md / 0813.md / 0820.md（0820 改造方案与实施记录）/ 前端测试指南-0813.md
API接口文档.md / API接口文档-前端对接.md   后端接口契约（后者为 0820 权威版）
前端修改任务.md         后端团队 0820 下发的前端改造任务清单
```

**关键约定**：
- 页面不直接拼请求，统一走 `src/api`。
- 记忆类型只用 5 类（fact/preference/task_state/process/correction）。
- 修改接口字段先改 `src/api/types.ts` 和对应模块，再改页面。
- 后端未提供的能力，前端用演示数据兜底并**明确标注"演示数据"**（0820 后演示兜底已大幅减少）。

---

## 八、给接手者的第一件事

1. 读 `Progress/0820.md`（0820 前后端联动改造：15 项任务 + 实施记录）、`Progress/前端测试指南-0813.md`（逐页怎么测）。
2. 前端 dev server：`cd D:\PythonProject\agent-memory-frontend-dev && corepack pnpm dev`；确认 http://localhost:5173 通。
3. 浏览器打开 http://localhost:5173 → 登录 `admin / admin123`（走真实 `/auth/login`，连**远程**后端）。若登录 404，先 `localStorage.removeItem('agent-memory-app-config')` 刷新（见坑 6.5-18）。
4. 登录后 userId 是后端派生的（admin → `user_796ac3c9cf51`）；远程库暂无记忆，记忆页空态是正常的，先通过「记忆数据导入」写入或等批量导入。
5. 检索/画像/上下文/看板均为真实接口（远程验证）；画像需智能体绑定场景，否则报 `SCENE_REQUIRED`。
6. 有任何改动，改完跑 `corepack pnpm lint` → `corepack pnpm test` → `corepack pnpm build`（分步，`check` 脚本会挂）。

---

*本文档由前端负责人维护，供新会话/同事无缝接手。详细会议意见、方案、完成记录见 `Progress/0810.md`、`Progress/0813.md`；0820 前后端联动改造（15 项）见 `Progress/0820.md`；逐页测试方法与数据对应见 `Progress/前端测试指南-0813.md`。*
