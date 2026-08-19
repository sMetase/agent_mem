# Dify Chatflow 编排说明（主链路 · 演示版）

> 按节点逐个编排。场景 + 智能体由接口**动态创建**，`scene_id` / `agent_id` / `api_key` 从接口返回赋值给对话变量。
> 适用场景：演示 / 测试，每个对话独立一套场景 + 智能体。

---

## 一、环境变量（Dify 工作流设置 → 环境变量）

只需 4 个，都是固定值：

| 变量名 | 值 | 说明 |
|---|---|---|
| `BASE_URL` | `http://120.27.207.238:8000` | 记忆系统地址 |
| `USER_ID` | `user_001` | 预定义用户标识 |
| `SCENE_NAME` | `客服场景` | 场景名称（固定） |
| `AGENT_NAME` | `客服助手` | 智能体名称（固定） |

> `SCENE_ID` / `AGENT_ID` / `API_KEY` **不再需要**——这三个值由下面的节点从接口返回动态赋值。

---

## 二、对话变量（Dify 工作流设置 → 对话变量）

| 变量名 | 类型 | 初始值 | 说明 |
|---|---|---|---|
| `scene_id` | 文本 | 空 | 场景 ID（第一轮创建后写入） |
| `agent_id` | 文本 | 空 | 智能体 ID（第一轮注册后写入） |
| `api_key` | 文本 | 空 | API Key（第一轮注册后写入） |
| `main_session_id` | 文本 | 空 | 主会话 |
| `task_id` | 文本 | 空 | 当前任务 |
| `task_session_id` | 文本 | 空 | 当前任务会话 |
| `task_active` | 文本 | `false` | 是否在任务中 |

---

## 三、节点清单（10 个）

### 节点 1 — 开始（Start）

- **类型**：开始
- **输入变量**：`query`（用户消息，段落，必填）
- **输出**：`query`

---

### 节点 2 — Code：初始化场景与智能体

- **类型**：代码执行（Code）
- **作用**：第一轮创建场景 + 注册智能体，拿到 `scene_id` / `agent_id` / `api_key`；后续轮直接复用。
- **输入变量**：

| 变量名 | 引用来源 |
|---|---|
| `scene_id` | 对话变量 `scene_id` |
| `agent_id` | 对话变量 `agent_id` |
| `api_key` | 对话变量 `api_key` |
| `SCENE_NAME` | 环境变量 `SCENE_NAME` |
| `AGENT_NAME` | 环境变量 `AGENT_NAME` |
| `BASE_URL` | 环境变量 `BASE_URL` |

- **代码**：

```python
import requests

def main(scene_id, agent_id, api_key, SCENE_NAME, AGENT_NAME, BASE_URL):
    # 第一轮：创建场景
    if not scene_id or not scene_id.strip():
        r = requests.post(f"{BASE_URL}/api/v1/scene",
            headers={"Content-Type": "application/json"},
            json={"scene_name": SCENE_NAME, "description": "演示场景"},
            timeout=15).json()
        scene_id = r["data"]["scene_id"]

    # 第一轮：注册智能体（依赖 scene_id）
    if not agent_id or not agent_id.strip():
        r = requests.post(f"{BASE_URL}/api/v1/agent/register",
            headers={"Content-Type": "application/json"},
            json={"agent_name": AGENT_NAME, "scene_id": scene_id,
                  "permissions": ["read", "write"]},
            timeout=15).json()
        agent_id = r["data"]["agent_id"]
        api_key = r["data"]["api_key"]

    return {"scene_id": scene_id, "agent_id": agent_id, "api_key": api_key}
```

- **输出变量**：`scene_id`、`agent_id`、`api_key` → 分别写回对话变量

---

### 节点 3 — Code：初始化主会话

- **类型**：代码执行（Code）
- **作用**：第一轮创建主会话，存 `main_session_id`。
- **输入变量**：

| 变量名 | 引用来源 |
|---|---|
| `main_session_id` | 对话变量 `main_session_id` |
| `scene_id` | 对话变量 `scene_id` |
| `agent_id` | 对话变量 `agent_id` |
| `api_key` | 对话变量 `api_key` |
| `USER_ID` | 环境变量 `USER_ID` |
| `BASE_URL` | 环境变量 `BASE_URL` |

- **代码**：

```python
import requests

def main(main_session_id, scene_id, agent_id, api_key, USER_ID, BASE_URL):
    if main_session_id and main_session_id.strip():
        return {"main_session_id": main_session_id}

    r = requests.post(f"{BASE_URL}/api/v1/session",
        headers={"X-API-Key": api_key, "X-Agent-Id": agent_id,
                 "Content-Type": "application/json"},
        json={"user_id": USER_ID, "scene_id": scene_id},
        timeout=15).json()
    sid = r["data"]["session_id"]
    return {"main_session_id": sid}
```

