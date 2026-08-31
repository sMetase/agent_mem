# 智能体记忆系统 — 前端接口对接文档

> **更新日期：2026-08-20**，已与后端实际路由对齐。
> 标记说明：【新增】= 旧文档没有、后端已实现；【变更】= 旧文档有但参数/响应已改；【废弃】= 已删除，前端不得再调用。
> 本文档为**当前后端全部接口**的权威说明，取代旧版（旧版含大量过时内容，已废弃）。

---

## 0. 本版改动速览

### 【废弃】接口（前端请立即停止调用）

| 旧接口 | 说明 |
|------|------|
| `POST /memory/generate` | 已删除，记忆生成统一走 `/memory/write` 异步链路 |
| `POST /memory/generate/batch` | 已删除 |
| `POST /memory/generate/async` | 已删除 |
| `GET /memory/generate/{id}/status` | 已删除 |
| `POST /memory/async_write` | 已删除（`/memory/write` 本身就是异步） |

### 【新增】接口（旧文档未覆盖）

| 新接口 | 说明 |
|------|------|
| `POST /auth/login` | 登录即注册，前端登录必用 |
| `GET /memory/stats` | 记忆层级分布统计 |
| `POST /memory/profile` | 用户画像报告（L3） |
| `GET /agent`、`GET /agent/{id}`、`PUT /agent/{id}`、`DELETE /agent/{id}`、`POST /agent/{id}/rotate-key` | 智能体完整 CRUD + Key 轮换 |
| `GET /scene`、`GET /scene/{id}`、`PUT /scene/{id}`、`DELETE /scene/{id}` | 场景完整 CRUD |
| `GET /session`、`GET /session/{id}`、`PUT /session/{id}` | 会话查询/列表/更新 |
| `GET /task`、`GET /task/{id}`、`POST /task/{id}/complete` | 任务查询/列表/完成 |
| `GET /admin/memories`、`GET /admin/memories/{id}`、`GET /admin/retrieval-logs`、`GET /admin/stats`、`GET /admin/dashboard`、`GET /admin/api-logs` | 管理后台 6 个接口 |
| `GET /monitor/stats` | worker 可观测统计 |
| `POST /proxy/{space_id}/v1/chat/completions` | OpenAI 兼容透明代理 |
| `GET /health`、`GET /api/v1/health` | 健康检查 |

### 【变更】接口（参数/响应已改）

| 接口 | 变更点 |
|------|------|
| `POST /memory/write` | 改为异步 Kafka 投递，`session_id` 变必填，响应结构改为 `{accepted, l0_count, record_ids}` |
| `POST /memory/search` | 检索改 hybrid（dense+sparse RRF 融合），`memory_types` 改为 5 类新枚举 |
| `POST /memory/context` | 改走 hybrid 检索，响应新增 `estimated_tokens`、`fragments` |

---

## 1. 基础信息

| 项 | 值 |
|------|-----|
| 开发 Base URL | `http://127.0.0.1:8000` |
| 生产 Base URL | `http://120.27.207.238:8000` |
| 数据格式 | JSON（UTF-8） |
| 接口前缀 | 除 `/health`、`/api/v1/health`、`/proxy/...` 外，均在 `/api/v1` 下 |

### 1.1 鉴权方式

| 场景 | 方式 |
|------|------|
| 开发阶段（`AUTH_ENABLED=False`） | 跳过鉴权，Header 可传 `X-Agent-Id` 指定智能体，缺省用测试智能体 |
| 生产阶段（`AUTH_ENABLED=True`） | 必须提供 `X-API-Key`（注册智能体时返回的明文 key）或 `Authorization: Bearer <token>` |

**常用请求头**（写入/检索时用于租户隔离）：

