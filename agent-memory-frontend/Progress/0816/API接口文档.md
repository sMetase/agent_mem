# API 接口文档

## 目录

- [一 智能体接入管理](#一-智能体接入管理)
  - [1. 注册智能体](#agent-register)
  - [2. 查询智能体](#agent-get)
  - [3. 智能体列表](#agent-list)
  - [4. 更新智能体](#agent-update)
  - [5. 停用智能体](#agent-disable)
  - [6. 轮换 API Key](#agent-rotate-key)
- [二 记忆数据写入](#二-记忆数据写入)
  - [7. 同步写入记忆](#write-sync)
  - [8. 异步写入记忆](#write-async)
- [三 会话管理](#三-会话管理)
  - [1. 创建会话](#session-create)
  - [2. 查询会话](#session-get)
  - [3. 会话列表](#session-list)
  - [4. 更新会话](#session-update)
  - [5. 关闭会话](#session-close)
- [四 场景管理](#四-场景管理)
  - [1. 创建场景](#scene-create)
  - [2. 查询场景](#scene-get)
  - [3. 场景列表](#scene-list)
  - [4. 更新场景](#scene-update)
  - [5. 停用场景](#scene-disable)
- [五 任务管理](#五-任务管理)
  - [1. 创建任务](#task-create)
  - [2. 查询任务](#task-get)
  - [3. 任务列表](#task-list)
  - [4. 更新任务进展](#task-update)
  - [5. 任务进展摘要](#task-progress)
  - [6. 完成任务](#task-complete)
- [六 记忆管理](#六-记忆管理)
  - [1. 列出全部记忆](#mem-list)
  - [2. 更新记忆](#mem-update)
  - [3. 删除记忆](#mem-delete)
  - [4. 清除全部记忆](#mem-delete-all)
  - [5. 记忆层级分布统计](#mem-stats)
- [七 多信号融合检索](#七-多信号融合检索)
  - [1. 语义检索记忆](#search)
  - [2. 上下文装配](#context)
  - [3. 更新记忆](#search-update)
  - [4. 用户画像报告](#profile)
- [八 管理后台](#八-管理后台)
  - [1. 分页查询全部记忆](#admin-memories)
  - [2. 记忆详情](#admin-memory-detail)
  - [3. 检索请求日志](#admin-retrieval-logs)
  - [4. 系统统计概览](#admin-stats)
  - [5. Dashboard](#admin-dashboard)
  - [6. 接口调用日志](#admin-api-logs)
- [九 记忆生成工具](#九-记忆生成工具)
  - [1. 单文本生成](#gen-sync)
  - [2. 批量生成](#gen-batch)
  - [3. 异步生成](#gen-async)
  - [4. 查询异步状态](#gen-status)
  - [5. 长对话压缩](#gen-compress)
  - [6. 上下文补全](#gen-context-complete)

---

## 一 智能体接入管理

<a id="agent-register"></a>

### 1. 注册智能体

外部智能体首次接入记忆系统时调用，获取唯一身份凭证。必须绑定一个 scene_id。

**接口**

```
POST /api/v1/agent/register
Content-Type: application/json
无需认证（开发阶段）
```

**入参**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:---:|--------|------|
| `agent_name` | string | ✅ | — | 智能体名称，1-256 字符，用于标识和展示 |
| `scene_id` | string | ✅ | — | 所属场景标识（必填），用于数据隔离。检索时强制按 user_id + scene_id 双重过滤 |
| `permissions` | string[] | ❌ | `["read","write"]` | 权限列表，生产阶段启用鉴权后生效 |

**请求示例**

```json
{
  "agent_name": "客服助手",
  "scene_id": "customer_service",
  "permissions": ["read", "write"]
}
```

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `agent_id` | string | 系统自动生成的智能体唯一标识，格式 `agent_xxx` |
| `agent_name` | string | 注册时传入的智能体名称 |
| `api_key` | string | **仅此一次返回明文**，后续所有请求需携带此凭证 |
| `api_key_prefix` | string | 部分遮罩的展示用前缀，如 `mem_bb63****` |
| `scene_id` | string | 注册时传入的场景标识 |
| `is_active` | bool | 注册后默认为 `true` |
| `created_at` | string | 注册时间，ISO 8601 格式 |

**响应示例**

```json
{
  "code": 0,
  "message": "注册成功 — API Key 仅显示一次，请妥善保存",
  "data": {
    "agent_id": "agent_a1b2c3d4e5f6",
    "agent_name": "客服助手",
    "api_key": "mem_bb63ae9b8e65dbfe8f1a2b3c4d5e6f7a8",
    "api_key_prefix": "mem_bb63****",
    "scene_id": "customer_service",
    "is_active": true,
    "created_at": "2026-08-06T10:00:00+00:00"
  }
}
```

**边界**

- DB 仅存储 `api_key` 的 SHA256 哈希，不存明文
- `api_key` 在响应中仅出现本次调用，后续无法从任何接口获取
- `agent_id` 系统自动生成，冲突概率极低（UUID 派生）
- `agent_name` 无唯一性约束，不同智能体可同名
- 丢失 api_key 时需调用 `/agent/{agent_id}/rotate-key` 换新 key

---

<a id="agent-get"></a>

### 2. 查询智能体

根据 `agent_id` 查询单个智能体的注册信息。

**接口**

```
GET /api/v1/agent/{agent_id}
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `agent_id` | string | Path | ✅ | 注册时返回的智能体唯一标识 |

**请求示例**

```
GET /api/v1/agent/agent_a1b2c3d4e5f6
```

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `agent_id` | string | 智能体唯一标识 |
| `agent_name` | string | 智能体名称 |
| `scene_id` | string | 所属场景标识 |
| `api_key_prefix` | string | 部分遮罩的展示用前缀 |
| `is_active` | bool | 是否启用 |
| `permissions` | string[] | 权限列表 |
| `created_at` | string | 注册时间 |
| `updated_at` | string | 最后更新时间 |

**响应示例**

```json
{
  "code": 0,
  "data": {
    "agent_id": "agent_a1b2c3d4e5f6",
    "agent_name": "客服助手",
    "scene_id": "customer_service",
    "api_key_prefix": "mem_bb63****",
    "is_active": true,
    "permissions": ["read", "write"],
    "created_at": "2026-08-06T10:00:00+00:00",
    "updated_at": null
  }
}
```

**边界**

- 不返回 `api_key` 明文（仅注册和轮换时返回）
- `agent_id` 不存在时返回 404 `{"code":-1,"error_code":"NOT_FOUND"}`
- 查询的是路径中指定的智能体，与当前认证身份无关

---

<a id="agent-list"></a>

### 3. 智能体列表

分页查询已注册的全部智能体，支持按场景和状态过滤。

**接口**

```
GET /api/v1/agent?scene_id=xxx&is_active=true&page=1&page_size=20
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|------|------|------|:---:|--------|------|
| `scene_id` | string | Query | ❌ | — | 按场景过滤 |
| `is_active` | bool | Query | ❌ | — | 按启用状态过滤 |
| `page` | int | Query | ❌ | 1 | 页码，从 1 开始 |
| `page_size` | int | Query | ❌ | 20 | 每页条数，范围 1-100 |

**请求示例**

```
GET /api/v1/agent?scene_id=customer_service&is_active=true&page=1&page_size=10
```

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `items` | array | 智能体列表 |
| `items[].agent_id` | string | 智能体唯一标识 |
| `items[].agent_name` | string | 智能体名称 |
| `items[].scene_id` | string | 所属场景 |
| `items[].api_key_prefix` | string | 展示用 key 前缀 |
| `items[].is_active` | bool | 启用状态 |
| `items[].permissions` | string[] | 权限列表 |
| `items[].created_at` | string | 注册时间 |
| `items[].updated_at` | string | 更新时间 |
| `total` | int | 符合条件的总数 |
| `page` | int | 当前页码 |
| `page_size` | int | 每页条数 |

**响应示例**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "agent_id": "agent_a1b2c3d4e5f6",
        "agent_name": "客服助手",
        "scene_id": "customer_service",
        "api_key_prefix": "mem_bb63****",
        "is_active": true,
        "permissions": ["read", "write"],
        "created_at": "2026-08-06T10:00:00+00:00",
        "updated_at": null
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 10
  }
}
```

**边界**

- 不传过滤条件时返回全部智能体
- `page_size` 超过 100 或小于 1 时返回 422
- 空列表返回 `{"items":[],"total":0}`，不报错

---

<a id="agent-update"></a>

### 4. 更新智能体

修改智能体的名称、权限或启用状态。

**接口**

```
PUT /api/v1/agent/{agent_id}
Content-Type: application/json
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `agent_id` | string | Path | ✅ | 智能体唯一标识 |
| `agent_name` | string | Body | ❌ | 新名称，null 表示不修改 |
| `is_active` | bool | Body | ❌ | 启用/停用，null 表示不修改 |
| `permissions` | string[] | Body | ❌ | 新权限列表，null 表示不修改 |
| `extra_meta` | object | Body | ❌ | 扩展元数据 |

**请求示例**

```json
{
  "agent_name": "VIP客服助手",
  "permissions": ["read", "write", "admin"]
}
```

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `agent_id` | string | 被更新的智能体 ID |
| `updated` | bool | 固定 `true` |

```json
{
  "code": 0,
  "message": "更新成功",
  "data": {"agent_id": "agent_a1b2c3d4e5f6", "updated": true}
}
```

**边界**

- 非 null 字段才更新（PATCH 语义，传 null 跳过）
- `agent_id` 和 `api_key` 不可通过此接口修改（后者用 rotate-key）
- agent_id 不存在 → 404
- 当前无权限校验，任意 agent 可更新任意 agent

---

<a id="agent-disable"></a>

### 5. 停用智能体

停用智能体，使其 api_key 立即失效，但数据保留。

**接口**

```
DELETE /api/v1/agent/{agent_id}
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `agent_id` | string | Path | ✅ | 智能体唯一标识 |

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `agent_id` | string | 智能体 ID |
| `is_active` | bool | 固定 `false` |

```json
{
  "code": 0,
  "message": "已停用",
  "data": {"agent_id": "agent_a1b2c3d4e5f6", "is_active": false}
}
```

**边界**

- **软删除**——数据库记录保留，仅 `is_active` 设为 `false`
- 生产阶段（AUTH_ENABLED=true）：`is_active=false` 的智能体调任何接口都返回 401
- 开发阶段（AUTH_ENABLED=false）：停用不生效，所有请求自由通过
- 可通过 `PUT /agent/{agent_id}` 传 `{"is_active":true}` 恢复
- agent_id 不存在 → 404

---

<a id="agent-rotate-key"></a>

### 6. 轮换 API Key

重新生成 api_key，旧 key 立即失效。

**接口**

```
POST /api/v1/agent/{agent_id}/rotate-key
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `agent_id` | string | Path | ✅ | 智能体唯一标识 |

无需 Body。

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `agent_id` | string | 智能体 ID |
| `api_key` | string | **新的 api_key 明文，仅此一次返回** |
| `api_key_prefix` | string | 新 key 的展示用前缀 |

```json
{
  "code": 0,
  "message": "轮换成功 — 新 API Key 仅显示一次，旧 Key 已失效",
  "data": {
    "agent_id": "agent_a1b2c3d4e5f6",
    "api_key": "mem_newkey123456789...",
    "api_key_prefix": "mem_newk****"
  }
}
```

**边界**

- 旧 api_key 的 SHA256 哈希被新值覆盖，**不可恢复**
- agent_name、permissions、scene_id 等其他信息保持不变
- agent_id 不存在 → 404
- 调用时无需提供旧 api_key（开发阶段无鉴权）

---

<a id="write-sync"></a>

### 7. 同步写入记忆

智能体每轮对话后调用，将对话数据或任务过程写入记忆系统。系统内部执行完整 Pipeline（抽取→生成→去重→存储），返回每条记忆的处理结果。

**接口**

```
POST /api/v1/memory/write
Content-Type: application/json
Header: X-API-Key: mem_xxx
```

**入参（通用字段）**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:---:|--------|------|
| `user_id` | string | ✅ | — | 用户唯一标识，1-128 字符，自动转小写 |
| `interaction_type` | string | ❌ | `"dialogue"` | 数据类型：`dialogue` / `session` / `task_process` |
| `scene_id` | string | ❌ | — | 场景标识 |
| `session_id` | string | ✅ | — | 会话标识（必填，记忆按会话归属） |
| `task_id` | string | ❌ | — | 任务标识 |
| `metadata` | object | ❌ | — | 业务扩展元数据，自由 JSON |

**入参（dialogue 对话记录）**

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `messages` | array | ✅ | 对话消息数组，1-100 条 |
| `messages[].role` | string | ✅ | 角色：`user` / `assistant` / `system` / `tool` / `agent` |
| `messages[].content` | string | ✅ | 消息内容，1-50000 字符 |

**入参（session 历史会话）**

与 dialogue 结构相同，核心数据仍是 `messages` 数组，附加元数据标记该段对话的时间与来源。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `interaction_type` | string | ✅ | 固定 `"session"` |
| `messages` | array | ✅ | 历史对话的完整 messages 数组，格式与 dialogue 相同 |
| `session_time` | string | ❌ | 该历史会话发生时间 (ISO 8601) |
| `session_source` | string | ❌ | 会话来源标识，如 `"电话客服"`、`"邮件"`、`"微信"`，≤256 字符 |
| `session_summary` | string | ❌ | 可选的简要摘要，≤10000 字符 |

**入参（task_process 任务过程）**

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `interaction_type` | string | ✅ | 固定 `"task_process"` |
| `task_goal` | string | ❌ | 任务目标，≤2000 字符 |
| `task_progress` | string | ❌ | 任务进展描述，≤5000 字符 |
| `task_result` | string | ❌ | 任务执行结果，≤5000 字符 |

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `mode` | string | 处理路径：`pipeline`（正常）/ `degraded`（降级）/ `mock`（Mock模式） |
| `results` | array | 每条记忆的处理结果 |
| `results[].id` | string | 记忆 ID（`mem_xxx`） |
| `results[].memory` | string | 记忆内容摘要 |
| `results[].event` | string | 处理事件：`ADD` / `MERGE` / `UPDATE` / `SKIP` |

**响应示例**

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "mode": "pipeline",
    "results": [
      {"id": "mem_001", "memory": "用户名为张三，偏好Python后端开发", "event": "ADD"},
      {"id": "mem_002", "memory": "项目 deadline 为下周五", "event": "ADD"}
    ]
  }
}
```

**边界**

- dialogue 类型必须传 `messages` 数组，session/task_process 可为空
- `interaction_type` 不在允许列表中 → 422
- Pipeline 失败时降级为 `degraded` 模式，返回 SKIP
- 写入耗时 5-15 秒（LLM 调用链路）
- 每条 message 的 role 仅限于 `user/assistant/system/tool/agent`

---

### 7.1 对话记录写入示例

**请求**

```json
{
  "user_id": "user_9527",
  "scene_id": "customer_service",
  "session_id": "sess_abc123",
  "interaction_type": "dialogue",
  "messages": [
    {"role": "user", "content": "你好，我之前买的衣服不合适想退货，订单号DH001"},
    {"role": "assistant", "content": "好的，已为您查询到订单DH001，商品为蓝色T恤。请问退货原因是什么？"},
    {"role": "user", "content": "尺寸不合适，想要退款"}
  ]
}
```

**响应**

```json
{
  "code": 0,
  "data": {
    "mode": "pipeline",
    "results": [
      {"id": "mem_abc", "memory": "用户订单DH001需要退货退款，原因为尺寸不合适", "event": "ADD"},
      {"id": "mem_def", "memory": "用户偏好简洁沟通，直达主题", "event": "ADD"}
    ]
  }
}
```

---

### 7.2 历史会话写入示例

将一段在某平台（如电话、邮件、微信）已发生的完整对话导入记忆系统。支持两种写入模式：

**模式一：完整对话记录**（有原始 messages）

```json
{
  "user_id": "user_9527",
  "scene_id": "customer_service",
  "interaction_type": "session",
  "session_time": "2026-08-01T10:30:00Z",
  "session_source": "电话客服",
  "messages": [
    {"role": "user", "content": "你好，我买的衣服不合适，想退货"},
    {"role": "assistant", "content": "好的，请问您的订单号是什么？"},
    {"role": "user", "content": "订单号是DH2024001"},
    {"role": "assistant", "content": "已查到，蓝色T恤对吧？您想退货还是换货？"},
    {"role": "user", "content": "退货，尺寸大了"},
    {"role": "assistant", "content": "已为您提交退货申请，退款将在3个工作日内退回。"}
  ]
}
```

**模式二：仅摘要**（无原始对话，只有总结文本）

```json
{
  "user_id": "user_9527",
  "scene_id": "customer_service",
  "interaction_type": "session",
  "session_time": "2026-08-01T10:30:00Z",
  "session_source": "电话客服",
  "messages": [],
  "session_summary": "用户来电咨询退货流程，确认了收货地址为北京朝阳区，客服承诺3个工作日内退款。用户对处理速度表示满意。"
}
```

**模式三：对话 + 摘要**（双保险，最完整）

```json
{
  "user_id": "user_9527",
  "scene_id": "customer_service",
  "interaction_type": "session",
  "session_time": "2026-08-01T10:30:00Z",
  "session_source": "电话客服",
  "messages": [
    {"role": "user", "content": "我要退货"},
    {"role": "assistant", "content": "订单号？"},
    {"role": "user", "content": "DH001"}
  ],
  "session_summary": "用户通过电话客服咨询退货，订单DH001，已确认收货地址，客服承诺3天退款。"
}
```

LLM 抽取时将 `messages` 逐轮拼接，再追加 `[历史会话摘要]`、`[会话来源]`、`[会话时间]`，统一输入 Pipeline。
```

**响应**

```json
{
  "code": 0,
  "data": {
    "mode": "pipeline",
    "results": [
      {"id": "mem_001", "memory": "用户订单DH2024001申请退货，原因为尺寸不合适", "event": "ADD"},
      {"id": "mem_002", "memory": "用户退款将在3个工作日内到账", "event": "ADD"}
    ]
  }
}
```

---

### 7.3 任务过程写入示例

**请求**

```json
{
  "user_id": "user_9527",
  "scene_id": "customer_service",
  "task_id": "task_refund_001",
  "interaction_type": "task_process",
  "task_goal": "处理用户订单DH001的退款申请",
  "task_progress": "已联系物流确认退货入库，等待仓库质检完成",
  "task_result": ""
}
```

**响应**

```json
{
  "code": 0,
  "data": {
    "mode": "pipeline",
    "results": [
      {"id": "mem_task_001", "memory": "退款任务当前进度：等待仓库质检", "event": "ADD"}
    ]
  }
}
```

---

### 7.4 业务元数据写入示例

**请求**

```json
{
  "user_id": "user_9527",
  "scene_id": "customer_service",
  "interaction_type": "dialogue",
  "messages": [
    {"role": "user", "content": "我的退款怎么还没到账"}
  ],
  "metadata": {
    "order_id": "DH001",
    "order_amount": 299.00,
    "device": "iPhone 15",
    "page_source": "退款详情页",
    "customer_level": "VIP"
  }
}
```

**响应**

```json
{
  "code": 0,
  "data": {
    "mode": "pipeline",
    "results": [
      {"id": "mem_xxx", "memory": "用户查询退款DH001到账进度", "event": "ADD"}
    ]
  }
}
```

`metadata` 不做任何解析，直接存入 T_INTERACTION_RECORD 的 `extra_meta` 列，供后续审计和业务分析使用。

---

<a id="write-async"></a>

### 8. 异步写入记忆

与同步写入功能相同，但即刻返回 request_id，后台异步处理。适用于高并发或不需立即获取记忆结果的场景。

**接口**

```
POST /api/v1/memory/async_write
Content-Type: application/json
Header: X-API-Key: mem_xxx
```

**入参**

与同步写入完全一致（`AsyncWriteRequest` 与 `MemoryWriteRequest` 共用同一字段结构），支持 `dialogue` / `session` / `task_process` / `metadata`。`session_id` 与同步写入一样为**必填**。

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `request_id` | string | 异步任务唯一标识，格式 `async_xxx` |
| `status` | string | 固定 `"accepted"`，表示任务已接收 |

**响应示例**

```json
{
  "code": 0,
  "data": {
    "request_id": "async_a1b2c3d4e5f67890123456",
    "status": "accepted"
  }
}
```

**边界**

- 正常流程：投递 Kafka → Consumer 异步处理 → 落库
- Kafka 不可用时：降级为同步写入（`_fallback_sync_write`），直接写入 T_INTERACTION_RECORD，status 标记为 `pending_extract` 等待后续补处理
- 不返回记忆处理结果，只返回接收确认
- 延迟：同步 5-15s vs 异步即刻返回

---

## 三 会话管理

会话是用户与智能体之间一次连续交互的组织单元。每个会话有独立的生命周期（创建 → 活跃 → 关闭），关联一条或多条记忆。

<a id="session-create"></a>

### 1. 创建会话

用户开始一次新对话时调用。系统从 Header `X-API-Key` 自动识别 Agent 身份（无需显式传 `agent_id`），生成唯一 `session_id`，后续所有写入和检索都绑定此会话。

**接口**

```
POST /api/v1/session
Content-Type: application/json
Header: X-API-Key: mem_xxx
```

**入参**

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `user_id` | string | ✅ | 所属用户标识 |
| `agent_id` | string | ❌ | 所属智能体。不传则从 Header `X-API-Key` 自动识别并关联。最终必定写入 T_SESSION |
| `scene_id` | string | ❌ | 所属场景 |
| `task_id` | string | ❌ | 关联的长周期任务 |
| `extra_meta` | object | ❌ | 扩展元数据 |

**请求示例**

```json
{
  "user_id": "user_9527",
  "agent_id": "agent_xxx",
  "scene_id": "customer_service",
  "task_id": "task_refund_001"
}
```

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 系统生成的会话唯一标识，格式 `sess_xxx` |
| `user_id` | string | 所属用户 |
| `agent_id` | string | 所属智能体 |
| `scene_id` | string | 所属场景 |
| `task_id` | string | 关联任务（可为 null） |
| `status` | string | 固定 `"active"` |
| `started_at` | string | 会话开始时间 (ISO 8601) |

```json
{
  "code": 0,
  "message": "创建成功",
  "data": {
    "session_id": "sess_a1b2c3d4e5f6",
    "user_id": "user_9527",
    "agent_id": "agent_xxx",
    "scene_id": "customer_service",
    "task_id": "task_refund_001",
    "status": "active",
    "started_at": "2026-08-11T10:00:00+00:00"
  }
}
```

**边界**

- `session_id` 系统自动生成，调用方无需自己生成
- `user_id` 自动转小写并去空格
- 创建后 `message_count=0`，每次 write 调用时需调用方自行更新（当前系统不会自动递增）

---

<a id="session-get"></a>

### 2. 查询会话

根据 session_id 查询单个会话的详细信息。

**接口**

```
GET /api/v1/session/{session_id}
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `session_id` | string | Path | ✅ | 会话唯一标识 |

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 会话标识 |
| `user_id` | string | 所属用户 |
| `agent_id` | string | 所属智能体 |
| `scene_id` | string | 所属场景 |
| `task_id` | string | 关联任务 |
| `status` | string | `active` / `closed` |
| `message_count` | int | 已记录的消息数量 |
| `started_at` | string | 开始时间 |
| `ended_at` | string | 结束时间（未关闭为 null） |

```json
{
  "code": 0,
  "data": {
    "session_id": "sess_a1b2c3d4e5f6",
    "user_id": "user_9527",
    "agent_id": "agent_xxx",
    "scene_id": "customer_service",
    "task_id": null,
    "status": "active",
    "message_count": 12,
    "started_at": "2026-08-11T10:00:00+00:00",
    "ended_at": null
  }
}
```

**边界**

- session_id 不存在 → 404
- 不会返回关联的记忆内容，只返回会话元数据

---

<a id="session-list"></a>

### 3. 会话列表

分页查询会话，支持按用户、智能体、状态、场景过滤。

**接口**

```
GET /api/v1/session?user_id=xxx&agent_id=agent_xxx&status=active&scene_id=xxx&page=1&page_size=20
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|------|------|------|:---:|--------|------|
| `user_id` | string | Query | ❌ | — | 按用户过滤 |
| `agent_id` | string | Query | ❌ | — | **按智能体过滤**，可查某个 Agent 下的全部会话 |
| `status` | string | Query | ❌ | — | 按状态过滤：`active` / `closed` |
| `scene_id` | string | Query | ❌ | — | 按场景过滤 |
| `page` | int | Query | ❌ | 1 | 页码 |
| `page_size` | int | Query | ❌ | 20 | 每页条数，1-100 |

**响应**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "session_id": "sess_xxx",
        "user_id": "user_9527",
        "status": "active",
        "message_count": 12,
        "started_at": "2026-08-11T10:00:00+00:00",
        "ended_at": null
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

**边界**

- 不传过滤条件返回全部会话
- 空列表返回 `{"items":[],"total":0}`
- 按 `started_at` 降序排列

---

<a id="session-update"></a>

### 4. 更新会话

修改会话状态或关联任务。

**接口**

```
PUT /api/v1/session/{session_id}
Content-Type: application/json
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `session_id` | string | Path | ✅ | 会话标识 |
| `status` | string | Body | ❌ | 新状态，null 不修改 |
| `task_id` | string | Body | ❌ | 关联任务，null 不修改 |
| `extra_meta` | object | Body | ❌ | 扩展元数据 |

```json
{
  "task_id": "task_refund_001"
}
```

```json
{
  "code": 0,
  "message": "更新成功",
  "data": {"session_id": "sess_xxx", "updated": true}
}
```

**边界**

- null 字段不修改
- session_id 不存在 → 404

---

<a id="session-close"></a>

### 5. 关闭会话

用户结束对话时调用。关闭即压缩：task_state / process / correction 三类过程性记忆自动 LLM 压缩为摘要 → 旧碎片 expired → 新摘要入库。preference / fact 保持原样不动。

**接口**

```
POST /api/v1/session/{session_id}/close
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `session_id` | string | Path | ✅ | 会话标识 |

无需 Body。

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 会话标识 |
| `status` | string | 固定 `"closed"` |
| `total_memory_count` | int | 该会话活跃记忆总数 |
| `kept_count` | int | 保留不变的记忆数（preference / fact） |
| `compressed_count` | int | 被压缩为摘要的记忆数（task_state / process / correction） |
| `summary_text` | string | LLM 生成的压缩摘要文本 |
| `ended_at` | string | 结束时间 |

```json
{
  "code": 0,
  "message": "关闭成功",
  "data": {
    "session_id": "sess_xxx",
    "status": "closed",
    "total_memory_count": 12,
    "kept_count": 3,
    "compressed_count": 9,
    "summary_text": "本次会话讨论了系统架构设计，确认了技术栈方案...",
    "ended_at": "2026-08-11T11:00:00+00:00"
  }
}
```

**边界**

- session_id 不存在 → 404
- 重复关闭：`status` 已为 `closed` 时仍可调用，不会报错，`ended_at` 更新为最新时间
- 无条件压缩：不再需要消息数阈值，关闭即执行
- 压缩的记忆会删除 T_MEMORY_VECTOR 和 Qdrant 向量，新摘要重新入库

---

## 四 场景管理

场景（Scene）是记忆数据隔离的第二维度。不同业务应用（如客服、物流、运维）通过不同 scene_id 隔离各自的记忆，避免数据混淆。

<a id="scene-create"></a>

### 1. 创建场景

注册一个新的业务场景。

**接口**

```
POST /api/v1/scene
Content-Type: application/json
```

**入参**

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `scene_name` | string | ✅ | 场景名称，1-256 字符，如 `"客服助手"` |
| `description` | string | ❌ | 场景描述，如 `"处理用户咨询、投诉、退款"` |
| `extra_meta` | object | ❌ | 扩展元数据 |

**请求示例**

```json
{
  "scene_name": "客服助手",
  "description": "处理用户咨询、投诉与退款流程"
}
```

**响应**

```json
{
  "code": 0,
  "message": "创建成功",
  "data": {
    "scene_id": "scene_a1b2c3d4",
    "scene_name": "客服助手",
    "description": "处理用户咨询、投诉与退款流程",
    "is_active": true,
    "created_at": "2026-08-11T10:00:00+00:00"
  }
}
```

**边界**

- `scene_id` 系统自动生成，格式 `scene_xxx`
- `scene_name` 无唯一性约束，但建议不同场景用不同名称以便区分
- 创建后默认 `is_active=true`

---

<a id="scene-get"></a>

### 2. 查询场景

根据 scene_id 查询单个场景信息。

**接口**

```
GET /api/v1/scene/{scene_id}
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `scene_id` | string | Path | ✅ | 场景唯一标识 |

**响应**

```json
{
  "code": 0,
  "data": {
    "scene_id": "scene_a1b2c3d4",
    "scene_name": "客服助手",
    "description": "处理用户咨询、投诉与退款流程",
    "is_active": true,
    "created_at": "2026-08-11T10:00:00+00:00",
    "updated_at": null
  }
}
```

**边界**

- scene_id 不存在 → 404

---

<a id="scene-list"></a>

### 3. 场景列表

分页查询所有场景，可按启用状态过滤。

**接口**

```
GET /api/v1/scene?is_active=true&page=1&page_size=20
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|------|------|------|:---:|--------|------|
| `is_active` | bool | Query | ❌ | — | 按启用状态过滤：`true` / `false` |
| `page` | int | Query | ❌ | 1 | 页码 |
| `page_size` | int | Query | ❌ | 20 | 每页条数，1-100 |

**响应**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "scene_id": "scene_xxx",
        "scene_name": "客服助手",
        "description": "...",
        "is_active": true,
        "created_at": "2026-08-11T10:00:00+00:00",
        "updated_at": null
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

**边界**

- 不传过滤条件返回全部场景
- 空列表返回 `{"items":[],"total":0}`

---

<a id="scene-update"></a>

### 4. 更新场景

修改场景的名称、描述或启用状态。

**接口**

```
PUT /api/v1/scene/{scene_id}
Content-Type: application/json
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `scene_id` | string | Path | ✅ | 场景标识 |
| `scene_name` | string | Body | ❌ | 新名称，null 不修改 |
| `description` | string | Body | ❌ | 新描述，null 不修改 |
| `is_active` | bool | Body | ❌ | 启用/停用，null 不修改 |
| `extra_meta` | object | Body | ❌ | 扩展元数据 |

```json
{
  "description": "处理用户咨询、投诉、退款及订单物流问题"
}
```

```json
{
  "code": 0,
  "message": "更新成功",
  "data": {"scene_id": "scene_xxx", "updated": true}
}
```

**边界**

- null 字段不修改
- scene_id 不存在 → 404
- 停用场景（`is_active=false`）后，该场景下的记忆仍可从 PG 查询，但认证层可配置拦截

---

<a id="scene-disable"></a>

### 5. 停用场景

软删除场景，数据保留但标记为不可用。

**接口**

```
DELETE /api/v1/scene/{scene_id}
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `scene_id` | string | Path | ✅ | 场景标识 |

```json
{
  "code": 0,
  "message": "已停用",
  "data": {"scene_id": "scene_xxx", "is_active": false}
}
```

**边界**

- **软删除**——数据库记录保留，仅 `is_active` 设为 `false`
- 可通过 `PUT /scene/{scene_id}` 传 `{"is_active":true}` 恢复
- scene_id 不存在 → 404

---

## 五 任务管理

任务（Task）是跨会话的长周期工作单元。一个任务可关联多个会话，通过渐进式进展更新追踪"目标→过程→结果"的完整链路。

<a id="task-create"></a>

### 1. 创建任务

用户开启一个明确的长周期目标时调用，系统生成唯一 task_id。

**接口**

```
POST /api/v1/task
Content-Type: application/json
```

**入参**

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `user_id` | string | ✅ | 所属用户标识 |
| `title` | string | ❌ | 任务标题，≤512 字符，如 `"处理用户退款"` |
| `goal` | string | ❌ | 任务目标描述 |
| `agent_id` | string | ❌ | 所属智能体，不传从 X-API-Key 自动关联 |
| `scene_id` | string | ❌ | 所属场景 |
| `session_id` | string | ❌ | 关联的初始会话 |
| `extra_meta` | object | ❌ | 扩展元数据 |

**请求示例**

```json
{
  "user_id": "user_9527",
  "title": "处理订单DH001退款",
  "goal": "完成用户订单DH001的退货退款全流程，包括物流核实、质检、退款到账",
  "scene_id": "customer_service"
}
```

**响应**

```json
{
  "code": 0,
  "message": "创建成功",
  "data": {
    "task_id": "task_a1b2c3d4",
    "user_id": "user_9527",
    "title": "处理订单DH001退款",
    "goal": "完成用户订单DH001的退货退款全流程",
    "status": "pending",
    "started_at": "2026-08-11T10:00:00+00:00"
  }
}
```

**边界**

- `task_id` 系统自动生成，格式 `task_xxx`
- 创建后默认状态 `pending`
- `agent_id` 不传则从 X-API-Key 自动识别

---

<a id="task-get"></a>

### 2. 查询任务

根据 task_id 查询单个任务的完整信息。

**接口**

```
GET /api/v1/task/{task_id}
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `task_id` | string | Path | ✅ | 任务唯一标识 |

**响应**

```json
{
  "code": 0,
  "data": {
    "task_id": "task_a1b2c3d4",
    "user_id": "user_9527",
    "agent_id": "agent_xxx",
    "scene_id": "customer_service",
    "session_id": null,
    "title": "处理订单DH001退款",
    "goal": "完成用户订单DH001的退货退款全流程",
    "status": "in_progress",
    "progress": "已联系物流确认退货入库，等待仓库质检",
    "completed_items": ["确认订单DH001属于可退换商品", "用户确认退货原因为尺寸不合适"],
    "pending_items": ["仓库质检完成", "退款到账确认"],
    "started_at": "2026-08-11T10:00:00+00:00",
    "ended_at": null
  }
}
```

**边界**

- task_id 不存在 → 404

---

<a id="task-list"></a>

### 3. 任务列表

分页查询任务，支持按用户、状态、会话过滤。

**接口**

```
GET /api/v1/task?user_id=xxx&status=in_progress&session_id=xxx&page=1&page_size=20
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|------|------|------|:---:|--------|------|
| `user_id` | string | Query | ❌ | — | 按用户过滤 |
| `status` | string | Query | ❌ | — | 按状态过滤：`pending` / `in_progress` / `completed` / `cancelled` |
| `session_id` | string | Query | ❌ | — | 按会话过滤 |
| `page` | int | Query | ❌ | 1 | 页码 |
| `page_size` | int | Query | ❌ | 20 | 每页条数，1-100 |

**响应**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "task_id": "task_xxx",
        "user_id": "user_9527",
        "title": "处理订单DH001退款",
        "goal": "...",
        "status": "in_progress",
        "progress": "已联系物流",
        "completed_items": ["确认可退换"],
        "pending_items": ["质检", "退款到账"],
        "started_at": "2026-08-11T10:00:00+00:00",
        "ended_at": null
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

**边界**

- 不传过滤条件返回全部任务
- 空列表返回 `{"items":[],"total":0}`

---

<a id="task-update"></a>

### 4. 更新任务进展

每轮对话后可调用，更新任务状态、进展描述、完成/待办清单。

**接口**

```
PUT /api/v1/task/{task_id}
Content-Type: application/json
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `task_id` | string | Path | ✅ | 任务标识 |
| `title` | string | Body | ❌ | 新标题，null 不修改 |
| `goal` | string | Body | ❌ | 新目标，null 不修改 |
| `status` | string | Body | ❌ | 状态：`pending` / `in_progress` / `completed` / `cancelled` |
| `progress` | string | Body | ❌ | 当前进展描述文本 |
| `completed_items` | string[] | Body | ❌ | 已完成事项清单 |
| `pending_items` | string[] | Body | ❌ | 待处理事项清单 |
| `extra_meta` | object | Body | ❌ | 扩展元数据 |

**状态转换规则**

```
pending      → in_progress, completed, cancelled
in_progress  → completed, cancelled, pending
completed    → in_progress, cancelled
cancelled    → pending
```

**请求示例**

```json
{
  "status": "in_progress",
  "progress": "已联系物流确认退货入库，等待仓库质检结果",
  "completed_items": ["确认订单DH001属于可退换商品"],
  "pending_items": ["仓库质检完成", "退款到账确认"]
}
```

**响应**

```json
{
  "code": 0,
  "message": "更新成功",
  "data": {"task_id": "task_xxx", "updated": true, "status": "in_progress"}
}
```

**边界**

- 不合法状态转换（如 `completed` → `pending`）→ 409 ConflictError
- task_id 不存在 → 404
- null 字段不修改
- 状态设为 `completed` 时自动记录 `ended_at`

---

<a id="task-progress"></a>

### 5. 任务进展摘要

查询任务的完成度统计和关联记忆数量。

**接口**

```
GET /api/v1/task/{task_id}/progress
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `task_id` | string | Path | ✅ | 任务标识 |

**响应**

```json
{
  "code": 0,
  "data": {
    "task_id": "task_xxx",
    "status": "in_progress",
    "progress": "已联系物流确认退货入库",
    "completed_count": 1,
    "pending_count": 2,
    "related_memory_count": 5,
    "last_activity": "2026-08-11T10:30:00+00:00"
  }
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `completed_count` | int | 已完成事项数 |
| `pending_count` | int | 待处理事项数 |
| `related_memory_count` | int | 该任务相关的活跃记忆数（`WHERE task_id=xxx AND status='active'`） |
| `last_activity` | string | 最近活动时间 |

**边界**

- task_id 不存在 → 404

---

<a id="task-complete"></a>

### 6. 完成任务

标记任务为已完成，记录结束时间。

**接口**

```
POST /api/v1/task/{task_id}/complete
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `task_id` | string | Path | ✅ | 任务标识 |

无需 Body。

**响应**

```json
{
  "code": 0,
  "message": "任务已完成",
  "data": {
    "task_id": "task_xxx",
    "status": "completed",
    "ended_at": "2026-08-11T11:00:00+00:00"
  }
}
```

**边界**

- task_id 不存在 → 404
- 完成后仍可通过 `PUT /task/{id}` 重新打开（`status: "in_progress"`）
- 当前不自动触发记忆归档（待后续版本）

---

## 六 记忆管理

以下接口用于记忆的查询、更新和删除。面向"通用记忆建模与多层记忆管理"功能。

<a id="mem-list"></a>

### 1. 列出全部记忆

分页查询指定用户的全部记忆，支持按场景、任务、会话、层级过滤。供管理后台或调试使用，区别于 `search` 的语义检索。

**接口**

```
GET /api/v1/memory/list?user_id=xxx&scene_id=xxx&task_id=xxx&session_id=xxx&page=1&page_size=20
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|------|------|------|:---:|--------|------|
| `user_id` | string | Query | ✅ | — | 用户标识 |
| `scene_id` | string | Query | ❌ | — | 按场景过滤 |
| `task_id` | string | Query | ❌ | — | 按任务过滤 |
| `session_id` | string | Query | ❌ | — | 按会话过滤 |
| `memory_scope` | string | Query | ❌ | — | 按层级过滤：`user` / `session` / `task` / `agent` |
| `page` | int | Query | ❌ | 1 | 页码 |
| `page_size` | int | Query | ❌ | 20 | 每页条数，1-100 |

**响应**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "memory_id": "mem_001",
        "content": "用户偏好简洁沟通",
        "memory_type": "preference",
        "status": "active",
        "importance": 0.8,
        "confidence": 0.9,
        "scene_id": "customer_service",
        "session_id": null,
        "task_id": null,
        "memory_scope": "user",
        "created_at": "2026-08-11T10:00:00+00:00"
      }
    ],
    "total": 15,
    "page": 1,
    "page_size": 20
  }
}
```

**边界**

- 严格按 `user_id` 过滤，不跨用户
- 默认只查 `status='active'`
- 空结果返回 `{"items":[],"total":0}`
- 区别于 `search`：此接口走 PG 直查，无相关性排序

---

<a id="mem-update"></a>

### 2. 更新记忆

修改单条记忆的内容、重要性、标签或状态。

**接口**

```
PUT /api/v1/memory/update
Content-Type: application/json
```

**入参**

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `memory_id` | string | ✅ | 记忆唯一标识 |
| `content` | string | ❌ | 新内容，null 不修改 |
| `summary` | string | ❌ | 新摘要，null 不修改 |
| `status` | string | ❌ | 新状态：`active` / `deleted` / `expired` |
| `importance` | float | ❌ | 重要性 0-1，null 不修改 |
| `confidence` | float | ❌ | 置信度 0-1，null 不修改 |
| `tags` | string[] | ❌ | 新标签列表，null 不修改 |

**请求示例**

```json
{
  "memory_id": "mem_001",
  "importance": 0.9,
  "tags": ["偏好", "代码风格"]
}
```

**响应**

```json
{
  "code": 0,
  "data": {
    "memory_id": "mem_001",
    "updated": true,
    "version": 2
  }
}
```

**边界**

- memory_id 不存在 → 无报错，`updated: false, version: 0`
- null 字段不修改
- 更新后 `version` 自增

---

<a id="mem-delete"></a>

### 3. 删除记忆（软删除）

将单条记忆标记为已删除，同时从 Qdrant 移除向量使其不再参与检索。PG 记录保留供审计。

**接口**

```
DELETE /api/v1/memory/delete
Content-Type: application/json
```

**入参**

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `memory_id` | string | ✅ | 记忆唯一标识 |
| `reason` | string | ❌ | 删除原因，供审计使用 |

**请求示例**

```json
{
  "memory_id": "mem_001",
  "reason": "用户要求删除个人信息"
}
```

**响应**

```json
{
  "code": 0,
  "data": {
    "memory_id": "mem_001",
    "deleted": true,
    "previous_status": "active"
  }
}
```

**边界**

- **软删除**：`status→deleted`，记录保留
- Qdrant 向量同步移除，不再参与检索
- memory_id 不存在 → `deleted: false`
- 已 deleted 的记忆再次调用 → 无变化，返回 `previous_status: "deleted"`

---

<a id="mem-delete-all"></a>

### 4. 清除全部记忆

清除指定用户的全部记忆（PG + Qdrant 双清）。适用于"忘记我的一切"场景。

**接口**

```
POST /api/v1/memory/delete-all?user_id=xxx&scene_id=xxx
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `user_id` | string | Query | ✅ | 用户标识 |
| `scene_id` | string | Query | ❌ | 仅清除指定场景的记忆，不传则清除全部 |

**响应**

```json
{
  "code": 0,
  "data": {
    "message": "成功删除 42 条记忆",
    "deleted_count": 42
  }
}
```

**边界**

- 操作不可逆（软删除，PG 记录保留但不可恢复）
- Qdrant 向量同步清除
- scene_id 可选，限定清除范围

---

<a id="mem-stats"></a>

### 5. 记忆层级分布统计

按 memory_scope 统计用户在四个层级（user/session/task/agent）的记忆分布。

**接口**

```
GET /api/v1/memory/stats?user_id=xxx&scene_id=xxx
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `user_id` | string | Query | ✅ | 用户标识 |
| `scene_id` | string | Query | ❌ | 按场景过滤 |

**响应**

```json
{
  "code": 0,
  "data": {
    "total": 120,
    "level_distribution": [
      {"level": "user", "count": 45, "ratio": 0.375},
      {"level": "session", "count": 30, "ratio": 0.25},
      {"level": "task", "count": 25, "ratio": 0.208},
      {"level": "agent", "count": 20, "ratio": 0.167}
    ],
    "generated_at": "2026-08-11T10:00:00+00:00",
    "classification_version": "memory_scope_v1"
  }
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `total` | int | 该用户活跃记忆总数 |
| `level_distribution[].level` | string | 层级：`user` / `session` / `task` / `agent` |
| `level_distribution[].count` | int | 该层级的记忆数量 |
| `level_distribution[].ratio` | float | 占总数的比例 |
| `classification_version` | string | 分类版本标识 |

**边界**

- 仅统计 `status='active'` 的记忆
- scene_id 可选，限定统计范围

---

## 七 多信号融合检索

多信号融合检索是记忆系统的核心调用接口。一轮调用内部执行：语义向量检索（Qdrant）+ BM25 关键词检索（PG）+ 元数据预过滤 → T_MEMORY_VECTOR 桥接 → T_MEMORY 取权威数据 → 五维加权重排。

<a id="search"></a>

### 1. 语义检索记忆

**接口**

```
POST /api/v1/memory/search
Content-Type: application/json
Header: X-API-Key: mem_xxx, X-User-Id: xxx
```

**入参**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:---:|--------|------|
| `query` | string | ✅ | — | 检索查询文本（通常为用户当前问题） |
| `user_id` | string | ✅ | — | 用户标识，检索范围限定在该用户下 |
| `scene_id` | string | ❌ | — | 按场景过滤 |
| `task_id` | string | ❌ | — | 按任务过滤 |
| `session_id` | string | ❌ | — | 按会话过滤 |
| `memory_types` | string[] | ❌ | — | 筛选类型：`fact` / `preference` / `task_state` / `process` / `correction` |
| `status` | string[] | ❌ | — | 按状态过滤，默认只查 `active` |
| `top_k` | int | ❌ | 10 | 返回几条，最大 50 |
| `time_start` | string | ❌ | — | 时间范围起点 (ISO 8601) |
| `time_end` | string | ❌ | — | 时间范围终点 (ISO 8601) |
| `rerank` | bool | ❌ | false | 是否启用 Reranker 二次排序 |
| `max_content_length` | int | ❌ | — | 内容最大字符数，超出截断 |

**请求示例**

```json
{
  "query": "退货退款流程",
  "user_id": "user_9527",
  "memory_types": ["fact", "task_state"],
  "top_k": 5
}
```

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `results` | array | 候选记忆列表，按 relevance_score 降序 |
| `results[].memory_id` | string | 记忆标识 |
| `results[].content` | string | 记忆内容 |
| `results[].summary` | string | 记忆摘要 |
| `results[].memory_type` | string | 记忆类型 |
| `results[].scene_id` | string | 所属场景 |
| `results[].task_id` | string | 关联任务 |
| `results[].session_id` | string | 所属会话 |
| `results[].status` | string | 记忆状态 |
| `results[].importance` | float | 重要性 |
| `results[].confidence` | float | 置信度 |
| `results[].relevance_score` | float | **综合相关性分数**（五维加权） |
| `total_candidates` | int | Qdrant 召回的候选总数 |
| `elapsed_ms` | int | 检索耗时（毫秒） |

**响应示例**

```json
{
  "code": 0,
  "data": {
    "query": "退货退款流程",
    "results": [
      {
        "memory_id": "mem_001",
        "content": "用户订单DH001需要退货退款",
        "memory_type": "fact",
        "relevance_score": 0.85,
        "importance": 0.8,
        "confidence": 0.9,
        "scene_id": "customer_service",
        "task_id": "task_refund_001",
        "session_id": "sess_chat_001",
        "status": "active"
      }
    ],
    "total_candidates": 30,
    "elapsed_ms": 253
  }
}
```

**边界**

- 检索严格限定 `user_id`，不跨用户
- Qdrant payload 仅 4 字段（user_id / scene_id / task_id / session_id），memory_type/status 在后过滤完成
- 默认只返回 `status='active'` 的记忆
- Qdrant 不可用时降级为 PG 关键词检索
- `relevance_score` 计算公式：`mem0_score×0.6 + recency×0.15 + importance×0.15 + confidence×0.1`

---

<a id="context"></a>

### 2. 检索 + 上下文装配

在检索结果基础上按记忆类型分组、容量预算内逐条装配，返回可直接注入 LLM Prompt 的纯文本。

**接口**

```
POST /api/v1/memory/context
Content-Type: application/json
Header: X-API-Key: mem_xxx, X-User-Id: xxx
```

**入参**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:---:|--------|------|
| `query` | string | ✅ | — | 当前用户问题 |
| `user_id` | string | ✅ | — | 用户标识 |
| `scene_id` | string | ❌ | — | 按场景过滤 |
| `task_id` | string | ❌ | — | 按任务过滤 |
| `session_id` | string | ❌ | — | 按会话过滤 |
| `max_tokens` | int | ❌ | 3000 | 上下文容量预算，超出时停止装配 |
| `top_k` | int | ❌ | 10 | 检索返回的候选数量 |
| `memory_types` | string[] | ❌ | — | 筛选类型 |
| `group_by_type` | bool | ❌ | true | 是否按记忆类型分组 |

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `formatted_text` | string | 拼接好的纯文本，可直接注入 System Prompt |
| `memory_count` | int | 实际纳入的记忆条数 |
| `estimated_tokens` | int | 估算 token 数 |

**响应示例**

```json
{
  "code": 0,
  "data": {
    "formatted_text": "## Key Facts\n- 用户订单DH001需要退货退款\n- 退款将在3个工作日内到账\n## User Preferences\n- 用户偏好简洁沟通",
    "memory_count": 3,
    "estimated_tokens": 45
  }
}
```

**边界**

- score < 0.5 的低相关记忆自动丢弃
- `correction` 类型记忆不参与上下文装配
- 单条 content > 200 字符时自动用 summary 替代
- 最大 10 条记忆 / max_tokens 限制，任一触及即停止
- query 与所有记忆都不匹配时返回空文本，不会"指鹿为马"

---

<a id="search-update"></a>

### 3. 更新记忆

修改单条记忆的内容、重要性、标签或状态。

**接口**

```
PUT /api/v1/memory/update
Content-Type: application/json
Header: X-API-Key: mem_xxx
```

**入参**

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `memory_id` | string | ✅ | 记忆唯一标识 |
| `content` | string | ❌ | 新内容，null 不修改 |
| `summary` | string | ❌ | 新摘要，null 不修改 |
| `status` | string | ❌ | 新状态：`active` / `deleted` / `expired` |
| `importance` | float | ❌ | 重要性 0-1 |
| `confidence` | float | ❌ | 置信度 0-1 |
| `tags` | string[] | ❌ | 新标签列表 |

**请求示例**

```json
{
  "memory_id": "mem_001",
  "importance": 0.9,
  "tags": ["偏好", "代码风格"]
}
```

**响应**

```json
{
  "code": 0,
  "data": {"memory_id": "mem_001", "updated": true, "version": 2}
}
```

**边界**

- memory_id 不存在 → `updated: false`
- null 字段不修改，更新后 version 自增

---

<a id="profile"></a>

### 4. 用户画像报告

聚合该用户全部 `preference` + `fact` 类型记忆，交由 LLM 生成结构化画像和文本总结。不走语义检索，直接 PG 全量查询，跨场景聚合。

**接口**

```
POST /api/v1/memory/profile
Content-Type: application/json
Header: X-API-Key: mem_xxx
```

**入参**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:---:|--------|------|
| `user_id` | string | ✅ | — | 用户标识 |
| `max_memories` | int | ❌ | 50 | 最多加载的偏好+事实记忆数 |

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `profile` | object | 结构化画像字段 |
| `profile.preferences` | string[] | 用户偏好 |
| `profile.business_focus` | string[] | 业务关注方向 |
| `profile.communication_style` | string[] | 沟通风格 |
| `profile.decision_habits` | string[] | 决策习惯 |
| `profile.project_background` | string[] | 项目背景 |
| `profile.personalization` | string[] | 个性化要求 |
| `summary` | string | LLM 生成的文本总结 |
| `memory_count` | int | 参与画像生成的记忆总数 |

**响应示例**

```json
{
  "code": 0,
  "data": {
    "profile": {
      "preferences": ["简洁代码", "高性能架构"],
      "business_focus": ["交付时效", "代码质量"],
      "communication_style": ["简洁直接"],
      "decision_habits": ["技术选型偏保守"],
      "project_background": ["长期使用Go语言", "开发企业OA系统"],
      "personalization": ["希望快速响应", "在意退款时效"]
    },
    "summary": "该用户是一名Go后端开发工程师，已有8年经验。偏好简洁沟通，技术选型保守倾向成熟方案。当前在开发OA系统，关注交付时效和退款处理速度。",
    "memory_count": 25
  }
}
```

**边界**

- 无偏好/事实记忆时返回空 `profile` 和 `summary`
- LLM 返回非 JSON 格式时降级为纯文本 summary
- 按 importance 降序，取前 max_memories 条

---

## 八 管理后台

管理后台接口面向系统管理员，用于审计、监控和数据维护。

<a id="admin-memories"></a>

### 1. 分页查询全部记忆

跨用户查询所有记忆，支持按 user_id / type / status 过滤。

**接口**

```
GET /api/v1/admin/memories?user_id=xxx&memory_type=fact&status=active&page=1&page_size=20
Header: X-API-Key: mem_xxx（需要 admin 权限）
```

**响应**

```json
{
  "code": 0,
  "data": {
    "items": [{"memory_id":"mem_001","content":"...","memory_type":"fact","status":"active","user_id":"user_9527"}],
    "total": 150,
    "page": 1,
    "page_size": 20
  }
}
```

---

<a id="admin-memory-detail"></a>

### 2. 记忆详情（含关系链路）

查询单条记忆的完整信息及其关联的记忆关系（补充/冲突/替代/继承）。

**接口**

```
GET /api/v1/admin/memories/{memory_id}
Header: X-API-Key: mem_xxx（需要 admin 权限）
```

**响应**

```json
{
  "code": 0,
  "data": {
    "memory_id": "mem_001",
    "content": "...",
    "relations": [
      {"relation_type": "conflicts_with", "target_memory_id": "mem_002"}
    ]
  }
}
```

**边界**

- memory_id 不存在 → 404

---

<a id="admin-retrieval-logs"></a>

### 3. 检索请求日志

查询指定时间窗口内的检索请求记录。

**接口**

```
GET /api/v1/admin/retrieval-logs?agent_id=xxx&hours=24&page=1&page_size=20
Header: X-API-Key: mem_xxx（需要 admin 权限）
```

| 参数 | 说明 |
|------|------|
| `agent_id` | 按智能体过滤 |
| `hours` | 时间窗口，1-720 小时，默认 24 |

**响应**

```json
{
  "code": 0,
  "data": {
    "items": [{"request_id":"...","agent_id":"...","user_id":"...","query_text":"退货","top_k":5,"created_at":"..."}],
    "total": 42,
    "page": 1,
    "page_size": 20
  }
}
```

---

<a id="admin-stats"></a>

### 4. 系统统计概览

返回系统级别的统计信息。

**接口**

```
GET /api/v1/admin/stats
Header: X-API-Key: mem_xxx（需要 admin 权限）
```

---

<a id="admin-dashboard"></a>

### 5. 系统总览 Dashboard

返回 Dashboard 聚合数据：摘要、对比、记忆趋势、类型分布。

**接口**

```
GET /api/v1/admin/dashboard?hours=24&trend_days=7
Header: X-API-Key: mem_xxx（需要 admin 权限）
```

| 参数 | 说明 |
|------|------|
| `hours` | 统计窗口，1-168 小时，默认 24 |
| `trend_days` | 按日趋势天数，1-90，默认 7 |

**边界**

- hours 或 trend_days 超范围 → 400

---

<a id="admin-api-logs"></a>

### 6. 接口调用日志

查询指定时间窗口内的 API 调用日志。

**接口**

```
GET /api/v1/admin/api-logs?api_path=/api/v1/memory/write&hours=24&page=1&page_size=20
Header: X-API-Key: mem_xxx（需要 admin 权限）
```

| 参数 | 说明 |
|------|------|
| `api_path` | 按接口路径过滤 |
| `error_code` | 按错误码过滤 |
| `hours` | 时间窗口，1-720 小时，默认 24 |

**边界**

- 最多查询 720 小时（30 天）内的日志

---

## 九 记忆生成工具

面向调试和批量导入场景，提供独立的记忆生成和压缩接口。这些接口不同于 `/memory/write`（后者走完整 Pipeline 含校验+原始记录入库），直接输入文本即可产出记忆，适合非交互式的文本处理。

<a id="gen-sync"></a>

### 1. 从文本生成结构化记忆（同步）

输入一段文本，执行完整 Pipeline（抽取→生成→去重→存储），返回生成的记忆列表和去重统计。

**接口**

```
POST /api/v1/memory/generate
Content-Type: application/json
```

**入参**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:---:|--------|------|
| `text` | string | ✅ | — | 输入文本（对话记录、任务描述等），1-10000 字符 |
| `user_id` | string | ✅ | — | 用户唯一标识 |
| `agent_id` | string | ❌ | — | 智能体标识 |
| `scene_id` | string | ❌ | — | 场景标识 |
| `session_id` | string | ❌ | — | 会话标识 |
| `task_id` | string | ❌ | — | 任务标识 |
| `extraction_types` | string[] | ❌ | 全部 6 种 | 抽取类型：`key_fact` / `task_state` / `decision` / `preference` / `process` / `feedback` |
| `source_record_ids` | string[] | ❌ | — | 来源记录 ID，用于追溯 |
| `metadata` | object | ❌ | — | 业务扩展元数据 |

**请求示例**

```json
{
  "text": "用户说他喜欢用 Python 开发，项目 deadline 是下周五，我们决定用 FastAPI 框架",
  "user_id": "user_001",
  "scene_id": "chat",
  "extraction_types": ["key_fact", "task_state", "preference"]
}
```

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `memory_ids` | string[] | 本次生成的记忆 ID 列表 |
| `new_count` | int | 新增数量 |
| `merged_count` | int | 合并到已有记忆的数量 |
| `discarded_count` | int | 因重复被丢弃的数量 |
| `updated_count` | int | 更新已有记忆的数量 |
| `conflict_count` | int | 标记冲突的数量（已废弃，恒为 0） |
| `details[]` | array | 每条记忆的处理详情 |
| `details[].action` | string | 处理动作：`keep_new` / `merge` / `discard` / `update_existing` |
| `details[].memory_id` | string | 记忆 ID |
| `details[].content_preview` | string | 内容预览（前 100 字） |
| `details[].memory_type` | string | 记忆类型 |
| `details[].importance` | float | 重要性 0-1 |
| `details[].confidence` | float | 置信度 0-1 |
| `details[].message` | string | 处理说明 |

**响应示例**

```json
{
  "code": 0,
  "data": {
    "memory_ids": ["mem_001", "mem_002"],
    "new_count": 2,
    "merged_count": 0,
    "discarded_count": 1,
    "updated_count": 0,
    "conflict_count": 0,
    "details": [
      {
        "action": "keep_new",
        "memory_id": "mem_001",
        "content_preview": "用户偏好 Python 开发",
        "memory_type": "preference",
        "importance": 0.8,
        "confidence": 0.9,
        "message": "新记忆已创建"
      }
    ]
  }
}
```

**边界**

- text 为空或超过 10000 字符 → 422
- extraction_types 不在允许列表中 → 422
- Pipeline 执行失败 → 500
- 耗时 5-15 秒（同步阻塞）

---

<a id="gen-batch"></a>

### 2. 批量生成记忆

一次处理多条文本，每条独立走完整 Pipeline。适用于批量导入历史数据。

**接口**

```
POST /api/v1/memory/generate/batch
Content-Type: application/json
```

**入参**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:---:|--------|------|
| `texts` | string[] | ✅ | — | 文本数组，1-50 条 |
| `user_id` | string | ✅ | — | 用户标识（所有文本共用） |
| `agent_id` | string | ❌ | — | 智能体标识 |
| `scene_id` | string | ❌ | — | 场景标识（所有文本共用） |
| `session_id` | string | ❌ | — | 会话标识 |
| `task_id` | string | ❌ | — | 任务标识 |
| `extraction_types` | string[] | ❌ | `["key_fact","task_state","decision"]` | 抽取类型 |

**请求示例**

```json
{
  "texts": [
    "用户张三偏好 React 前端开发，追求代码简洁",
    "项目 Alpha 需要在下月底前完成性能优化"
  ],
  "user_id": "user_001",
  "extraction_types": ["key_fact", "preference"]
}
```

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `results[]` | array | 每条文本的独立生成结果（同 `/generate` 响应结构） |
| `total_memories` | int | 总记忆数 |
| `total_new` | int | 总新增数 |
| `total_merged` | int | 总合并数 |
| `total_discarded` | int | 总丢弃数 |

**响应示例**

```json
{
  "code": 0,
  "data": {
    "results": [
      {"memory_ids": ["mem_001"], "new_count": 1, "merged_count": 0, "discarded_count": 0, "details": [...]},
      {"memory_ids": ["mem_002"], "new_count": 1, "merged_count": 0, "discarded_count": 0, "details": [...]}
    ],
    "total_memories": 2,
    "total_new": 2,
    "total_merged": 0,
    "total_discarded": 0
  }
}
```

**边界**

- texts 超过 50 条 → 422
- 每条文本独立走 Pipeline，总耗时 = 单条耗时 × 文本数

---

<a id="gen-async"></a>

### 3. 异步生成记忆

与 `/generate` 参数相同，但即刻返回 `request_id`，后台异步执行 Pipeline。适用于高并发或内容较长的场景。

**接口**

```
POST /api/v1/memory/generate/async
Content-Type: application/json
```

**入参**

与 `/generate` 完全一致（`GenerationRequest`）。

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `request_id` | string | 异步任务唯一标识，格式 `req_xxx` |
| `status` | string | 固定 `"accepted"` |
| `message` | string | 说明信息（含当前队列长度） |

```json
{
  "code": 0,
  "data": {
    "request_id": "req_a1b2c3d4",
    "status": "accepted",
    "message": "任务已提交 (当前队列: 2)"
  }
}
```

**边界**

- 最多 5 个并发任务，超额排队
- 任务结果缓存 30 分钟
- 失败时不重试，status 标记为 `failed`

---

<a id="gen-status"></a>

### 4. 查询异步生成状态

根据 request_id 查询异步任务的进度和结果。

**接口**

```
GET /api/v1/memory/generate/{request_id}/status
```

**入参**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|:---:|------|
| `request_id` | string | Path | ✅ | 异步任务标识 |

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `request_id` | string | 任务标识 |
| `status` | string | `pending` / `processing` / `completed` / `failed` / `not_found` |
| `progress` | float | 进度 0.0-1.0 |
| `result` | object | 完成后的 GenerationResponse（仅 completed 时有值） |
| `error` | string | 错误信息（仅 failed 时有值） |

```json
{
  "code": 0,
  "data": {
    "request_id": "req_a1b2c3d4",
    "status": "completed",
    "progress": 1.0,
    "result": {
      "memory_ids": ["mem_001"],
      "new_count": 1,
      "merged_count": 0,
      "discarded_count": 0,
      "details": [...]
    },
    "error": null
  }
}
```

**边界**

- request_id 不存在或已过期（>30min）→ `status: "not_found"`

---

<a id="gen-compress"></a>

### 5. 长对话压缩

将长对话历史压缩为结构化记忆，保留关键事实、偏好、决策和修正记录。对应设计文档 Section 5.4。

**接口**

```
POST /api/v1/memory/compress
Content-Type: application/json
```

**入参**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:---:|--------|------|
| `text` | string | ✅ | — | 长对话文本 |
| `validate_preservation` | bool | ❌ | true | 是否验证关键信息保留率 |

**请求示例**

```json
{
  "text": "[user](轮次1): 我们决定用FastAPI...\n[assistant](轮次2): 好的，FastAPI支持异步...",
  "validate_preservation": true
}
```

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `conversation_overview` | string | 对话概览 |
| `key_facts_count` | int | 保留的关键事实数 |
| `preferences_count` | int | 保留的用户偏好数 |
| `decisions_count` | int | 保留的决策数 |
| `corrections_count` | int | 保留的修正记录数 |
| `original_length` | int | 原文长度（字符） |
| `compressed_length` | int | 压缩后长度（字符） |
| `compression_ratio` | float | 压缩率 |
| `preservation_score` | float | 关键信息保留评分 |
| `compact_text` | string | 压缩后的紧凑文本 |

**边界**

- 输入为空 → 422
- 压缩结果仅返回结构化数据，不自动入库

---

<a id="gen-context-complete"></a>

### 6. 基于压缩记忆补全上下文

根据当前查询和指定压缩记忆 ID 列表，生成上下文补全文本。对应设计文档 Section 5.4.3。

**接口**

```
POST /api/v1/memory/context/complete
Content-Type: application/json
```

**入参**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:---:|--------|------|
| `query` | string | ✅ | — | 当前用户查询 |
| `memory_ids` | string[] | ✅ | — | 相关历史记忆 ID 列表 |
| `max_context_tokens` | int | ❌ | 3000 | 最大上下文 token 数 |

**请求示例**

```json
{
  "query": "当前项目使用什么技术栈",
  "memory_ids": ["mem_001", "mem_002", "mem_003"],
  "max_context_tokens": 2000
}
```

**响应**

| 参数 | 类型 | 说明 |
|------|------|------|
| `context_text` | string | 补全的上下文文本 |
| `sections_used` | string[] | 使用的记忆分类 |
| `estimated_relevance` | float | 预估相关性分数 |

**边界**

- memory_ids 全部不存在 → 返回空 context_text
- 从 T_MEMORY 加载记忆后组装为压缩记忆对象再补全
```
- 压缩阈值配置在 `config/settings.yaml` 的 `compression.trigger_session_length`（默认 30 轮）
