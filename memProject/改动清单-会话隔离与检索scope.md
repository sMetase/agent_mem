# 改动清单：会话隔离与检索 scope

> 范围：包含两部分——「会话隔离」（压缩摘要会话级 / 稳定事实偏好用户级 / 检索 scope 参数）与「跨会话任务」（工作记忆 / DAG 结构 / 干净上下文 / 自动触发）。
> 不涉及：写入去重（UPDATE 覆盖丢信息）、版本链（replaced_by）、自引用关系边、审计空表等——这些是另一批问题，单独列清单。

---

## 改动 1：压缩摘要默认保留在会话级

### 1. 解决什么问题
- 当前会话关闭时，`session_close` 把压缩摘要硬编码为 `session_id=None`（`app/api/v1/session.py:276`），把「会话级过程性信息」提升成了「用户级共享记忆」。
- 后果：会话 A 关闭后，其「订单退款 7 个工作日」这类订单级临时信息，会被会话 B 当成共享长期记忆捞走，破坏干净上下文。

### 2. 需要改动哪些点
- `app/api/v1/session.py` `session_close`（约 271–290 行）：
  - 新摘要 `Memory(session_id=...)` 由 `None` 改为当前会话 `sid`。
  - `memory_scope` 显式设为 `"session"`。
- 同函数 Qdrant payload（约 305–309 行）：`"session_id": ""` 改为 `"session_id": sid`。
- 同步更新接口响应/文档中 `kept_count`、`compressed_count`、`summary_text` 的归属说明。

### 3. 有什么隐患
- **必须与改动 3 一起做**：若检索端仍默认 `all`，写侧改成会话级但读侧不过滤，等于白改；只有 `scope=hybrid` 下才真正「隔离 + 共享长期」。
- **存量数据不自动修正**：已落库的 `source_type=compressed` 且 `session_id=NULL` 的旧摘要仍在 user 桶，需一次性数据迁移或明确容忍。
- **跨会话连续性下降**：原本「会话摘要跨会话复用」的能力消失，需靠改动 2（稳定事实/偏好升级）补回来，否则多轮客服连续性受损。

### 4. 边界是什么
- 只影响「会话关闭压缩」路径，不影响正常写入（write 仍按请求携带的 session_id 落库）。
- 只改 `task_state/process/correction` 的压缩摘要归属；`preference/fact` 走改动 2。
- 不涉及表结构变更（`session_id` 字段已存在且 nullable）。

---

## 改动 2：稳定事实和偏好升级为 user 级

### 1. 解决什么问题
- 当前会话关闭时，`preference/fact` 只是「原样保留」（计入 `kept_count`），并未真正把 `session_id` 置空，用户级长期记忆没有建立。
- 改动 1 把压缩摘要降到会话级后，若没有这个升级，跨会话连续性会丢失，需要稳定事实/偏好来补。

### 2. 需要改动哪些点
- `app/api/v1/session.py` `session_close`：对 `memory_type in ("preference","fact")` 且 `status="active"` 的记忆，执行升级：
  - `session_id → None`
  - `memory_scope → "user"`
  - 同步 Qdrant payload 的 `session_id → ""`（否则 PG 是 user 级、Qdrant 还是旧 session_id，检索会漏）。
- 需定义「稳定」判定标准（否则所有 fact/preference 一律升级，会把会话内临时事实误升上去）。至少给一个最低门槛：`importance`/`confidence` 阈值，或 LLM 判断「是否跨会话长期有效」。

### 3. 有什么隐患
- **「稳定」判定缺失会自相矛盾**：若把「这次退款 7 个工作日」这种临时事实误升为 user 级，会重新引入跨会话污染，与改动 1 的目标相悖。
- **升级后原会话查不到**：`session_id` 置空后，`scope=session` 下该记忆消失，历史审计需靠 `source_record_ids` / `t_interaction_record` 追溯。
- **与写入侧去重可能重复作用**：`memory_service._create_preference/_create_fact` 已有替换/冲突逻辑，需确认升级只发生在会话关闭，避免双重去重或覆盖语义冲突。

### 4. 边界是什么
- 只在「会话关闭」时升级，写入时不改（写入仍按请求 session_id）。
- 只对 `preference/fact` 两类生效；`task_state/process/correction` 走改动 1。
- 升级 = 改 `session_id=None` + `memory_scope=user` + Qdrant payload 同步，不新增列、不删数据。