- **输出变量**：`main_session_id` → 写回对话变量

---

### 节点 4 — LLM：任务判定

- **类型**：LLM
- **输入**：`query`（节点 1）、`task_active`（会话变量）
- **记忆窗口**：开启，最近 5 轮
- **输出模式**：JSON 输出

**System Prompt**：

```
你是对话任务识别器。根据用户当前消息、最近对话、以及"当前是否已有进行中的任务"，判断任务动作。

任务定义：需要多轮推进、有明确目标、需持续跟踪进展的复杂工作（退货流程、项目推进、问题排查等）。简单问答、闲聊、单次查询不算任务。

输出 JSON，字段：
- action：
  - "none"：普通闲聊/简单问答，不涉及任务
  - "new_task"：开启全新复杂任务（仅当当前无进行中任务时）
  - "continue_task"：当前消息是进行中任务的延续（仅当当前有任务时）
  - "new_session"：当前任务进入新阶段，需开新的子会话（仅当当前有任务时）
- title：任务标题（仅 new_task 时，≤20字）
- goal：任务目标（仅 new_task 时，一句话）

判断规则（先看"当前是否已有进行中的任务"）：
- 当前无任务（false）：
  - 简单问答/闲聊 → none
  - 复杂任务（多轮推进、有明确目标）→ new_task
- 当前有任务（true）：
  - 消息是当前任务的延续 → continue_task
  - 消息是当前任务的新阶段/新子主题 → new_session
  - 消息是完全无关的闲聊 → none
```

**User Prompt**：

```
用户当前消息：{{query}}
当前是否已有进行中的任务：{{task_active}}
```

- **输出变量**：`action`、`title`、`goal`

---

### 节点 5 — Code：任务管理

- **类型**：代码执行（Code）
- **输入变量**：

| 变量名 | 引用来源 |
|---|---|
| `action` | 节点 4 输出 |
| `title` | 节点 4 输出 |
| `goal` | 节点 4 输出 |
| `task_active` | 对话变量 |
| `task_id` | 对话变量 |
| `task_session_id` | 对话变量 |
| `scene_id` | 对话变量 |
| `agent_id` | 对话变量 |
| `api_key` | 对话变量 |
| `USER_ID` | 环境变量 |
| `BASE_URL` | 环境变量 |

- **代码**：

```python
import requests

def main(action, title, goal, task_active, task_id, task_session_id,
         scene_id, agent_id, api_key, USER_ID, BASE_URL):
    headers = {"X-API-Key": api_key, "X-Agent-Id": agent_id,
               "Content-Type": "application/json"}

    # 开新任务
    if action == "new_task" and task_active != "true":
        t = requests.post(f"{BASE_URL}/api/v1/task", headers=headers,
            json={"user_id": USER_ID, "scene_id": scene_id,
                  "title": title, "goal": goal}, timeout=15).json()
        task_id = t["data"]["task_id"]
        s = requests.post(f"{BASE_URL}/api/v1/session", headers=headers,
            json={"user_id": USER_ID, "scene_id": scene_id,
                  "task_id": task_id}, timeout=15).json()
        task_session_id = s["data"]["session_id"]
        task_active = "true"

    # 当前任务开新子会话
    elif action == "new_session" and task_active == "true" and task_id:
        s = requests.post(f"{BASE_URL}/api/v1/session", headers=headers,
            json={"user_id": USER_ID, "scene_id": scene_id,
                  "task_id": task_id}, timeout=15).json()
        task_session_id = s["data"]["session_id"]

    return {"task_id": task_id, "task_session_id": task_session_id,
            "task_active": task_active}
```

- **输出变量**：`task_id`、`task_session_id`、`task_active` → 写回对话变量

---

### 节点 6 — HTTP：检索上下文

- **类型**：HTTP 请求
- **配置**：

| 项 | 值 |
|---|---|
| 方法 | POST |
| URL | `{{BASE_URL}}/api/v1/memory/context` |
| Header | `X-API-Key: {{api_key}}`、`X-User-Id: {{USER_ID}}`、`X-Agent-Id: {{agent_id}}`、`Content-Type: application/json` |
| Body (JSON) | `{"query": "{{query}}", "user_id": "{{USER_ID}}", "memory_types": ["preference", "fact"], "top_k": 5, "max_tokens": 2000}` |

- **提取变量**：`formatted_text` ← `body.data.formatted_text`

---

### 节点 7 — LLM：生成回复

- **类型**：LLM
- **输入**：`query`（节点 1）、`formatted_text`（节点 6）
- **输出模式**：JSON 输出

**System Prompt**：

```
你是客服助手。参考用户的偏好和事实记忆，生成自然回复。

## 用户记忆上下文
{{formatted_text}}

输出 JSON，字段：
- reply：回复文本
- task_completed：bool，仅当本轮对话明确达成某个任务目标（如"退款已到账"、"问题已解决"）时为 true，否则 false
- task_progress_changed：bool，仅当本轮产生实质任务进展（完成某步骤/进入新阶段）时为 true，否则 false
```

