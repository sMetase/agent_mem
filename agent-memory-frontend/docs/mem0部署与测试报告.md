## mem0部署与测试报告

第二个工作日完成了mem0的本地部署，并且结合官方文档测试了mem0的功能。我将mem0已经具备的功能与本项目的功能需求做对比，了解哪些功能需要扩展，哪些功能可以直接复用。

**注意：**此文档内容有待与组员商议。

### 部署过程总结

#### 部署决策

我选择用docker compose+postgreSQL+pgvector+Neo4j的方式本地部署mem0。

模型选择Ollama本地模型，根据本机的硬件情况，选择qwen3.5:4b中文模型，文本嵌入模型使用nomic-embed-text

本地部署采取以下架构：

```
  |
   | HTTP
   v
Mem0 REST API  http://localhost:8888
   |
   +-- Postgres + pgvector  记忆向量存储
   |
   +-- Neo4j          实体关系/图谱记忆
   |
   +-- Ollama              本地 LLM + Embedding
```

#### 部署中遇到的问题

**环境配置.env相关问题**：

1. Windows端口保留：官方文档提示的3000在本机无法使用，故选择其他可用端口
2. postgreSQL密码格式：最初的随机生成密码中存在斜杠，在插值生成字符串时造成URL错乱，表现为DNS异常。更改密码为纯字母+数字组合
3. 模型配置：mem0默认支持OpenAI/Gemini，不支持本地模型，需要自行配置。
4. 网络暴露问题：AUTH_DISABLED=true，限制在本机开发联调，禁止暴露到公网。

**本地模型与词向量处理链路问题：**

1. mem0不支持本地模型作为provider：需要让服务端将ollama纳入为可用provider，将默认LLM/嵌入模型指向本地模型。
2. 嵌入模型与mem0默认向量维数对齐：nomic-embed-text的维数是768，mem0默认pgvector是1536，需要显式改动。

**其他问题：**

1. infer=false显式写入、搜索、删除正常，但是infer=true和本地模型自动抽取却返回空结果：推测是mem0的固有问题，需要我们在系统中拓展此功能。

### 测试总结

这次冒烟测试的目的是根据mem0的官方文档确认mem0的已有功能，与本项目设计文档作比较，确定复用/扩展方向。

#### 可复用功能

原结论不变，mem0可以作为本项目的记忆基座。具体具备的功能如下：

1. 认证功能：存在注册、登录、刷新token、个人信息、API创建/吊销，可以有限复用
2. 记忆写入：POST /memories写入
3. 记忆查询：GET /memories按user_id查询
4. 语义检索：POST /search 支持检索、过滤、top_k检索等。有限复用，可作为基础检索
5. 记忆更新/删除：PUT /memories/{id}支持记忆更新，DELETE /memories/{id}支持记忆删除
6. 记忆历史：GET /memories/{id}/history查看记忆写入/更新历史
7. 实体列表：GET /entities 可以列出user实体

注意：infer=false显式写入、搜索、删除正常，但是infer=true和本地模型自动抽取却返回空结果：推测是mem0的固有问题，需要我们在系统中拓展此功能。

#### 测试流程记录

下面附上测试流程和结果截图：

**服务状态验证**：![image-20260630095637103](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630095637103.png)

容器服务正常运行，端口占用情况按预期进行

**登录与token保存**：

![image-20260630095746933](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630095746933.png)

通过auth接口验证登陆情况，登陆情况如图：

![image-20260630095823807](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630095823807.png)

**配置情况验证：**

使用configure接口查看本地mem0服务的模型配置

![image-20260630095948148](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630095948148.png)

![image-20260630095956524](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630095956524.png)

**记忆写入**：

指定用户名、用户身份、agent_id、元数据等信息，infer指定为false。查看记忆内容，得知写入正常完成

![image-20260630101105833](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630101105833.png)

memory id也能够正确拿到

![image-20260630101137278](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630101137278.png)

**根据用户id检索记忆**：可以正常捕获该用户名下的记忆

![image-20260630101212696](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630101212696.png)

**抽取用户偏好：**

![image-20260630110425793](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630110425793.png)

指定user_id，top_k指定为5，检索用户的偏好信息。

返回结果中重点观察score，user_id和score_details.semantic_score这三个指标

**指定memories_id筛选memories：**

![image-20260630110650121](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630110650121.png)

根据response可知回复正确

**更新记忆**![image-20260630110723452](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630110723452.png)

使用接口/PUT memories，最后回复Memory updated successfully!

**查询记忆更新历史：**

![image-20260630110834205](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630110834205.png)

共回复两条更新信息，一条add和一条put，正确。

**删除记忆记录：**

![image-20260630110912414](C:\Users\lenovo\AppData\Roaming\Typora\typora-user-images\image-20260630110912414.png)

使用接口/DELETE memories，指定删除记忆的id。最终返回Memory deleted successfully信息说明删除成功

以上测试结果验证了mem0已经具备本项目记忆基座所需的功能。

#### 扩展方向

然而测试流程中也发现了mem0的局限：

当infer指定为true时，发现检索的结果为空，这说明mem0 默认抽取链路需优化提示词/模型配置，由于模型配置为本地小参数模型，可能无法满足mem0要求的模型配置。

此外还根据文档和测试情况发现了项目可能存在的扩展方向，可能的扩展方向以表格形式给出：

| 扩展方向                 | mem0 局限                                                    |
| ------------------------ | ------------------------------------------------------------ |
| 分层记忆模型 UI          | 文档要求用户级、会话级、任务级、智能体状态级；mem0 只有基础字段，需要业务化分类和视图 |
| 记忆类型与标签体系       | 文档要求事实型、偏好型、任务型、过程型、反馈型等；mem0 默认不等于完整企业分类 |
| 记忆状态管理             | 文档要求有效、失效、冲突、待确认、冷归档、强制遗忘等；mem0 主要是 update/delete/history |
| 去重融合与冲突处理工作台 | mem0 会做基础抽取/更新，但文档要求相似度匹配、实体校验、版本关系、冲突标记和可追溯记录 |
| 多信号融合检索调试台     | mem0 本地 search 有语义分数和部分 score details，但文档要求语义、关键词、实体、时间、重要性、置信度、调用频次综合排序 |
| 上下文装配预览           | mem0 返回记忆列表；文档要求 JSON 与 prompt 片段双格式、预算控制、分组裁剪、一致性校验 |
| 长对话压缩管理           | mem0 可存记忆，但文档强调长对话分段、压缩、关键事实保持、上下文恢复质量控制 |
| 数据标注与人工审核       | 文档明确 B/S 后台要有数据标注、记忆审计；mem0 dashboard 更偏基础管理 |
| 系统监控与运维面板       | mem0 有基础请求/配置接口，但文档要求日志审计、监控告警、性能测试、高并发指标 |
| 企业多租户/SSO/权限矩阵  | mem0 有 auth/API key，但文档要求企业统一身份认证、多场景硬/软隔离、权限标签 |
| 图谱关系与版本链路       | mem0 Platform 有 Graph Memory，但你本地 OSS 未直接体现企业级图数据库关系/多跳推理 |