| Header | 含义 | 说明 |
|------|------|------|
| `X-API-Key` | 智能体身份 | 生产阶段必填 |
| `X-Agent-Id` | 智能体 ID | 开发阶段用 |
| `X-User-Id` | 用户 ID | 优先级高于 Body 里的 `user_id` |
| `X-Scene-Id` | 场景 ID | 优先级高于 Body 里的 `scene_id` |
| `X-Session-Id` | 会话 ID | 优先级高于 Body 里的 `session_id` |
| `X-Task-Id` | 任务 ID | 优先级高于 Body 里的 `task_id` |

> 管理后台（`/admin/*`）接口额外要求智能体 `permissions` 含 `admin`（生产阶段）。

### 1.2 统一响应格式

成功（`code=0`）：
```json
{"code": 0, "message": "ok", "data": {...}}
```

失败（`code=-1`）：
```json
{"code": -1, "message": "错误描述", "error_code": "NOT_FOUND", "trace_id": "abc123"}
```

分页响应 `data` 结构：
```json
{"items": [...], "total": 100, "page": 1, "page_size": 20}
```

前端先看 `code != 0` 判断失败，再按 `error_code` 细分错误类型。

### 1.3 记忆类型（5 类）

`memory_type` 的合法值已从旧的 5 类（preference/fact/task/decision/constraint）改为：

| 值 | 含义 |
|------|------|
| `fact` | 关键事实 |
| `preference` | 用户偏好 |
| `task_state` | 任务状态/进展 |
| `process` | 流程/方法论/决策/经验 |
| `correction` | 用户纠正/修订 |

---

## 2. 系统接口

### 2.1 GET /health 【新增】

健康检查，无鉴权。

```json
// ← 返回
{"status": "ok", "app": "agent-memory", "version": "1.0.0"}
```

### 2.2 GET /api/v1/health 【新增】

```json
// ← 返回
{"status": "ok", "app": "agent-memory", "version": "1.0.0", "database": true}
```

---

## 3. 认证接口

### 3.1 POST /api/v1/auth/login 【新增】

**登录即注册**：`username` 不存在时自动创建账号（用传入密码）；已存在则校验密码。

```json
// → 发送
{"username": "admin", "password": "admin123"}

// ← 返回
{
  "code": 0,
  "data": {
    "user": {"user_id": "usr_xxx", "username": "admin", "name": "admin"},
    "token": "eyJhbGciOi...",
    "user_id": "usr_xxx"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | 是 | 登录账号（1-128 字符） |
| `password` | string | 是 | 密码（1-128 字符） |

**响应 `data` 字段：**

| 字段 | 说明 |
|------|------|
| `user.user_id` | 用户唯一标识（登录派生，前端应保存并用于后续 `user_id`） |
| `user.username` | 登录账号 |
| `user.name` | 显示名（初始 = username） |
| `token` | JWT（subject = user_id） |
| `user_id` | 冗余字段，等价 `user.user_id` |

> 前端登录后把 `user_id` 写入应用配置，后续所有请求用它作为用户标识；不再需要用户在设置页手动填 userId。

---

## 4. 智能体接口（/agent）

### 4.1 POST /api/v1/agent/register

注册智能体，返回 API Key（**仅此一次明文**）。

```json
// → 发送
{"agent_name": "Web聊天助手", "scene_id": "scene_xxx", "permissions": ["read", "write"]}

