# mem0 框架源码解析

> 基于本地源码副本 `mem0_repo`（`mem0ai/mem0`，版本 `2.0.11`，Apache-2.0）
> 定位：**AI Agent 的长期记忆层（Long-term memory for AI Agents）**

---

## 1. 概览

mem0 是一个可插拔的长期记忆框架，核心职责是把「对话/事件」提炼成「结构化记忆」，并支持按语义检索。它把记忆能力拆成四个可替换的引擎，通过工厂模式装配：

| 引擎 | 职责 | 可替换 Provider 数量 |
| --- | --- | --- |
| **LLM** | 从对话中抽取/更新记忆、回答 | ~18（openai/deepseek/anthropic/...） |
| **Embedding** | 文本 → 向量 | ~11（openai/huggingface/...） |
| **Vector Store** | 向量存储与相似度/关键词检索 | ~26（qdrant/chroma/pgvector/...） |
| **Reranker** | 对检索结果重排序 | ~5（cohere/sentence_transformer/...） |

一个 `Memory` 实例 = 1 个 LLM + 1 个 Embedder + 1 个 Vector Store + 1 个 SQLite 历史库（+ 可选 Reranker + 懒加载的实体存储）。

---

## 2. 目录结构

```
mem0_repo/
├── mem0/                        # Python 核心包
│   ├── __init__.py              # 对外导出 Memory / AsyncMemory / MemoryClient / AsyncMemoryClient
│   ├── exceptions.py            # 异常定义（Mem0ValidationError / LLMError / VectorStoreError ...）
│   ├── memory/                  # ★ 核心：Memory 类与记忆生命周期
│   │   ├── main.py              # ★★★ 最重要的文件（~3800 行），Memory/AsyncMemory 全部 API 实现
│   │   ├── base.py              # MemoryBase 抽象基类（get/get_all/update/delete/history）
│   │   ├── storage.py           # SQLiteManager：历史表 + 消息表
│   │   ├── setup.py             # ~/.mem0/config.json 与 user_id / 遥测身份
│   │   ├── utils.py             # 消息解析、JSON 提取、实体格式化、prompt 选择
│   │   ├── notices.py           # 首次运行 / 性能 / 时序等控制台提示
│   │   └── telemetry.py         # PostHog 遥测（可用 MEM0_TELEMETRY 关闭）
│   ├── vector_stores/           # 26 个向量库实现（qdrant/chroma/pgvector/pinecone/...）
│   │   ├── base.py              # VectorStoreBase 抽象接口（insert/search/update/delete/...）
│   │   └── qdrant.py            # ★ 示例实现：支持 gRPC、BM25 稀疏向量、search_batch
│   ├── llms/                    # 18 个 LLM 实现
│   │   ├── base.py              # LLMBase（generate_response 统一入口）
│   │   └── openai.py / deepseek.py / anthropic.py / ...
│   ├── embeddings/              # 11 个 Embedding 实现
│   │   ├── base.py              # EmbeddingBase（embed / embed_batch）
│   │   └── openai.py / huggingface.py / ...
│   ├── reranker/                # 重排序实现（cohere / sentence_transformer / llm ...）
│   ├── configs/                 # 各类配置与 Prompt 模板
│   │   ├── base.py              # MemoryConfig / MemoryItem 顶层配置
│   │   ├── prompts.py           # ★ 记忆抽取/更新/回答用的 Prompt 模板
│   │   ├── llms/ embeddings/ vector_stores/ rerankers/
│   │   └── enums.py             # MemoryType 等枚举
│   ├── utils/
│   │   ├── factory.py           # ★ 工厂注册表（LlmFactory/EmbedderFactory/VectorStoreFactory/RerankerFactory）
│   │   ├── entity_extraction.py # 实体抽取（extract_entities / extract_entities_batch）
│   │   ├── scoring.py           # 混合评分（语义 + BM25 + 实体 boost）
│   │   └── lemmatization.py     # BM25 词形归并
│   └── client/
│       └── main.py              # MemoryClient / AsyncMemoryClient（远程托管 API 客户端）
├── mem0-ts/                     # TypeScript 版本
├── openmemory/                  # 带 Web UI 的开源记忆服务
├── server/                      # 自托管 REST API 服务
├── integrations/                # LangChain / CrewAI / AutoGen 等框架集成
└── evaluation/                  # 评测
```

---

## 3. 架构设计