**User Prompt**：

```
用户消息：{{query}}
```

- **输出变量**：`reply`、`task_completed`、`task_progress_changed`

---

### 节点 8 — Code：任务收尾

- **类型**：代码执行（Code）
- **输入变量**：

| 变量名 | 引用来源 |
|---|---|
| `task_completed` | 节点 7 输出 |
| `task_progress_changed` | 节点 7 输出 |
| `reply` | 节点 7 输出 |
| `goal` | 节点 4 输出 |
| `task_id` | 对话变量 |
| `task_session_id` | 对话变量 |
| `task_active` | 对话变量 |
| `scene_id` | 对话变量 |
| `agent_id` | 对话变量 |
| `api_key` | 对话变量 |
| `USER_ID` | 环境变量 |
| `BASE_URL` | 环境变量 |

- **代码**：

```python
import requests

def main(task_completed, task_progress_changed, reply, goal,
         task_id, task_session_id, task_active,
         scene_id, agent_id, api_key, USER_ID, BASE_URL):
    headers = {"X-API-Key": api_key, "X-Agent-Id": agent_id,
               "X-User-Id": USER_ID, "Content-Type": "application/json"}

    # 任务完成 → complete + close 任务会话
    if task_completed and task_id:
        requests.post(f"{BASE_URL}/api/v1/task/{task_id}/complete",
                      headers=headers, timeout=15)
        if task_session_id:
            requests.post(f"{BASE_URL}/api/v1/session/{task_session_id}/close",
                          headers=headers, timeout=15)
        task_active = "false"

    # 进展实质变化 → 写 task_process 到任务会话
    elif task_progress_changed and task_session_id:
        requests.post(f"{BASE_URL}/api/v1/memory/write", headers=headers,
            json={"user_id": USER_ID, "scene_id": scene_id,
                  "session_id": task_session_id, "task_id": task_id,
                  "interaction_type": "task_process",
                  "task_goal": goal, "task_progress": reply}, timeout=90)

    return {"task_active": task_active}
```

- **输出变量**：`task_active` → 写回对话变量

---

### 节点 9 — Code：写入对话记忆

- **类型**：代码执行（Code）
- **输入变量**：

| 变量名 | 引用来源 |
|---|---|
| `query` | 节点 1 |
| `reply` | 节点 7 |
| `main_session_id` | 对话变量 |
| `scene_id` | 对话变量 |
| `agent_id` | 对话变量 |
| `api_key` | 对话变量 |
| `USER_ID` | 环境变量 |
| `BASE_URL` | 环境变量 |

- **代码**：

```python
import requests

def main(query, reply, main_session_id,
         scene_id, agent_id, api_key, USER_ID, BASE_URL):
    requests.post(f"{BASE_URL}/api/v1/memory/write",
        headers={"X-API-Key": api_key, "X-Agent-Id": agent_id,
                 "X-User-Id": USER_ID, "Content-Type": "application/json"},
        json={"user_id": USER_ID, "scene_id": scene_id,
              "session_id": main_session_id, "interaction_type": "dialogue",
              "messages": [
                  {"role": "user", "content": query},
                  {"role": "assistant", "content": reply}
              ]},
        timeout=90)
    return {"ok": True}
```

---

### 节点 10 — 结束（End）

- **类型**：结束
- **输出变量**：`reply`（节点 7）

---

## 四、连线（数据流）

```
节点1 开始(query)
  → 节点2 初始化场景与智能体 → scene_id / agent_id / api_key
  → 节点3 初始化主会话 → main_session_id
  → 节点4 LLM任务判定 → action / title / goal
  → 节点5 任务管理 → task_id / task_session_id / task_active
  → 节点6 检索上下文 → formatted_text
  → 节点7 LLM生成回复 → reply / task_completed / task_progress_changed
  → 节点8 任务收尾
  → 节点9 写入对话记忆
  → 节点10 结束(reply)
```

---

## 五、编排提醒

1. **对话变量写回**：节点 2 / 3 / 5 / 8 的返回值必须「写回对话变量」。这是跨轮不「断片」的关键。
2. **第一轮 vs 后续轮**：节点 2 / 3 内部用「if 为空才创建」判断——第一轮创建，后续轮复用对话变量里的值。
3. **演示特性**：每个新对话都会创建一套新场景 + 智能体（对话变量每对话重置），数据库会累积，但演示场景无所谓。
4. **超时**：节点 8 / 9 的 `memory/write` 是同步 LLM pipeline（5-15 秒），`timeout` 给 ≥90 秒。
5. **敏感信息**：`api_key` 是对话变量（运行时动态），不落环境变量，演示场景 OK；若以后转生产，要改回预创建 + secret 环境变量。