---

## 改动 3：search / context 增加 scope 参数

### 1. 解决什么问题
- 当前 search/context 只按 `user_id` + 可选 `session_id/task_id/scene_id` 过滤，是「全有或全无」：不传 session_id 就捞到所有会话（互相干扰），传了就丢掉 user 级共享（失去连续性）。
- 缺少「干净上下文」模式 = 本会话私有 + user 级共享，排除其他会话。

### 2. 需要改动哪些点
- `app/schemas/memory.py`：`MemorySearchRequest`、`ContextRequest` 增加 `scope` 字段，枚举 `session | user | hybrid | all`，默认 `hybrid`。
- `app/api/v1/memory.py`：
  - `memory_search`（约 582–595 行）按 scope 构造 Qdrant payload 过滤 + PG 后过滤。
  - `memory_context`（约 806–820 行）同样处理。
  - 过滤语义：
    - `session` → `session_id == 当前`
    - `user` → Qdrant `session_id == ""`，PG `session_id IS NULL`
    - `hybrid` → Qdrant `session_id in ["", 当前]`，PG `IS NULL OR = 当前`
    - `all` → 不过滤 session
  - 默认值由现状「无过滤 = all」收敛到 `hybrid`。

### 3. 有什么隐患
- **默认值变更是行为变更**：依赖现有「不传就全量」的调用方会受影响；`profile`、`list` 走 PG 直查、不走 Qdrant，需单独确认是否/如何复用 scope。
- **空串 vs NULL 口径**：Qdrant payload 里 user 级是空串 `""`，PG 里是 `NULL`，两处过滤条件要分别写对，历史数据若存在空串/None 混用，`in ["", "sess_X"]` 可能漏或误匹配。
- **scope 与已有 session_id/task_id 参数并存**：需定清楚冲突规则（如同时传 `scope=session` 和 `session_id=Y`，谁生效）。
- **`scope=all` 语义需文档明确**：它仍是同一 user+scene 的全量历史，不跨用户/场景，无越权，但要在文档里写清边界。

### 4. 边界是什么
- scope 只管「会话维度」；`user_id` + `scene_id` 始终是硬边界，不跨用户、不跨场景。
- 只作用于 search/context 两个检索接口；list/stats/profile 各自确认是否复用。
- 不改表结构，只改过滤条件。

---

## 第二部分：跨会话任务

> 设计共识：跨会话任务 = 复杂问题被规划（plan）拆解成 DAG 步骤，子步骤开新会话用干净上下文执行；主会话是「拆解者 + 汇总者」，子会话是 worker，`task_state`（挂 `task_id`）是它们之间的共享白板，结果回流主会话汇总。串行步骤**可选**跨会话，并行步骤**必然**跨会话。

---

### 改动 4：task_state 从会话压缩池剔除

#### 1. 解决什么问题
- 当前会话关闭时，`compress_types = {"task_state", "process", "correction"}`（`app/api/v1/session.py:216`）把 `task_state` 也当会话碎片压缩。
- 跨会话任务靠 `task_state`（挂 `task_id`）承载任务简报与中间结果；子会话关闭若把它压成摘要并 `expired`，主会话按 `task_id` 就捞不到完整中间结果，跨会话执行断裂。

#### 2. 需要改动哪些点
- `app/api/v1/session.py` `session_close`：`compress_types` 去掉 `task_state`，只保留 `{"process", "correction"}`。
- `task_state` 在会话关闭时保持原样（`status=active`、`session_id/task_id` 不变），随任务生命周期管理。
- 任务侧新增「归档」逻辑：任务 `completed` 后，其 `task_state` 才决定保留 / 摘要 / 归档（否则长期堆积）。

#### 3. 有什么隐患
- `task_state` 不压缩会随任务增多而堆积；若任务长期不 `completed`，工作记忆膨胀——需任务完成 / 过期归档机制兜底。
- 与改动 2 的边界要划清：`task_state` 属于任务，既不升级 user 级、也不随会话压缩，是第三条路径。

#### 4. 边界是什么
- 只改「会话关闭压缩」对 `task_state` 的处理；`process / correction` 仍压缩。
- `task_state` 的归档由任务侧负责，不在会话关闭里做。

---

### 改动 5：任务 DAG 结构 + step/branch 标识