### 3.1 分层架构

```
                    ┌─────────────────────────────────────┐
   调用方            │  Memory / AsyncMemory   (本地 OSS)    │
   (Agent/App)      │  MemoryClient            (远程托管)    │
                    └───────────────┬─────────────────────┘
                                    │ 装配（工厂）
        ┌──────────────┬────────────┼──────────────┬─────────────┐
        ▼              ▼            ▼              ▼             ▼
     LLM 引擎      Embedder      VectorStore    Reranker      SQLite
  (抽取/回答)     (文本→向量)    (存储+检索)     (重排)       (历史/消息)
                                    │
                          ┌─────────┴──────────┐
                          ▼                    ▼
                     主 collection      entity collection
                    (记忆向量)          (实体-记忆关联)
```

### 3.2 工厂模式 + 可插拔 Provider

`utils/factory.py` 是唯一的装配点。每种引擎都有一个 `provider_to_class` 注册表，把 `provider` 字符串映射到具体的实现类路径：

```python
# VectorStoreFactory.provider_to_class 中的一行
"qdrant": "mem0.vector_stores.qdrant.Qdrant"
```

`Memory.__init__` 里就是四行装配（`memory/main.py:448-456`）：

```python
self.embedding_model = EmbedderFactory.create(...)   # 按 provider 创建 embedder
self.vector_store    = VectorStoreFactory.create(...) # 按 provider 创建向量库
self.llm             = LlmFactory.create(...)         # 按 provider 创建 LLM
self.db              = SQLiteManager(self.config.history_db_path)  # 历史库
```

> 换存储/换模型只改配置字符串，不改业务代码——这是 mem0 架构的核心设计。

### 3.3 双入口

- **本地 OSS 入口**（`memory/main.py`）：`Memory` / `AsyncMemory`，直接在进程内装配 LLM + Embedder + 本地/远程向量库，逻辑完全自包含。
- **远程托管入口**（`client/main.py`）：`MemoryClient` / `AsyncMemoryClient`，走 HTTP API（`api.mem0.ai`），本地不跑任何引擎，只做参数校验 + 请求封装。

两者 API 形状基本一致（`add / search / get_all / ...`），上层代码可以无感切换。

---

## 4. 核心模块

### 4.1 `memory/` — 记忆生命周期（核心）

| 文件 | 职责 |
| --- | --- |
| `main.py` | `Memory` / `AsyncMemory` 全部逻辑：写入 `add`、检索 `search`、增删改查、实体链接、去重 |
| `storage.py` | `SQLiteManager`：`history` 表（记忆变更流水）+ `messages` 表（原始消息） |
| `utils.py` | `parse_messages`（消息拼串）、`extract_json`/`remove_code_blocks`（解析 LLM 输出）、`format_entities` |
| `base.py` | `MemoryBase` 抽象接口，保证 sync/async 一致 |

### 4.2 `vector_stores/` — 向量存储层

统一抽象 `VectorStoreBase`（`base.py`），关键方法：

- `insert(vectors, payloads, ids)` — 批量插入
- `search(query, vectors, top_k, filters)` — 语义检索（**必须返回相似度，越大越像**）
- `keyword_search(query, top_k, filters)` — BM25/关键词检索（可选，默认返回 `None`）
- `search_batch(...)` — 批量检索（可选，Qdrant 等有原生实现）
- `update / delete / get / list / reset`

`qdrant.py` 是完整范例：用稀疏向量（BM25 encoder）实现 `keyword_search`，用 `query_batch_points` 实现 `search_batch`，并支持 gRPC 客户端注入（`config.client` 优先于 host/port）。

### 4.3 `llms/` — LLM 抽象

统一入口 `LLMBase.generate_response(messages, response_format=...)`。子类（`openai.py`、`deepseek.py`...）各自处理 provider 差异（参数名、`max_completion_tokens` vs `max_tokens`、reasoning 模型等）。

### 4.4 `embeddings/` — Embedding 抽象

`EmbeddingBase` 提供 `embed(text, memory_action)` 与 `embed_batch(texts, memory_action)`。`memory_action` 区分 `add/search/update`（某些 provider 对检索与写入用不同模型）。

### 4.5 `configs/` — 配置与 Prompt

