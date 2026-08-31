# 智能体记忆系统 — 前端接口对接文档

## 这个系统是做什么的

当用户和 AI 对话时，本系统自动从对话中提取有价值的"记忆"（用户偏好、关键事实、任务状态），并存储起来。下次用户再对话时，AI 能通过检索这些记忆，知道"这个人喜欢什么""之前聊到哪了""上次决策是什么"，实现连续、个性化的对话体验。

对话交互 → 调接口存记忆 → 下次对话前检索记忆 → 注入 AI 上下文。

---

## 基础信息

| 项 | 值 |
|------|-----|
| Base URL | `http://120.27.207.238:8000` |
| 数据格式 | JSON |
| 鉴权 | 开发阶段无需鉴权，未来需 `X-API-Key` 请求头 |
| 字符编码 | UTF-8 |

---

## 统一响应格式

成功 `code=0`：
```json
{"code": 0, "message": "ok", "data": {...}}
```

失败 `code=-1`：
```json
{"code": -1, "message": "错误描述", "error_code": "NOT_FOUND", "trace_id": "abc123"}
```

前端用 `code` 判断成功/失败，`error_code` 做具体错误区分，`trace_id` 帮你排查问题。

---

## 注册智能体

每个前端应用只需注册一次，拿到一个 `api_key`。这个 key 将来用于鉴权。

**POST `/api/v1/agent/register`**

```json
// → 发送
{"agent_name": "Web聊天助手", "scene_id": "chat", "permissions": ["read","write"]}

// ← 返回
{"code":0, "data":{"agent_id":"agent_abc","api_key":"mem_xxxx","api_key_prefix":"mem_****"}}
```

> `api_key` 仅这一次返回明文！请保存到前端配置中。如果丢失请调 `/agent/{id}/rotate-key` 换新 key。

---

## 典型使用流程

一个完整的对话周期大概是这样的：

```
用户打开聊天 → 创建会话 → 用户说话 → 检索历史记忆 → AI回复 → 存入本次对话记忆 → 用户继续说话 → 循环
```

每一步对应的接口在下面详细说明。

---

## 一、记忆接口（最核心，4个）

### 1. 写入记忆 — `/api/v1/memory/write`

**什么时候调**：用户每轮对话后，把本轮对话内容写入系统。系统自动从中提取重要的记忆（偏好、事实、决定等）。

**为什么需要它**：不存就没记忆。存了之后检索接口才能搜到。

支持三种数据写入模式（通过 `interaction_type` 区分）：

**① 对话记录（dialogue）** — 最常用：
```json
{
  "user_id": "user_001",
  "scene_id": "chat",
  "task_id": "task_001",
  "interaction_type": "dialogue",
  "messages": [
    {"role": "user", "content": "我叫张伟，喜欢Python后端开发"}
  ]
}
```

**② 历史会话导入（session）** — 含时间/来源/摘要：
```json
{
  "user_id": "user_001",
  "interaction_type": "session",
  "session_time": "2026-07-15T10:00:00Z",
  "session_source": "chat",
  "session_summary": "用户和AI讨论了Python后端开发"
}
```

**③ 任务过程写入（task_process）** — 含目标/进展/结果：
```json
{
  "user_id": "user_001",
  "interaction_type": "task_process",
  "task_goal": "完成技术方案文档",
  "task_progress": "已完成需求分析",
  "task_result": "方案已通过评审"
}
```

**响应：**
```json
{"code":0, "data":{"results":[{"id":"mem_abc","memory":"用户名为张伟，偏好Python后端。","event":"ADD"}]}}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | **是** | 用户唯一标识 |
| `interaction_type` | string | 否 | dialogue / session / task_process，默认 dialogue |
| `scene_id` | string | 否 | 场景标识，写入后检索可按场景过滤 |
| `session_id` | string | 否 | 会话ID（Header `X-Session-Id` 可替代） |
| `task_id` | string | 否 | 任务ID |
| `messages` | array | dialogue 必填 | `[{"role":"user","content":"..."}]` |
| `session_time` | string | session 时 | 会话发生时间 |
| `session_source` | string | session 时 | 会话来源 |
| `session_summary` | string | session 时 | 会话摘要 |
| `task_goal` | string | task 时 | 任务目标 |
| `task_progress` | string | task 时 | 任务进展 |
| `task_result` | string | task 时 | 执行结果 |

> 注意：此接口调用大模型做记忆抽取，**耗时约 5-15 秒**（Mock 模式 < 100ms）。

---

### 2. 检索记忆 — `/api/v1/memory/search`

**什么时候调**：用户发起新对话或新问题时，检索与该用户相关的历史记忆。这是整个系统的核心——让 AI "记住"之前聊过什么。

**为什么需要它**：把检索到的记忆注入 AI 的上下文（Prompt），AI 就能说"上次你提到喜欢 Python，这个方案也可以用 Python 实现"。

```json
// → 发送
{
  "query": "后端技术栈",
  "user_id": "user_001",
  "scene_id": "chat",
  "task_id": "task_001",
  "memory_types": ["preference"],
  "top_k": 5
}

