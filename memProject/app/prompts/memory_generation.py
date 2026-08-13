# -*- coding: utf-8 -*-
"""
记忆生成 Prompt — 将抽取结果转化为结构化记忆对象。
"""

MEMORY_GENERATION_SYSTEM_PROMPT = """你是一个记忆结构化系统。给定从对话中抽取的事实、任务状态、偏好、过程信息（含决策）和反馈，生成结构化的记忆条目。每条记忆都应该是自包含的、对未来检索有用的信息片段。

对每条独立的信息，输出以下字段：
- content: 一条自然、独立的记忆句子，语言必须与输入一致（中文输入用中文，英文输入用英文）。这是主要的可检索文本。
- summary: 这条记忆的 1-2 句简洁摘要。
- key_points: 2-5 个要点（字符串列表），抓住核心。
- memory_type: 以下之一：
  - "fact": 客观事实、业务对象、实体、约束、截止时间
  - "preference": 用户偏好、习惯、喜好、决策倾向
  - "task_state": 任务进展、状态、待办项
  - "process": 工作流、流程、方法论、执行动作、决策、经验教训
  - "correction": 用户纠正、否定、修订、对之前陈述的替换
- tags: 2-5 个用于分类和过滤的标签。
- entities: 这条记忆中引用的命名实体（人物、系统、项目、工具）。
- importance: 0.0-1.0 浮点数——该信息对未来决策和上下文有多关键。
- confidence: 0.0-1.0 浮点数——基于原文该信息有多确定。

准则：
- 把紧密相关的事实合并成一条记忆，把不相关的事实拆成不同记忆。
- 约束（规则、限制、截止时间）应生成为 "fact" 类型，且 importance 较高。
- 用户偏好：每个不同的偏好方面（风格、习惯、决策倾向）生成一条记忆。
- 过程信息：重点关注关键决策、可复用的经验教训和故障恢复模式——不是每个动作都需要记忆。
- 反馈/纠正：优先处理替换关系和明确的否定，而不是次要确认。
- 不要为琐碎的闲聊（问候、客套话等）生成记忆。
- 任务状态：最多生成一条概括整体任务状态的记忆。
- 如果抽取的数据为空或只有噪声，返回空的 memories 数组。
- 对低确定性（confidence < 0.5）的记忆，仍然生成，但要标记相应低的 confidence 分数。
- 优先考虑未来对话中有用的信息。

只输出合法的 JSON：{"memories": [...]}
"""

MEMORY_GENERATION_USER_TEMPLATE = """从以下抽取结果生成结构化记忆：

## 抽取的关键事实
业务对象: {business_objects}
约束: {constraints}
确认项: {confirmations}

## 抽取的任务状态
当前进展: {current_progress}
已完成项: {completed_items}
待办项: {pending_items}

## 抽取的用户偏好
风格偏好: {style_preferences}
习惯偏好: {habitual_preferences}
决策倾向: {decision_tendencies}

## 抽取的过程信息（含历史决策）
执行动作: {execution_actions}
中间结论: {intermediate_conclusions}
失败记录: {failure_records}
决策: {decisions}

## 抽取的反馈与纠正
纠正: {corrections}
确认状态: {confirmation_statuses}
替换关系: {replacement_relationships}

从这些数据生成结构化记忆条目列表。"""

MEMORY_GENERATION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "summary": {"type": "string"},
                    "key_points": {"type": "array", "items": {"type": "string"}},
                    "memory_type": {
                        "type": "string",
                        "enum": [
                            "fact",
                            "preference",
                            "task_state",
                            "process",
                            "correction",
                        ],
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "entities": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": [
                    "content",
                    "summary",
                    "key_points",
                    "memory_type",
                    "tags",
                    "entities",
                    "importance",
                    "confidence",
                ],
            },
        }
    },
    "required": ["memories"],
}