- `base.py`：`MemoryConfig`（聚合 vector_store/llm/embedder/history_db_path/reranker/version/custom_instructions）
- `prompts.py`：**所有 Prompt 模板的集中地**，包括
  - `ADDITIVE_EXTRACTION_PROMPT` — V3 增量式记忆抽取（add 的核心 prompt）
  - `USER_MEMORY_EXTRACTION_PROMPT` / `AGENT_MEMORY_EXTRACTION_PROMPT` — 用户/Agent 记忆抽取
  - `DEFAULT_UPDATE_MEMORY_PROMPT` — 记忆更新
  - `MEMORY_ANSWER_PROMPT` — 用记忆回答问题
  - `PROCEDURAL_MEMORY_SYSTEM_PROMPT` — 程序性记忆

### 4.6 `utils/` — 基础设施

| 文件 | 职责 |
| --- | --- |
| `factory.py` | 四大工厂注册表 + `load_class`（字符串路径动态导入） |
| `entity_extraction.py` | 从文本抽取实体 `(type, text)`，供实体链接使用 |
| `scoring.py` | 混合评分（见 6.2） |
| `lemmatization.py` | BM25 用词形归并 |

---

## 5. 对外提供的功能（API 面）

### 5.1 `Memory` / `AsyncMemory`（本地）

| 方法 | 说明 |
| --- | --- |
| `add(messages, *, user_id, agent_id, run_id, metadata, infer=True, ...)` | 写入记忆。`infer=True` 走 LLM 抽取；`infer=False` 原样存 |
| `search(query, *, top_k=20, filters, threshold=0.1, rerank=False, ...)` | 语义/混合检索，`filters` 必须含 `user_id/agent_id/run_id` 至少一个 |
| `get(memory_id)` | 按 ID 取单条记忆 |
| `get_all(*, user_id, agent_id, run_id, ...)` | 列出一个 scope 下全部记忆 |
| `update(memory_id, data)` | 更新记忆 |
| `delete(memory_id)` / `delete_all(...)` | 删除单条 / 删除整个 scope |
| `history(memory_id)` | 查看一条记忆的变更历史 |
| `reset()` | 清空 |
| `chat(query)` | 记忆增强问答 |

### 5.2 `MemoryClient` / `AsyncMemoryClient`（远程托管）

在本地 API 基础上，额外提供托管平台能力：`batch_update`、`batch_delete`、`users` / `delete_users`、`create_memory_export` / `get_memory_export`、`get_summary`、`get_project` / `update_project`、`webhooks`、`feedback` 等。

### 5.3 过滤语法（search 的 filters）

支持增强型元数据过滤：精确匹配 `{"key":"v"}`、比较 `eq/ne/gt/gte/lt/lte`、`in/nin`、`contains/icontains`、通配 `*`，以及逻辑组合 `AND/OR/NOT`（`_process_metadata_filters` 翻译成各向量库原生过滤格式）。

---

## 6. 底层实现

### 6.1 写入链路：`add()` — V3 分阶段批处理流水线

`infer=True` 时（默认），`_add_to_vector_store`（`memory/main.py:831`）执行 8 个阶段：

| 阶段 | 动作 | 关键点 |
| --- | --- | --- |
| **0. 上下文收集** | 取 session 最近 10 条消息 | `db.get_last_messages` |
| **1. 已有记忆检索** | 向量检索 top_k=10 相关旧记忆 | 给 LLM 提供「去重/更新」上下文 |
| **2. LLM 抽取** | 单次调用 `ADDITIVE_EXTRACTION_PROMPT`，`response_format=json` | 返回 `{"memory":[{text,...}]}`；UUID 用 0..n 占位防幻觉 |
| **3. 批量 Embedding** | `embed_batch` 一次嵌入所有抽取文本 | 失败回退逐条 embed |
| **4/5. 去重** | 对每条记忆算 MD5，与已有 hash 和批内 hash 比对 | 重复直接跳过 |
| **6. 批量持久化** | `vector_store.insert` 批量写入；同步写 history 表 | payload 含 `data/hash/created_at/updated_at/text_lemmatized` |
| **7. 实体链接** | 批量抽取实体 → 去重 → 批量 embed → 批量 search → 插入/更新实体 collection | 语义匹配阈值 0.95 |
| **8. 收尾** | `db.save_messages` 存原始消息 | 供下次 add 的 Phase 0 使用 |

**`infer=False`** 则跳过 LLM，直接把每条消息 `embed` 后原样入库（`memory/main.py:832`）。