// ← 返回
{
  "code":0,
  "data":{
    "query": "后端技术栈",
    "results":[
      {
        "memory_id": "mem_abc",
        "content": "用户使用Python和FastAPI",
        "relevance_score": 0.853,
        "memory_type": "unknown",
        "scene_id": "chat",
        "task_id": "task_001",
        "created_at": "2026-07-06T10:30:00Z"
      }
    ],
    "total_candidates": 12,
    "elapsed_ms": 156
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | **是** | 用什么文本去搜索记忆（可以是用户当前的问题） |
| `user_id` | string | **是** | 查谁的历史记忆 |
| `scene_id` | string | 否 | 只查某个场景下的记忆 |
| `task_id` | string | 否 | 只查某个任务相关的记忆 |
| `memory_types` | array | 否 | 只查某类记忆：「preference偏好」「fact事实」「task任务状态」「decision决策」「constraint约束」 |
| `time_start`/`time_end` | string | 否 | 只查某个时间段内的记忆，格式 ISO 8601 |
| `top_k` | int | 否 | 返回几条，默认10，最多50 |
| `max_content_length` | int | 否 | 内容最大长度（超出截断加省略号） |
| `rerank` | bool | 否 | 是否启用二次排序，开启后检索更准但多 200ms |
| `status` | array | 否 | 按记忆状态过滤，如 `["active"]` |

**如何理解结果**：
- `relevance_score` — 综合相关性分数，越高越相关
- `total_candidates` — 还有多少条候选你没拿（你可以用 `top_k` 多拿一些）
- `elapsed_ms` — 这次检索花了多少毫秒

---

### 3. 列出全部记忆 — `/api/v1/memory/list`

**什么时候调**：你想在界面上展示用户所有已存储的记忆（类似"我的记忆"页面），或者调试时查看存了哪些。

```json
// → 请求（Query 参数）
POST /api/v1/memory/list?user_id=user_001

// ← 返回
{"code":0, "data":[{...记忆对象...}, {...}]}
```

---

### 4. 清除全部记忆 — `/api/v1/memory/delete-all`

**什么时候调**：用户要求"忘记我的一切"或测试时需要清空数据。

```json
// → 请求（Query 参数）
POST /api/v1/memory/delete-all?user_id=user_001

// ← 返回
{"code":0, "data":"Successfully deleted all memories"}
```

---

## 二、辅助记忆接口（4个）

### 获取 Prompt 上下文片段 — `/api/v1/memory/context`

**什么时候调**：检索完之后，如果你不想自己拼接 Prompt，可以直接调这个接口，返回一段格式化好的文本，直接塞进 AI Prompt 就行。

```json
// → 发送
{"query":"当前任务","user_id":"u1","max_tokens":3000,"group_by_type":true}

// ← 返回
{"code":0,"data":{"formatted_text":"## 用户偏好\n- Python\n## 关键事实\n- 张伟，后端","memory_count":5}}
```

### 更新记忆 — `PUT /api/v1/memory/update`

用户纠正某条记忆时使用：`{"memory_id":"xxx","content":"修正后的内容"}`

### 删除记忆 — `DELETE /api/v1/memory/delete`

删掉单条记忆（软删除，可追溯）：`{"memory_id":"xxx","reason":"用户要求"}`

### 异步写入 — `POST /api/v1/memory/async_write`

参数同 `/write`，即刻返回 `request_id`，后台异步处理。适合不需要立即检索的高并发场景。Phase 5 实现。

---

## 三、记忆生成与去重融合接口（3个）

这些接口直接输入文本，执行完整流水线：**关键记忆抽取 → 结构化记忆生成 → 去重融合 → 存储**。适合调试、批量导入、或不需要 messages 数组格式的场景。

与 `/memory/write` 的区别：`/write` 接收 messages 数组（对话格式），内部调用同一套流水线；`/generate` 接收纯文本，更直接。

### 1. 同步生成 — `POST /api/v1/memory/generate`

**什么时候调**：有一整段文本（对话摘要、任务描述等），想直接从中提取并存储记忆。

```json
// → 发送
{
  "text": "用户说他喜欢用 Python 开发，项目 deadline 是下周五，我们决定用 FastAPI 框架",
  "user_id": "user_001",
  "scene_id": "chat",
  "task_id": "task_001",
  "extraction_types": ["key_fact", "task_state", "decision", "preference"]
}

// ← 返回
{
  "code": 0,
  "data": {
    "memory_ids": ["mem_abc123", "mem_def456"],
    "new_count": 2,
    "merged_count": 0,
    "discarded_count": 1,
    "updated_count": 0,
    "conflict_count": 0,
    "details": [
      {
        "action": "keep_new",
        "memory_id": "mem_abc123",
        "content_preview": "用户偏好 Python 开发",
        "memory_type": "preference",
        "importance": 0.8,
        "confidence": 0.9,
        "message": "新记忆已创建"
      },
      {
        "action": "keep_new",
        "memory_id": "mem_def456",
        "content_preview": "项目 deadline 为下周五",
        "memory_type": "fact",
        "importance": 0.7,
        "confidence": 0.85,
        "message": "新记忆已创建"
      },
      {
        "action": "discard",
        "memory_id": null,
        "content_preview": "决定用 FastAPI",
        "memory_type": "decision",
        "importance": 0.5,
        "confidence": 0.5,
        "message": "与已有记忆高度重复，跳过"
      }
    ]
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | **是** | 输入文本，最大 10000 字符 |
| `user_id` | string | **是** | 用户唯一标识 |
| `scene_id` | string | 否 | 场景标识 |
| `session_id` | string | 否 | 会话标识 |
| `task_id` | string | 否 | 任务标识 |
| `agent_id` | string | 否 | 智能体标识 |
| `extraction_types` | array | 否 | 要抽取的记忆类型，默认全部：`key_fact` `task_state` `decision` `preference` `process` `feedback` |
| `source_record_ids` | array | 否 | 来源记录 ID，用于追溯 |
| `metadata` | object | 否 | 业务扩展元数据 |

**响应字段说明：**

| 字段 | 说明 |
|------|------|
| `memory_ids` | 本次实际存储的记忆 ID 列表 |
| `new_count` | 新增记忆数 |
| `merged_count` | 合并到已有记忆的数量 |
| `discarded_count` | 因高度重复被丢弃的数量 |
| `updated_count` | 更新已有记忆的数量 |
| `conflict_count` | 冲突数量（通常为 0） |
| `details[].action` | 处理动作：`keep_new`(新增) `merge`(合并) `discard`(丢弃) `update_existing`(更新) `conflict`(冲突) |
| `details[].content_preview` | 记忆内容前 100 字预览 |
| `details[].memory_type` | 记忆类型：preference / fact / task / decision / constraint |
| `details[].importance` | 重要性评分（0-1） |
| `details[].confidence` | 置信度评分（0-1） |

> 耗时约 **5-15 秒**（4 次 LLM 调用：3 路并行抽取 + 1 次生成）。

---

### 2. 批量生成 — `POST /api/v1/memory/generate/batch`

**什么时候调**：一次性导入多条文本（如批量迁移历史数据），最多 50 条。

```json
// → 发送
{
  "texts": [
    "用户张三偏好 React 前端开发，追求代码简洁",
    "项目 Alpha 需要在下月底前完成性能优化"
  ],
  "user_id": "user_001",
  "extraction_types": ["key_fact", "preference"]
}

// ← 返回
{
  "code": 0,
  "data": {
    "results": [
      {
        "memory_ids": ["mem_xxx"],
        "new_count": 1,
        "merged_count": 0,
        "discarded_count": 0,
        "updated_count": 0,
        "details": [...]
      },
      {
        "memory_ids": ["mem_yyy"],
        "new_count": 1,
        "merged_count": 0,
        "discarded_count": 0,
        "updated_count": 0,
        "details": [...]
      }
    ],
    "total_memories": 2,
    "total_new": 2,
    "total_merged": 0,
    "total_discarded": 0
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `texts` | array | **是** | 文本列表，1-50 条，每条最大 10000 字符 |
| `user_id` | string | **是** | 用户唯一标识 |
| `scene_id` | string | 否 | 场景标识（所有文本共用） |
| `session_id` | string | 否 | 会话标识 |
| `task_id` | string | 否 | 任务标识 |
| `agent_id` | string | 否 | 智能体标识 |
| `extraction_types` | array | 否 | 抽取类型，默认 `["key_fact","task_state","decision"]` |

> 每条文本独立执行完整流水线，总耗时 = 单条耗时 × 文本数（并行度受 LLM API 限流影响）。

---

### 3. 异步生成 — `POST /api/v1/memory/generate/async`

**什么时候调**：文本很长或不想等 5-15 秒，提交后台任务，立即返回 `request_id`，之后轮询结果。

```json
// → 发送（参数同 /generate）
{
  "text": "大段文本...",
  "user_id": "user_001"
}

// ← 返回（即刻）
{
  "code": 0,
  "data": {
    "request_id": "req_abc123",
    "status": "accepted",
    "message": "任务已提交 (当前队列: 2)"
  }
}
```

**查询进度** — `GET /api/v1/memory/generate/{request_id}/status`

```json
// ← 返回（处理中）
{
  "code": 0,
  "data": {
    "request_id": "req_abc123",
    "status": "processing",
    "progress": 0.5,
    "result": null,
    "error": null
  }
}

// ← 返回（完成）
{
  "code": 0,
  "data": {
    "request_id": "req_abc123",
    "status": "completed",
    "progress": 1.0,
    "result": { ... GenerationResponse ... },
    "error": null
  }
}
```

| status 值 | 含义 |
|-----------|------|
| `pending` | 排队中 |
| `processing` | 正在执行 |
| `completed` | 已完成，result 中有数据 |
| `failed` | 失败，error 中有错误信息 |
| `not_found` | request_id 不存在或已过期 |

> 最多 5 个并发任务，超额排队等待。任务结果缓存 30 分钟。

---

## 四、会话接口（对话开始/结束）

会话是一次完整的多轮对话单位。你可以用它来追踪"这次对话持续了多久""聊了多少轮"。

### 创建会话 — `POST /api/v1/session`

**什么时候调**：用户开始一次新对话时。

```json
// → 发送
{"user_id":"u1","agent_id":"agent_xxx","scene_id":"chat","task_id":"task_xxx"}
// ← 返回
{"code":0,"data":{"session_id":"sess_abc","status":"active"}}
```

### 关闭会话 — `POST /api/v1/session/{session_id}/close`

**什么时候调**：用户结束对话时。会触发后台对本次会话做记忆压缩（把冗长对话提炼为摘要）。

查询、列表、更新接口详见 Swagger。

---

## 五、任务接口（长周期任务追踪）

如果你做的是"技术方案编写""代码开发"等需要跨多轮对话完成的任务，可以用任务接口追踪进展。

### 创建任务 — `POST /api/v1/task`

**什么时候调**：用户开启一个明确的目标，比如"帮我写技术方案"。

```json
// → 发送
{"user_id":"u1","title":"技术方案编写","goal":"完成Q3技术方案文档","scene_id":"doc"}
// ← 返回
{"code":0,"data":{"task_id":"task_abc","status":"pending"}}
```

### 更新任务进展 — `PUT /api/v1/task/{task_id}`

**什么时候调**：每轮对话后，更新任务到了哪一步、完成了什么。

```json
{"status":"in_progress","progress":"已完成需求分析，正在设计方案",
 "completed_items":["需求文档"],"pending_items":["技术方案","代码实现"]}
```

### 查看进展 — `GET /api/v1/task/{task_id}/progress`

```json
{"code":0,"data":{"task_id":"task_abc","status":"in_progress",
 "completed_count":3,"pending_count":2,"related_memory_count":12}}
```

`related_memory_count` 告诉你这个任务已经有多少条相关记忆了。

---

## 六、场景接口（环境隔离）

如果你有多个 AI 应用（比如一个聊天助手、一个代码助手、一个文档助手），用不同 `scene_id` 来隔离它们的记忆。

### 创建场景 — `POST /api/v1/scene`

```json
{"scene_name":"代码助手","description":"写代码相关的对话"}
```


---

## 七、实现状态说明（2026-07-17 更新）

### 后端处理管线

`POST /memory/write` 已从 Mock 替换为**真实记忆生成流水线**：

```
messages 数组 → 拼接对话文本 → MemoryPipeline
  ├── Phase 1: MemoryExtractor   (三路并行 LLM 抽取: 关键事实 + 任务状态 + 历史决策)
  ├── Phase 2: MemoryGenerator   (LLM 生成结构化 MemoryCandidate)
  ├── Phase 3: DedupService      (Qdrant 向量 + Jaccard 关键词 + 标识检查 → 综合决策)
  └── Phase 4: Store             (PostgreSQL + Qdrant 双写)
```

**关键技术栈:**
- LLM: DeepSeek (`deepseek-chat`) — 直连 API
- Embedding: SiliconFlow (`BGE-M3`, 1024维) — 直连 API
- 向量库: Qdrant (collection: `agent_mem_generation`)
- 数据库: PostgreSQL (`t_memory` 表)

### 端点实现状态

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| `/memory/write` | POST | ✅ 已实现 | 真实 Pipeline：extract→generate→dedup→store |
| `/memory/search` | POST | ✅ 已实现 | Qdrant 语义搜索 + PostgreSQL 元数据过滤 |
| `/memory/list` | POST | ✅ 已实现 | PostgreSQL 分页查询，空时降级 MCP |
| `/memory/delete-all` | POST | ✅ 已实现 | PostgreSQL + Qdrant + MCP 三清 |
| `/memory/context` | POST | ✅ 已实现 | 检索 + 按类型分组格式化为 Prompt |
| `/memory/update` | PUT | ✅ 已实现 | 部分字段更新 + 向量重算 |
| `/memory/delete` | DELETE | ✅ 已实现 | 软删除 + Qdrant 向量移除 |
| `/memory/async_write` | POST | ⚠️ 占位 | 即刻返回 request_id，MQ 未实现（降级同步） |
| `/memory/generate` | POST | ✅ 已实现 | 直接输入文本→记忆，完整 Pipeline |
| `/memory/generate/batch` | POST | ✅ 已实现 | 批量生成，最多 50 条 |
| `/memory/generate/async` | POST | ✅ 已实现 | 异步提交，内存队列（生产建议换 Celery/Kafka） |
| `/memory/generate/{id}/status` | GET | ✅ 已实现 | 查询异步任务进度与结果 |
| `/memory/compress` | POST | ✅ 已实现 | 长对话压缩为结构化记忆 |
| `/memory/context/complete` | POST | ✅ 已实现 | 基于历史压缩记忆补全上下文 |

### 去重决策矩阵

`/memory/write` 返回的 `event` 字段映射：

| Pipeline Action | 前端 event | 含义 |
|-----------------|-----------|------|
| `keep_new` | `ADD` | 新记忆已创建 |
| `merge` | `MERGE` | 合并到已有记忆 |
| `update_existing` | `ADD` | 更新已有记忆（视为新增信息） |
| `discard` | `SKIP` | 高度重复，跳过 |

### 延迟预估

| 操作 | 预估延迟 | 说明 |
|------|---------|------|
| `/memory/write` | 5-15s | 4 次 LLM 调用（3 路并行抽取 + 1 次生成） |
| `/memory/search` | 200-500ms | Embedding 计算 + Qdrant 检索 + DB 查询 |
| `/memory/list` | 50-200ms | 纯 DB 分页查询 |
| `/memory/delete-all` | 100-500ms | DB 批量删除 + Qdrant 向量清理 |
| `/memory/context` | 300-800ms | 等同于 search + 格式化 |

> **建议**: 生产环境中将 `/memory/write` 替换为 `/memory/async_write`，前端先展示对话，后台异步生成记忆。下一次对话前检索即可命中新记忆。