#### 1. 解决什么问题
- 当前 `t_task` 是扁平的（`goal + progress + status + completed_items / pending_items` 清单），无法表达「步骤依赖图」。
- 并行分支往同一 `task_id` 写 `task_state` 会互相覆盖，join 时无法区分「2a 的结果还是 2b 的结果」。

#### 2. 需要改动哪些点
- 最小改动：`t_memory` 增加 `step_id`（或 `branch_id`）字段，`task_state` 写入时带上，检索 / join 按 `step_id` 区分并行分支。
- 完整改动：新增子步骤实体（`t_task_step`：`step_id / task_id / parent_step_id / depends_on / status / result`）+ 依赖边，支持完整 DAG。
- `t_task` 的 `completed_items / pending_items` 从「清单」升级为「步骤」语义，或由子步骤实体替代。

#### 3. 有什么隐患
- 最小改动（只加 `step_id`）能解决并行覆盖，但表达不了依赖 / 拓扑，join 顺序要靠调用方保证。
- 完整改动（子步骤 DAG）量级大，需评估是否真需要「复杂依赖图」，还是「顺序步骤 + 偶发并行」就够。
- `step_id` 是新增字段，涉及 `t_memory` 表结构变更；是否进 Qdrant payload（检索按 step 过滤时才需要）需确认。

#### 4. 边界是什么
- `step_id / branch_id` 只服务 `task_state` 类任务工作记忆；user / session 级记忆不涉及。
- DAG 复杂度按需裁剪：先做「step_id 标识 + 串行 / 简单并行」，依赖图后续再加。

---

### 改动 6：跨会话任务的干净上下文（task_id + scope=hybrid）

#### 1. 解决什么问题
- 子会话接手任务时需要「任务简报 + 自身进度 + user 级共享」，且不能看到兄弟分支过程噪音、不能带上主会话长上下文。
- 现有检索只有 `user_id` + 可选 `session / task` 过滤，没有「任务级 + 会话级」组合的干净上下文语义。

#### 2. 需要改动哪些点
- 复用改动 3 的 `scope` 参数：子会话检索用 `task_id=T + scope=hybrid`。
- 明确组合语义：`task_id=T` 拉任务工作记忆（`task_state`），`scope=hybrid` 决定会话维可见（自身 + user 共享，排除其他会话）。
- 确认 task 维度与 session 维度正交时，`task_state`（scope=task）在 `scope=hybrid` 下应被正确包含（按 `task_id` 命中，不受 session 过滤拦截）。

#### 3. 有什么隐患
- task 维度与 session 维度正交，但 Qdrant payload 只有 4 字段（user/scene/task/session），组合过滤语义要写清楚，否则「hybrid + task_id」可能漏掉 `task_state` 或误带其他会话。
- 兄弟分支隔离依赖「scope=hybrid 不含其他会话」，需验证并行分支 `session_id` 互不相同、互不命中。

#### 4. 边界是什么
- 干净上下文 = `task_id=T` ∩ `scope=hybrid`。不跨 user、不跨 scene。
- 主会话的 join 汇总（读所有分支 step 结果）在任务侧做，不属于检索 scope 的改动。

---

### 改动 7（可选）：任务自动触发（模型规划）

#### 1. 解决什么问题
- 当前任务只能外部手动 `POST /task` 创建，模型不判断「要不要开任务」，跨会话任务无从自动触发。

#### 2. 需要改动哪些点
- 在写入 / 对话处理链路加「规划」步骤：模型判断请求是否「可分解 + 需分段」，是则自动建任务 + 拆步。
- 规划信号：步骤数、可并行性、预估上下文长度。

#### 3. 有什么隐患
- 自动开任务可能误判（简单问题也开任务），需保守阈值 + 可回退「直接执行」。
- 规划本身消耗一次 LLM 调用，增加延迟。

#### 4. 边界是什么
- 只影响「触发」环节；任务一旦建立，执行 / 归档走改动 4 / 5 / 6。

---

## 附：实现前需先解决的前置项

- `app/models/base.py` 中 `memory_scope` 列被定义了两次（约 185 行与 193 行），改动 1/2 写入 `memory_scope`、改动 3 过滤时都会受影响，需先清理为单一定义。
- 统一 Qdrant payload 中 `session_id` 的空值口径（user 级统一存 `""`），否则改动 3 的 `in ["", "sess_X"]` 过滤会不稳定。