> 特点：**单次 LLM 调用**（不像旧版逐条抽取），**全链路批处理**（embed / insert / search 都 batch），**MD5 hash 去重**替代单纯语义去重。

### 6.2 检索链路：`search()` — 混合检索

`_search_vector_store`（`memory/main.py:1580`）分 9 步：

1. **预处理**：query 词形归并（BM25 用）+ 实体抽取
2. **Embed query**
3. **语义检索**：over-fetch（`limit*4` 与 60 取大）扩大候选池
4. **关键词检索**：`keyword_search`（BM25，仅支持的库如 Qdrant）
5. **算 BM25 分**：`normalize_bm25` 归一化到 [0,1]
6. **算实体 boost**：query 中的实体在 entity store 里查到关联记忆，加权
7. **构建候选集**：合并语义结果 + 过滤过期
8. **混合评分排序**：`score_and_rank` 综合 语义分 + BM25 分 + 实体 boost，按 threshold 过滤、top_k 截断
9. **格式化**：payload 拆成 `MemoryItem` 结构返回

`rerank=True` 且配置了 reranker 时，在最终结果上再做一次重排（`memory/main.py:1451`）。

### 6.3 历史存储（SQLite）

`storage.py` 的 `SQLiteManager` 维护两张表：

- **`history` 表**：`(memory_id, old_memory, new_memory, event, created_at, is_deleted)`，记录每条记忆的 `ADD/UPDATE/DELETE` 流水，支撑 `history(memory_id)` 与「记忆漂移」追踪。
- **`messages` 表**：按 `session_scope`（user/agent/run 组合）存原始消息，支撑 add 时的上下文回溯。

### 6.4 实体存储（entity store）

独立于主记忆 collection 的**第二个 collection**（懒加载 `entity_store` property，`memory/main.py:516`）。每条实体记录：

```json
{ "data": "实体名", "entity_type": "person/...", "linked_memory_ids": ["mem_id", ...] }
```

- **写入时**（Phase 7）：抽取实体 → 精确匹配（list 比对）或语义匹配（score≥0.95）→ 命中则追加 `linked_memory_ids`，否则新建实体。
- **检索时**（Step 6）：query 抽出实体 → 查实体 collection → 对关联记忆加 boost。
- **删除时**：从实体记录里摘除 `memory_id`，空了则删实体。

用途：让「提到同一实体」的记忆在检索时相互加权，提升召回。

### 6.5 去重机制

写入阶段用 **MD5 hash 精确去重**（`memory/main.py:972`）：`hashlib.md5(text.encode()).hexdigest()`，与向量库中已有 hash、以及当前批次内 hash 双重比对。这是记忆幂等写入的关键，避免同一事实反复入库。

---

## 7. 关键设计要点总结

1. **可插拔是灵魂**：LLM / Embedder / VectorStore / Reranker 全部通过 `factory.py` 字符串映射装配，换实现零侵入。
2. **双入口同形 API**：本地 `Memory` 与远程 `MemoryClient` 方法签名一致。
3. **写入 = 单次 LLM + 全批处理**：V3 流水线把「抽取→去重→入库→实体链接」做成 8 个阶段，批量化所有 IO。
4. **检索 = 混合召回**：语义向量 + BM25 关键词 + 实体 boost 三者融合评分，`score_and_rank` 统一归一。
5. **记忆与实体分离存储**：主 collection 存记忆，entity collection 存实体-记忆关联，互为增强。
6. **历史可追踪**：SQLite `history` 表记录每次 ADD/UPDATE/DELETE，支撑 `history()` 与审计。
7. **幂等靠 hash**：MD5 精确去重，语义层面再由 LLM 的增量抽取兜底。
8. **遥测可关闭**：`MEM0_TELEMETRY=false` 可禁用 PostHog 上报（见 `memory/telemetry.py` 与 `memory/setup.py`）。

---

## 8. 建议阅读顺序

```
mem0/__init__.py                     → 了解导出面
mem0/memory/main.py:444              → Memory.__init__（装配）
mem0/memory/main.py:717-1158         → add 全流程（V3 流水线）
mem0/memory/main.py:1331-1684        → search 全流程（混合检索）
mem0/utils/factory.py                → 工厂注册与装配机制
mem0/configs/prompts.py              → 抽取/更新 Prompt 模板
mem0/memory/storage.py               → SQLite 历史/消息表
mem0/vector_stores/qdrant.py         → 一个完整的向量库实现范例
```