// ← 返回
{
  "code": 0,
  "data": {
    "agent_id": "agent_xxx",
    "agent_name": "Web聊天助手",
    "api_key": "mem_xxxx",
    "api_key_prefix": "mem_****",
    "scene_id": "scene_xxx",
    "is_active": true,
    "created_at": "2026-08-20T..."
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent_name` | string | 是 | 智能体名称（1-256） |
| `scene_id` | string | 是 | 所属场景（**需先创建场景**，否则 404） |
| `permissions` | array | 否 | 默认 `["read","write"]`，管理接口需含 `admin` |

> `api_key` 仅注册时返回一次明文，请保存到前端配置。丢失需调 `/agent/{id}/rotate-key` 换新。

### 4.2 GET /api/v1/agent/{agent_id} 【新增】

查询单个智能体（不含 API Key 明文）。

```json
// ← 返回
{"code":0, "data":{"agent_id":"agent_xxx","agent_name":"...","scene_id":"...","api_key_prefix":"mem_****","is_active":true,"permissions":["read","write"],"created_at":"...","updated_at":"..."}}
```

### 4.3 GET /api/v1/agent 【新增】

分页查询智能体列表。

Query 参数：`scene_id`（可选）、`is_active`（可选）、`page`（默认 1）、`page_size`（默认 20，最大 100）。

```json
// ← 返回
{"code":0, "data":{"items":[{"agent_id":"...","agent_name":"...","scene_id":"...","api_key_prefix":"...","is_active":true,"permissions":[...],"created_at":"...","updated_at":"..."}], "total":10, "page":1, "page_size":20}}
```

### 4.4 PUT /api/v1/agent/{agent_id} 【新增】

更新智能体（名称/权限/启停）。

```json
// → 发送
{"agent_name": "新名称", "is_active": true, "permissions": ["read","write"], "extra_meta": {}}
// ← 返回
{"code":0, "data":{"agent_id":"agent_xxx", "updated":true}}
```

### 4.5 DELETE /api/v1/agent/{agent_id} 【新增】

停用智能体（软删除）。

```json
// ← 返回
{"code":0, "data":{"agent_id":"agent_xxx", "is_active":false}}
```

### 4.6 POST /api/v1/agent/{agent_id}/rotate-key 【新增】

轮换 API Key，旧 Key 立即失效。

```json
// ← 返回
{"code":0, "data":{"agent_id":"agent_xxx", "api_key":"mem_newkey", "api_key_prefix":"mem_****"}}
```

---

## 5. 场景接口（/scene）

### 5.1 POST /api/v1/scene

创建场景。

```json
// → 发送
{"scene_name": "代码助手", "description": "写代码相关对话", "extra_meta": {}}
// ← 返回
{"code":0, "data":{"scene_id":"scene_xxx","scene_name":"代码助手","description":"...","is_active":true,"created_at":"..."}}
```

### 5.2 GET /api/v1/scene/{scene_id} 【新增】

查询单个场景。

```json
// ← 返回
{"code":0, "data":{"scene_id":"scene_xxx","scene_name":"...","description":"...","is_active":true,"created_at":"...","updated_at":"..."}}
```

### 5.3 GET /api/v1/scene 【新增】

分页场景列表。Query：`is_active`（可选）、`page`、`page_size`。

```json
// ← 返回
{"code":0, "data":{"items":[...],"total":5,"page":1,"page_size":20}}
```

### 5.4 PUT /api/v1/scene/{scene_id} 【新增】

更新场景。

```json
// → 发送
{"scene_name": "新名称", "description": "...", "is_active": true, "extra_meta": {}}
// ← 返回
{"code":0, "data":{"scene_id":"scene_xxx", "updated":true}}
```

### 5.5 DELETE /api/v1/scene/{scene_id} 【新增】

停用场景（软删除）。

```json
// ← 返回
{"code":0, "data":{"scene_id":"scene_xxx", "is_active":false}}
```

---

## 6. 会话接口（/session）

### 6.1 POST /api/v1/session

创建会话（状态 active）。

```json
// → 发送
{"user_id":"user_001","agent_id":"agent_xxx","scene_id":"scene_xxx","task_id":"task_xxx","extra_meta":{}}
// ← 返回
{"code":0, "data":{"session_id":"sess_xxx","user_id":"user_001","agent_id":"...","scene_id":"...","task_id":"...","status":"active","started_at":"..."}}
```

### 6.2 GET /api/v1/session/{session_id} 【新增】

查询单个会话。

```json
// ← 返回
{"code":0, "data":{"session_id":"...","user_id":"...","agent_id":"...","scene_id":"...","task_id":"...","status":"active","message_count":0,"started_at":"...","ended_at":null}}
```

### 6.3 GET /api/v1/session 【新增】

分页会话列表。Query：`user_id`、`agent_id`、`status`、`scene_id`（均可选）、`page`、`page_size`。

### 6.4 PUT /api/v1/session/{session_id} 【新增】

更新会话状态/关联任务。

```json
// → 发送
{"status": "archived", "task_id": "task_xxx", "extra_meta": {}}
// ← 返回
{"code":0, "data":{"session_id":"...", "updated":true}}
```

### 6.5 POST /api/v1/session/{session_id}/close 【变更】

关闭会话，触发记忆压缩（preference/fact 升级为长期记忆，task_state/process/correction 压缩为摘要）。

```json
// ← 返回
{
  "code": 0,
  "data": {
    "session_id": "sess_xxx",
    "status": "closed",
    "total_memory_count": 10,
    "kept_count": 6,
    "compressed_count": 4,
    "summary_text": "本次会话摘要...",
    "ended_at": "..."
  }
}
```

---

## 7. 任务接口（/task）

### 7.1 POST /api/v1/task

创建任务（状态 pending）。

```json
// → 发送
{"user_id":"user_001","agent_id":"agent_xxx","scene_id":"scene_xxx","session_id":"sess_xxx","title":"技术方案编写","goal":"完成Q3技术方案","extra_meta":{}}
// ← 返回
{"code":0, "data":{"task_id":"task_xxx","user_id":"user_001","title":"技术方案编写","goal":"...","status":"pending","started_at":"..."}}
```

### 7.2 GET /api/v1/task/{task_id} 【新增】

查询单个任务。

```json
// ← 返回
{"code":0, "data":{"task_id":"...","user_id":"...","agent_id":"...","scene_id":"...","session_id":"...","title":"...","goal":"...","status":"pending","progress":null,"completed_items":[],"pending_items":[],"started_at":"...","ended_at":null}}
```

### 7.3 GET /api/v1/task 【新增】

分页任务列表。Query：`user_id`、`status`、`session_id`（均可选）、`page`、`page_size`。

### 7.4 PUT /api/v1/task/{task_id}

更新任务进展（状态机校验：pending→in_progress→completed，cancelled→pending）。

```json
// → 发送
{"title":"...","goal":"...","status":"in_progress","progress":"已完成需求分析","completed_items":["需求文档"],"pending_items":["技术方案"],"extra_meta":{}}
// ← 返回
{"code":0, "data":{"task_id":"task_xxx", "updated":true, "status":"in_progress"}}
```

### 7.5 GET /api/v1/task/{task_id}/progress

任务进展摘要。

```json
// ← 返回
{"code":0, "data":{"task_id":"task_xxx","status":"in_progress","progress":"...","completed_count":3,"pending_count":2,"related_memory_count":12,"last_activity":"..."}}
```

### 7.6 POST /api/v1/task/{task_id}/complete 【新增】

标记任务完成。

```json
// ← 返回
{"code":0, "data":{"task_id":"task_xxx", "status":"completed", "ended_at":"..."}}
```

---

## 8. 记忆接口（/memory）

### 8.1 POST /api/v1/memory/write 【变更】

写入记忆。**已改为异步**：投递 Kafka 后立即返回，L1 后台 worker 异步抽取记忆，**不再阻塞等待 LLM 抽取**。

支持三种数据类型（`interaction_type`）：`dialogue`（对话）、`session`（历史会话导入）、`task_process`（任务过程）。

```json
// → 发送（dialogue 最常用）
{
  "user_id": "user_001",
  "scene_id": "scene_xxx",
  "session_id": "sess_xxx",
  "interaction_type": "dialogue",
  "messages": [
    {"role": "user", "content": "订单DH001需要退货退款"},
    {"role": "assistant", "content": "好的，已为您提交"}
  ]
}

// ← 返回（Kafka 正常）
{"code":0, "data":{"accepted":true, "session_id":"sess_xxx", "l0_count":2, "record_ids":["rec_xxx","rec_yyy"]}}

// ← 返回（Kafka 不可用，降级同步落 L0）
{"code":0, "data":{"accepted":true, "session_id":"sess_xxx", "l0_count":2, "record_ids":[...], "degraded":true}}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | 是 | 用户唯一标识 |
| `session_id` | string | **是** | 会话 ID（**本版改为必填**） |
| `scene_id` | string | 否 | 场景标识 |
| `task_id` | string | 否 | 任务标识 |
| `interaction_type` | string | 否 | `dialogue`/`session`/`task_process`，默认 dialogue |
| `messages` | array | dialogue 必填 | `[{"role":"user","content":"..."}]`，role 支持 user/assistant/system/tool/agent |
| `session_time` | string | session 时 | 历史会话时间 ISO 8601 |
| `session_source` | string | session 时 | 会话来源 |
| `session_summary` | string | session 时 | 会话摘要 |
| `task_goal` | string | task_process 时 | 任务目标 |
| `task_progress` | string | task_process 时 | 任务进展 |
| `task_result` | string | task_process 时 | 执行结果 |
| `metadata` | object | 否 | 扩展元数据 |

**响应字段：**

| 字段 | 说明 |
|------|------|
| `accepted` | 是否已受理 |
| `l0_count` | 落 L0 的记录条数 |
| `record_ids` | L0 记录 ID（幂等键） |
| `degraded` | 仅降级路径返回，表示 Kafka 不可用 |

> **注意**：这是异步链路，写入后记忆不会立即出现在检索结果里。需等 L1 worker 抽取（通常秒级到几十秒）。前端展示对话，后台异步生成记忆。

### 8.2 POST /api/v1/memory/search 【变更】

检索记忆。**已改 hybrid 检索**（dense 语义 + sparse 关键词 RRF 融合）。

```json
// → 发送
{
  "query": "DH001",
  "user_id": "user_001",
  "scene_id": "scene_xxx",
  "task_id": "task_xxx",
  "session_id": "sess_xxx",
  "memory_types": ["fact", "preference"],
  "keyword": "DH001",
  "top_k": 5,
  "status": ["active"],
  "rerank": true
}

// ← 返回
{
  "code": 0,
  "data": {
    "query": "DH001",
    "results": [
      {
        "memory_id": "mem_xxx",
        "content": "订单DH001需要退货退款",
        "summary": "...",
        "memory_type": "fact",
        "scene_id": "scene_xxx",
        "task_id": "task_xxx",
        "session_id": "sess_xxx",
        "status": "active",
        "importance": 0.8,
        "confidence": 0.9,
        "relevance_score": 0.85,
        "created_at": "2026-08-20T...",
        "updated_at": "2026-08-20T..."
      }
    ],
    "total_candidates": 30,
    "elapsed_ms": 156
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 检索文本 |
| `user_id` | string | 是 | 用户标识 |
| `scene_id` | string | 否 | 场景过滤 |
| `task_id` | string | 否 | 任务过滤 |
| `session_id` | string | 否 | 会话过滤 |
| `memory_types` | array | 否 | 类型过滤，合法值：`fact`/`preference`/`task_state`/`process`/`correction` |
| `keyword` | string | 否 | 应用层关键词强制后过滤 |
| `top_k` | int | 否 | 返回条数，默认 10，最大 50 |
| `time_start` / `time_end` | string | 否 | 时间范围 ISO 8601 |
| `include_scores` | bool | 否 | 默认 true |
| `rerank` | bool | 否 | 默认 true（+150-200ms） |
| `status` | array | 否 | 默认只查 `active` |
| `max_content_length` | int | 否 | 内容截断长度 |

### 8.3 POST /api/v1/memory/context 【变更】

检索并格式化为 Prompt 上下文片段。**已改走 hybrid 检索**。

```json
// → 发送
{
  "query": "当前任务",
  "user_id": "user_001",
  "scene_id": "scene_xxx",
  "max_tokens": 3000,
  "top_k": 10,
  "group_by_type": true,
  "memory_types": ["preference", "fact"]
}

// ← 返回
{
  "code": 0,
  "data": {
    "formatted_text": "## User Preferences\n- 用户偏好 Python\n## Key Facts\n- 订单DH001需要退货退款",
    "memory_count": 2,
    "estimated_tokens": 45,
    "fragments": [
      {"memory_id":"mem_xxx","content":"...","summary":"...","memory_type":"fact","relevance_score":0.85}
    ]
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 当前用户问题 |
| `user_id` | string | 是 | 用户标识 |
| `agent_id` | string | 否 | 智能体 |
| `scene_id` / `task_id` / `session_id` | string | 否 | 过滤维度 |
| `max_tokens` | int | 否 | 默认 3000 |
| `top_k` | int | 否 | 默认 10 |
| `group_by_type` | bool | 否 | 默认 true，按类型分组 |
| `memory_types` | array | 否 | 类型过滤 |
| `status` | array | 否 | 状态过滤 |
| `include_preferences` / `include_facts` / `include_task_state` | bool | 否 | 默认 true |
| `rerank` | bool | 否 | 默认 false |

**响应字段**：`formatted_text`（格式化好的 Prompt 文本）、`memory_count`（实际记忆条数）、`estimated_tokens`（token 估算）、`fragments`（原始检索片段）。

### 8.4 PUT /api/v1/memory/update

更新单条记忆。

```json
// → 发送
{"memory_id":"mem_xxx","content":"修正后的内容","summary":"...","status":"active","importance":0.9,"confidence":0.9,"tags":["x"]}
// ← 返回
{"code":0, "data":{"memory_id":"mem_xxx", "updated":true, "version":2}}
```

### 8.5 DELETE /api/v1/memory/delete

软删除单条记忆。

```json
// → 发送
{"memory_id":"mem_xxx","reason":"用户要求"}
// ← 返回
{"code":0, "data":{"memory_id":"mem_xxx", "deleted":true, "previous_status":"active"}}
```

### 8.6 POST /api/v1/memory/list

分页列出全部记忆（Query 参数，POST）。

```
POST /api/v1/memory/list?user_id=user_001&page=1&page_size=20
```

Query：`user_id`（必填）、`scene_id`、`task_id`、`session_id`、`memory_scope`、`page`（默认 1）、`page_size`（默认 20，最大 100）。

```json
// ← 返回
{"code":0, "data":{"items":[{...记忆对象...}], "total":100, "page":1, "page_size":20}}
```

### 8.7 POST /api/v1/memory/delete-all

清除全部记忆。

```
POST /api/v1/memory/delete-all?user_id=user_001&scene_id=scene_xxx
```

```json
// ← 返回
{"code":0, "data":{"message":"...", "deleted_count":50}}
```

### 8.8 GET /api/v1/memory/stats 【新增】

记忆层级分布统计（user/session/task/agent 四层）。

```
GET /api/v1/memory/stats?user_id=user_001&scene_id=scene_xxx
```

```json
// ← 返回
{
  "code": 0,
  "data": {
    "total": 100,
    "level_distribution": [
      {"level": "user", "count": 40, "ratio": 0.4},
      {"level": "session", "count": 30, "ratio": 0.3},
      {"level": "task", "count": 20, "ratio": 0.2},
      {"level": "agent", "count": 10, "ratio": 0.1}
    ],
    "generated_at": "2026-08-20T...",
    "classification_version": "memory_scope_v1"
  }
}
```

### 8.9 POST /api/v1/memory/profile 【新增】

用户画像报告（L3 画像，消费 L2 场景块）。

```json
// → 发送
{"user_id":"user_001","max_memories":50}
// ← 返回
{"code":0, "data":{"persona":"用户画像自由文本...","scene_id":"scene_xxx","changed_scenes":2}}
```

> 画像从当前 agent 绑定的 scene_id 推导，agent 未绑定场景时返回 `SCENE_REQUIRED`。

### 8.10 POST /api/v1/memory/compress 【变更】

压缩长对话为结构化记忆。

```json
// → 发送
{"text":"长对话文本...","validate_preservation":true}
// ← 返回
{
  "code":0,
  "data":{
    "conversation_overview":"...","key_facts_count":3,"preferences_count":2,
    "decisions_count":1,"corrections_count":0,"original_length":500,
    "compressed_length":120,"compression_ratio":0.24,"preservation_score":0.95,"compact_text":"..."
  }
}
```

### 8.11 POST /api/v1/memory/context/complete 【变更】

基于历史压缩记忆补全上下文。

```json
// → 发送
{"query":"当前查询","memory_ids":["mem_xxx","mem_yyy"],"max_context_tokens":3000}
// ← 返回
{"code":0, "data":{"context_text":"...","sections_used":["..."],"estimated_relevance":0.85}}
```

---

## 9. 管理后台接口（/admin）

> 生产阶段需智能体 `permissions` 含 `admin`。所有接口返回分页结构 `{items, total, page, page_size}`。

### 9.1 GET /api/v1/admin/memories 【新增】

分页查询全部记忆（跨用户）。

```
GET /api/v1/admin/memories?user_id=user_001&memory_type=fact&status=active&page=1&page_size=20
```

### 9.2 GET /api/v1/admin/memories/{memory_id} 【新增】

记忆详情（含关系链路）。

```json
// ← 返回
{"code":0, "data":{"memory_id":"...","content":"...","memory_type":"...","status":"...","importance":0.8,"user_id":"...","agent_id":"...","session_id":"...","task_id":"...","created_at":"...","relations":[...]}}
```

### 9.3 GET /api/v1/admin/retrieval-logs 【新增】

检索请求日志。Query：`agent_id`（可选）、`hours`（默认 24，最大 720）、`page`、`page_size`。

### 9.4 GET /api/v1/admin/stats 【新增】

系统统计概览（聚合计数）。

### 9.5 GET /api/v1/admin/dashboard 【新增】

系统总览 Dashboard。Query：`hours`（1-168，默认 24）、`trend_days`（1-90，默认 7）。

返回 `summary`（指标卡）、`comparison`（环比）、`memory_trend`（按日趋势）、`memory_type_distribution`（类型分布）、`generation_summary`（去重汇总）、`retrieval_signal_distribution`（检索信号）、`recent_agents`、`recent_retrievals`、`recent_alerts`、`recent_tasks`、`latest_context`。

### 9.6 GET /api/v1/admin/api-logs 【新增】

接口调用日志。Query：`api_path`（可选）、`error_code`（可选）、`hours`（默认 24）、`page`、`page_size`。

---

## 10. 监控接口（/monitor）

### 10.1 GET /api/v1/monitor/stats 【新增】

worker 可观测统计（积压数、失败率、产出速率），仅聚合计数不暴露内容。

```json
// ← 返回
{"code":0, "data":{...worker 统计快照...}}
```

---

## 11. 透明代理接口（/proxy）

### 11.1 POST /proxy/{space_id}/v1/chat/completions 【新增】

OpenAI 兼容透明代理：接收外部 Agent 的 LLM 请求 → 召回记忆注入 → 转发 LLM → 异步写回记忆。

```
POST /proxy/{space_id}/v1/chat/completions
```

- `space_id` 从 URL 提取，映射到 `{user_id, api_key, scene_id, agent_id}`（YAML 配置 `spaces.yaml`）
- 请求体为 OpenAI 格式 `{model, messages}`
- 响应为 OpenAI 兼容格式（`choices[0].message.content` 为 LLM 回复）

```json
// → 发送
{"model":"deepseek-chat","messages":[{"role":"user","content":"你好"}]}
// ← 返回
{"id":"chatcmpl-...","object":"chat.completion","model":"deepseek-chat","choices":[{"index":0,"message":{"role":"assistant","content":"..."},"finish_reason":"stop"}],"usage":{...}}
```

---

## 12. 废弃接口（前端请勿调用）

以下接口已从后端删除，调用返回 404：

| 废弃接口 | 替代方案 |
|------|------|
| `POST /memory/generate` | 改用 `POST /memory/write` |
| `POST /memory/generate/batch` | 改用 `POST /memory/write`（逐条） |
| `POST /memory/generate/async` | 无需，`/write` 本身异步 |
| `GET /memory/generate/{id}/status` | 无需，用 `/memory/list` 轮询 L1 抽取结果 |
| `POST /memory/async_write` | 改用 `POST /memory/write` |

---

## 13. 完整接口清单（速查）

| 方法 | 路径 | 状态 |
|------|------|------|
| GET | `/health` | 新增 |
| GET | `/api/v1/health` | 新增 |
| POST | `/api/v1/auth/login` | 新增 |
| POST | `/api/v1/agent/register` | 已有 |
| GET | `/api/v1/agent` | 新增 |
| GET | `/api/v1/agent/{agent_id}` | 新增 |
| PUT | `/api/v1/agent/{agent_id}` | 新增 |
| DELETE | `/api/v1/agent/{agent_id}` | 新增 |
| POST | `/api/v1/agent/{agent_id}/rotate-key` | 新增 |
| POST | `/api/v1/scene` | 已有 |
| GET | `/api/v1/scene` | 新增 |
| GET | `/api/v1/scene/{scene_id}` | 新增 |
| PUT | `/api/v1/scene/{scene_id}` | 新增 |
| DELETE | `/api/v1/scene/{scene_id}` | 新增 |
| POST | `/api/v1/session` | 已有 |
| GET | `/api/v1/session` | 新增 |
| GET | `/api/v1/session/{session_id}` | 新增 |
| PUT | `/api/v1/session/{session_id}` | 新增 |
| POST | `/api/v1/session/{session_id}/close` | 变更 |
| POST | `/api/v1/task` | 已有 |
| GET | `/api/v1/task` | 新增 |
| GET | `/api/v1/task/{task_id}` | 新增 |
| PUT | `/api/v1/task/{task_id}` | 已有 |
| GET | `/api/v1/task/{task_id}/progress` | 已有 |
| POST | `/api/v1/task/{task_id}/complete` | 新增 |
| POST | `/api/v1/memory/write` | 变更 |
| POST | `/api/v1/memory/search` | 变更 |
| POST | `/api/v1/memory/context` | 变更 |
| PUT | `/api/v1/memory/update` | 已有 |
| DELETE | `/api/v1/memory/delete` | 已有 |
| POST | `/api/v1/memory/list` | 已有 |
| POST | `/api/v1/memory/delete-all` | 已有 |
| GET | `/api/v1/memory/stats` | 新增 |
| POST | `/api/v1/memory/profile` | 新增 |
| POST | `/api/v1/memory/compress` | 变更 |
| POST | `/api/v1/memory/context/complete` | 变更 |
| GET | `/api/v1/admin/memories` | 新增 |
| GET | `/api/v1/admin/memories/{memory_id}` | 新增 |
| GET | `/api/v1/admin/retrieval-logs` | 新增 |
| GET | `/api/v1/admin/stats` | 新增 |
| GET | `/api/v1/admin/dashboard` | 新增 |
| GET | `/api/v1/admin/api-logs` | 新增 |
| GET | `/api/v1/monitor/stats` | 新增 |
| POST | `/proxy/{space_id}/v1/chat/completions` | 新增 |

**废弃接口（404）**：`/memory/generate`、`/memory/generate/batch`、`/memory/generate/async`、`/memory/generate/{id}/status`、`/memory/async_write`
